# This file is part of ts_salobj.
#
# Developed for the LSST Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import contextlib
import itertools
import logging
import os
import pathlib
import sys
import unittest

import asynctest
import numpy as np
import yaml

from lsst.ts import salobj

# Long enough to perform any reasonable operation
# including starting a CSC or loading a script (seconds)
STD_TIMEOUT = 60
# Timeout for when we expect no new data (seconds).
NODATA_TIMEOUT = 0.1

np.random.seed(47)

index_gen = salobj.index_generator()
TEST_DATA_DIR = TEST_CONFIG_DIR = pathlib.Path(__file__).resolve().parent / "data"
TEST_CONFIG_DIR = TEST_DATA_DIR / "config"


def all_permutations(items):
    """Return all permutations of a list of items and of all sublists,
    including [].
    """
    for i in range(len(items) + 1):
        for val in itertools.permutations(items, r=i):
            yield val


class FailInReportFaultCsc(salobj.TestCsc):
    """A Test CSC that fails in report_summary_state when reporting fault.

    This CSC always starts up in the ENABLED state.

    Used to test for infinite loops and other issues when something
    goes wrong while going to the fault state.

    Parameters
    ----------
    index : `int`
        SAL index.
    doraise : `bool`
        Raise in report_summary_state?
        If false then call fault instead.
    report_first : `bool`
        Call super().report_summary_state first in report_summary_state?
        If false then call it last.
    """

    def __init__(self, index, doraise, report_first):
        super().__init__(index=index, initial_state=salobj.State.ENABLED)
        self.doraise = doraise
        self.report_first = report_first

    def report_summary_state(self):
        if self.report_first:
            super().report_summary_state()
        if self.summary_state == salobj.State.FAULT:
            if self.doraise:
                raise RuntimeError(
                    "Intentionally raise an exception when going to the FAULT state"
                )
            else:
                self.fault(
                    code=10934,
                    report="a report that will be ignored",
                    traceback="a traceback that will be ignored",
                )
        if not self.report_first:
            super().report_summary_state()


class CommunicateTestCase(salobj.BaseCscTestCase, asynctest.TestCase):
    def basic_make_csc(self, initial_state, config_dir, simulation_mode):
        return salobj.TestCsc(
            self.next_index(),
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    @contextlib.asynccontextmanager
    async def make_remote(
        self, identity,
    ):
        """Create a remote to talk to self.csc with a specified identity.

        Uses the domain created by make_csc.

        Parameters
        ----------
        identity : `str`
            Identity for remote.

        Notes
        -----
        Adds a logging.StreamHandler if one is not alread present.
        """
        domain = self.csc.domain
        original_default_identity = domain.default_identity
        try:
            domain.default_identity = identity
            remote = salobj.Remote(
                domain=domain, name=self.csc.salinfo.name, index=self.csc.salinfo.index,
            )
        finally:
            domain.default_identity = original_default_identity
        self.assertEqual(remote.salinfo.identity, identity)
        try:
            await remote.start_task
            yield remote
        finally:
            await remote.close()

    async def test_authorization(self):
        """Test authorization.

        For simplicity this test calls setAuthList without a +/- prefix.
        The prefix is tested elsewhere.
        """
        async with self.make_csc(initial_state=salobj.State.ENABLED):
            # TODO DM-26605 remove this line as no longer needed:
            self.csc.authorize = True
            await self.assert_next_sample(
                self.remote.evt_authList, authorizedUsers="", nonAuthorizedCSCs="",
            )

            domain = self.csc.salinfo.domain

            # Note that self.csc and self.remote have the same user_host.
            csc_user_host = domain.user_host

            # Make a remote that pretends to be from a different CSC
            # and test non-authorized CSCs
            other_name_index = "Script:5"
            async with self.make_remote(identity=other_name_index) as other_csc_remote:

                all_csc_names = ["ATDome", "Hexapod:1", other_name_index]
                for csc_names in all_permutations(all_csc_names):
                    csc_names_str = ", ".join(csc_names)
                    with self.subTest(csc_names_str=csc_names_str):
                        await self.remote.cmd_setAuthList.set_start(
                            nonAuthorizedCSCs=csc_names_str, timeout=STD_TIMEOUT
                        )
                        await self.assert_next_sample(
                            self.remote.evt_authList,
                            authorizedUsers="",
                            nonAuthorizedCSCs=", ".join(sorted(csc_names)),
                        )
                        if other_name_index in csc_names:
                            # A blocked CSC; this should fail.
                            with salobj.assertRaisesAckError(
                                ack=salobj.SalRetCode.CMD_NOPERM
                            ):
                                await other_csc_remote.cmd_wait.set_start(
                                    duration=0, timeout=STD_TIMEOUT
                                )
                        else:
                            # Not a blocked CSC; this should work.
                            await other_csc_remote.cmd_wait.set_start(
                                duration=0, timeout=STD_TIMEOUT
                            )

                        # My user_host should work regardless of
                        # non-authorized CSCs.
                        await self.remote.cmd_wait.set_start(
                            duration=0, timeout=STD_TIMEOUT
                        )

                        # Disabling authorization should always work
                        self.csc.cmd_wait.authorize = False
                        try:
                            await other_csc_remote.cmd_wait.set_start(
                                duration=0, timeout=STD_TIMEOUT
                            )
                        finally:
                            self.csc.cmd_wait.authorize = True

            # Test authorized users that are not me.
            # Reported auth users should always be in alphabetical order;
            # test this by sending users NOT in alphabetical order.
            all_other_user_hosts = [f"notme{i}{csc_user_host}" for i in (3, 2, 1)]
            other_user_host = all_other_user_hosts[1]

            async with self.make_remote(identity=other_user_host) as other_user_remote:
                for auth_user_hosts in all_permutations(all_other_user_hosts):
                    users_str = ", ".join(auth_user_hosts)
                    with self.subTest(users_str=users_str):
                        await self.remote.cmd_setAuthList.set_start(
                            authorizedUsers=users_str,
                            nonAuthorizedCSCs="",
                            timeout=STD_TIMEOUT,
                        )
                        await self.assert_next_sample(
                            self.remote.evt_authList,
                            authorizedUsers=", ".join(sorted(auth_user_hosts)),
                            nonAuthorizedCSCs="",
                        )
                        if other_user_host in auth_user_hosts:
                            # An allowed user; this should work.
                            await other_user_remote.cmd_wait.set_start(
                                duration=0, timeout=STD_TIMEOUT
                            )
                        else:
                            # Not an allowed user; this should fail.
                            with salobj.assertRaisesAckError(
                                ack=salobj.SalRetCode.CMD_NOPERM
                            ):
                                await other_user_remote.cmd_wait.set_start(
                                    duration=0, timeout=STD_TIMEOUT
                                )

                        # Temporarily disable authorization and try again;
                        # this should always work.
                        self.csc.cmd_wait.authorize = False
                        try:
                            await other_user_remote.cmd_wait.set_start(
                                duration=0, timeout=STD_TIMEOUT
                            )
                        finally:
                            self.csc.cmd_wait.authorize = True

                        # My user_host should work regardless of
                        # authorized users.
                        self.remote.salinfo.domain.identity = csc_user_host
                        await self.remote.cmd_wait.set_start(
                            duration=0, timeout=STD_TIMEOUT
                        )

    async def test_set_auth_list_prefix(self):
        """Test the setAuthList command with a +/- prefix
        """
        async with self.make_csc(initial_state=salobj.State.ENABLED):
            await self.assert_next_sample(
                self.remote.evt_authList, authorizedUsers="", nonAuthorizedCSCs="",
            )

            all_csc_names = ["Test:5", "ATDome:0", "ATDome"]
            expected_cscs_set = set()
            # Test adding non-authorized CSCs.
            # Test that a trailing :0 is stripped (so, in this test
            # setAuthList treats ATDome:0 and ATDome as the same CSC).
            # Reported non-auth CSCs should always be in alphabetical order;
            # test this by sending CSC names NOT in alphabetical order.
            for i in range(len(all_csc_names)):
                csc_names = all_csc_names[:i]
                # Compute a variant of csc_names with trailing :0 stripped
                # and use that for the expected output from the authList event.
                nonzero_csc_names = [
                    csc[:-2] if csc.endswith(":0") else csc for csc in csc_names
                ]
                expected_cscs_set |= set(nonzero_csc_names)
                add_some_str = "+ " + ", ".join(csc_names)
                await self.remote.cmd_setAuthList.set_start(
                    nonAuthorizedCSCs=add_some_str, timeout=STD_TIMEOUT
                )
                await self.assert_next_sample(
                    self.remote.evt_authList,
                    authorizedUsers="",
                    nonAuthorizedCSCs=", ".join(sorted(expected_cscs_set)),
                )

            # Removing CSCs should have the expected effect
            for i in range(len(all_csc_names)):
                csc_names = all_csc_names[:i]
                # Compute a variant of csc_names with trailing :0 stripped
                # and use that for the expected output from the authList event.
                nonzero_csc_names = [
                    csc[:-2] if csc.endswith(":0") else csc for csc in csc_names
                ]
                expected_cscs_set -= set(nonzero_csc_names)
                remove_some_str = "- " + ", ".join(csc_names)
                await self.remote.cmd_setAuthList.set_start(
                    nonAuthorizedCSCs=remove_some_str, timeout=STD_TIMEOUT
                )
                await self.assert_next_sample(
                    self.remote.evt_authList,
                    authorizedUsers="",
                    nonAuthorizedCSCs=", ".join(sorted(expected_cscs_set)),
                )

            # Test setting authorized users.
            # Test that user = csc_user_host (the CSC's user_host) is ignored.
            # Reported auth users should always be in alphabetical order;
            # test this by sending users NOT in alphabetical order.
            csc_user_host = salobj.get_user_host()
            all_users_hosts = [csc_user_host] + [
                f"notme{i}{csc_user_host}" for i in (3, 2, 1)
            ]
            expected_user_set = set()
            # Test adding authorized users; only users other than "me"
            # are actually added.
            for i in range(len(all_users_hosts)):
                user_names = all_users_hosts[:i]
                expected_user_set |= set(user_names)
                expected_user_set -= {csc_user_host}
                add_some_str = "+ " + ", ".join(user_names)
                await self.remote.cmd_setAuthList.set_start(
                    authorizedUsers=add_some_str, timeout=STD_TIMEOUT
                )
                await self.assert_next_sample(
                    self.remote.evt_authList,
                    authorizedUsers=", ".join(sorted(expected_user_set)),
                    nonAuthorizedCSCs="",
                )

            # Removing authorized users should have the expected effect
            for i in range(len(all_users_hosts)):
                user_names = all_users_hosts[:i]
                expected_user_set -= set(user_names)
                remove_some_str = "- " + ", ".join(user_names)
                await self.remote.cmd_setAuthList.set_start(
                    authorizedUsers=remove_some_str, timeout=STD_TIMEOUT
                )
                await self.assert_next_sample(
                    self.remote.evt_authList,
                    authorizedUsers=", ".join(sorted(expected_user_set)),
                    nonAuthorizedCSCs="",
                )

    async def test_heartbeat(self):
        async with self.make_csc(initial_state=salobj.State.STANDBY):
            self.csc.heartbeat_interval = 0.1
            await self.remote.evt_heartbeat.next(flush=True, timeout=STD_TIMEOUT)
            await self.remote.evt_heartbeat.next(flush=True, timeout=0.2)
            await self.remote.evt_heartbeat.next(flush=True, timeout=0.2)
            await self.remote.evt_heartbeat.next(flush=True, timeout=0.2)

    async def test_bin_script(self):
        """Test running the Test CSC from the bin script.

        Note that the bin script calls class method ``amain``.
        """
        index = self.next_index()
        await self.check_bin_script(
            name="Test", index=index, exe_name="run_test_csc.py"
        )

    async def test_log_level(self):
        """Test that specifying a log level to make_csc works."""
        # If specified then log level is the value given.
        async with self.make_csc(
            initial_state=salobj.State.STANDBY, log_level=logging.DEBUG
        ):
            self.assertEqual(self.csc.log.getEffectiveLevel(), logging.DEBUG)

        async with self.make_csc(
            initial_state=salobj.State.STANDBY, log_level=logging.WARNING
        ):
            self.assertEqual(self.csc.log.getEffectiveLevel(), logging.WARNING)

        # At this point log level is WARNING; now check that by default
        # log verbosity is increased (log level decreased) to INFO.
        async with self.make_csc(initial_state=salobj.State.STANDBY):
            self.assertEqual(self.csc.log.getEffectiveLevel(), logging.INFO)

    async def test_setArrays_command(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED):
            # until the controller gets its first setArrays
            # it will not send any arrays events or telemetry
            self.assertFalse(self.csc.evt_arrays.has_data)
            self.assertFalse(self.csc.tel_arrays.has_data)
            self.assertFalse(self.remote.evt_arrays.has_data)
            self.assertFalse(self.remote.tel_arrays.has_data)
            self.assertIsNone(self.remote.evt_arrays.get())
            self.assertIsNone(self.remote.tel_arrays.get())

            # check that info level messages are enabled
            await self.assert_next_sample(
                topic=self.remote.evt_logLevel, level=logging.INFO
            )

            # purge any existing messages
            self.remote.evt_logMessage.flush()

            # send the setArrays command with random data
            cmd_data_sent = self.csc.make_random_cmd_arrays()
            await self.remote.cmd_setArrays.start(cmd_data_sent, timeout=STD_TIMEOUT)

            log_message = await self.remote.evt_logMessage.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(log_message.level, logging.INFO)
            self.assertIn("setArrays", log_message.message)

            # see if new data was broadcast correctly
            evt_data = await self.remote.evt_arrays.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.csc.assert_arrays_equal(cmd_data_sent, evt_data)
            tel_data = await self.remote.tel_arrays.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.csc.assert_arrays_equal(cmd_data_sent, tel_data)

            self.assertTrue(self.csc.evt_arrays.has_data)
            self.assertTrue(self.csc.tel_arrays.has_data)
            self.assertTrue(self.remote.evt_arrays.has_data)
            self.assertTrue(self.remote.tel_arrays.has_data)

            # also test get
            self.csc.assert_arrays_equal(cmd_data_sent, self.remote.tel_arrays.get())
            self.csc.assert_arrays_equal(cmd_data_sent, self.remote.evt_arrays.get())

    async def test_setScalars_command(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED):
            # until the controller gets its first setArrays
            # it will not send any arrays events or telemetry
            self.assertFalse(self.csc.evt_scalars.has_data)
            self.assertFalse(self.csc.tel_scalars.has_data)
            self.assertFalse(self.remote.evt_scalars.has_data)
            self.assertFalse(self.remote.tel_scalars.has_data)
            self.assertIsNone(self.remote.evt_scalars.get())
            self.assertIsNone(self.remote.tel_scalars.get())

            # check that info level messages are enabled
            await self.assert_next_sample(
                topic=self.remote.evt_logLevel, level=logging.INFO
            )

            # purge any existing messages
            self.remote.evt_logMessage.flush()

            # send the setScalars command with random data
            cmd_data_sent = self.csc.make_random_cmd_scalars()
            await self.remote.cmd_setScalars.start(cmd_data_sent, timeout=STD_TIMEOUT)
            log_message = await self.remote.evt_logMessage.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(log_message.level, logging.INFO)
            self.assertIn("setScalars", log_message.message)

            # see if new data is being broadcast correctly
            evt_data = await self.remote.evt_scalars.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.csc.assert_scalars_equal(cmd_data_sent, evt_data)
            tel_data = await self.remote.tel_scalars.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.csc.assert_scalars_equal(cmd_data_sent, tel_data)

            self.assertTrue(self.csc.evt_scalars.has_data)
            self.assertTrue(self.csc.tel_scalars.has_data)
            self.assertTrue(self.remote.evt_scalars.has_data)
            self.assertTrue(self.remote.tel_scalars.has_data)

            # also test get
            self.csc.assert_scalars_equal(cmd_data_sent, self.remote.tel_scalars.get())
            self.csc.assert_scalars_equal(cmd_data_sent, self.remote.evt_scalars.get())

    async def test_fault_state_transitions(self):
        """Test CSC state transitions into fault and out again.

        Going into the fault state is done via the ``fault`` command.
        """
        for initial_state in salobj.State:
            if initial_state == salobj.State.OFFLINE:
                # Not a valid initial state
                continue
            if initial_state == salobj.State.FAULT:
                # The ``fault`` command does nothing if TestCsc
                # is already in the FAULT state
                continue
            with self.subTest(initial_state=initial_state):
                async with self.make_csc(initial_state=initial_state):
                    await self.assert_next_summary_state(initial_state)

                    # Issue the ``fault`` command
                    # and check the state and error code.
                    await self.remote.cmd_fault.start(timeout=STD_TIMEOUT)
                    await self.assert_next_summary_state(salobj.State.FAULT)
                    await self.assert_next_sample(
                        topic=self.remote.evt_errorCode, errorCode=1
                    )

                    # Issue the ``standby`` command to recover.
                    await self.remote.cmd_standby.start(timeout=STD_TIMEOUT)
                    await self.assert_next_summary_state(salobj.State.STANDBY)

    async def test_fault_method(self):
        """Test BaseCsc.fault with and without optional arguments."""
        async with self.make_csc(initial_state=salobj.State.STANDBY):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            with self.assertRaises(asyncio.TimeoutError):
                await self.remote.evt_errorCode.next(
                    flush=False, timeout=NODATA_TIMEOUT
                )

            code = 52
            report = "Report for error code"
            traceback = "Traceback for error code"

            # if an invalid code is specified then errorCode is not output
            # but the CSC stil goes into a FAULT state
            self.csc.fault(code="not a valid code", report=report)
            await self.assert_next_summary_state(salobj.State.FAULT)
            with self.assertRaises(asyncio.TimeoutError):
                await self.remote.evt_errorCode.next(
                    flush=False, timeout=NODATA_TIMEOUT
                )

            await self.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.assert_next_summary_state(salobj.State.STANDBY)

            # if code is specified then errorReport is output;
            # first test with report and traceback specified,
            # then without, to make sure those values are not cached
            self.csc.fault(code=code, report=report, traceback=traceback)
            await self.assert_next_summary_state(salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=code,
                errorReport=report,
                traceback=traceback,
            )

            # Try a disallowed command and check that the error report
            # is part of the traceback.
            with salobj.assertRaisesAckError(result_contains=report):
                await self.remote.cmd_wait.set_start(duration=5, timeout=STD_TIMEOUT)

            await self.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.assert_next_summary_state(salobj.State.STANDBY)

            self.csc.fault(code=code, report="")
            await self.assert_next_summary_state(salobj.State.FAULT)
            await self.assert_next_sample(
                topic=self.remote.evt_errorCode,
                errorCode=code,
                errorReport="",
                traceback="",
            )

            await self.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.remote.cmd_exitControl.start(timeout=STD_TIMEOUT)

    async def test_fault_problems(self):
        """Test BaseCsc.fault when report_summary_state misbehaves."""
        index = self.next_index()
        for doraise, report_first in itertools.product((False, True), (False, True)):
            with self.subTest(doraise=doraise, report_first=report_first):
                async with FailInReportFaultCsc(
                    index=index, doraise=doraise, report_first=report_first
                ) as csc, salobj.Remote(
                    domain=csc.domain, name="Test", index=index
                ) as remote:
                    await self.assert_next_summary_state(
                        salobj.State.ENABLED, remote=remote
                    )

                    code = 51
                    report = "Report for error code"
                    traceback = "Traceback for error code"
                    csc.fault(code=code, report=report, traceback=traceback)

                    await self.assert_next_summary_state(
                        salobj.State.FAULT, remote=remote
                    )
                    await self.assert_next_sample(
                        topic=remote.evt_errorCode,
                        errorCode=code,
                        errorReport=report,
                        traceback=traceback,
                    )

                    # make sure FAULT state and errorCode are only sent once
                    with self.assertRaises(asyncio.TimeoutError):
                        await remote.evt_summaryState.next(
                            flush=False, timeout=NODATA_TIMEOUT
                        )
                    with self.assertRaises(asyncio.TimeoutError):
                        await remote.evt_errorCode.next(
                            flush=False, timeout=NODATA_TIMEOUT
                        )

    async def test_make_csc_timeout(self):
        """Test that setting the timeout argument to make_csc works.
        """
        with self.assertRaises(asyncio.TimeoutError):
            # Use such a short timeout that make_csc times out
            async with self.make_csc(initial_state=salobj.State.STANDBY, timeout=0):
                pass

    async def test_standard_state_transitions(self):
        """Test standard CSC state transitions.

        The initial state is STANDBY.
        The standard commands and associated state transitions are:

        * start: STANDBY to DISABLED
        * enable: DISABLED to ENABLED

        * disable: ENABLED to DISABLED
        * standby: DISABLED or FAULT to STANDBY
        * exitControl: STANDBY to OFFLINE (quit)
        """
        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.check_standard_state_transitions(
                enabled_commands=("setArrays", "setScalars", "wait"),
                skip_commands=("fault",),
                settingsToApply="all_fields",
            )


class NoIndexCsc(salobj.TestCsc):
    """A CSC whose constructor has no index argument."""

    def __init__(self, arg1, arg2, config_dir=None):
        super().__init__(index=next(index_gen), config_dir=config_dir)
        self.arg1 = arg1
        self.arg2 = arg2


class InvalidPkgNameCsc(salobj.TestCsc):
    """A CSC whose get_pkg_name classmethod returns a nonexistent package.
    """

    @staticmethod
    def get_config_pkg():
        """Return a name of a non-existent package."""
        return "not_a_valid_pkg_name"


class WrongConfigPkgCsc(salobj.TestCsc):
    """A CSC whose get_pkg_name classmethod returns the wrong package.
    """

    @staticmethod
    def get_config_pkg():
        """Return a package that does not have a Test subdirectory."""
        return "ts_salobj"


class TestCscConstructorTestCase(asynctest.TestCase):
    """Test the TestCsc constructor.

    Note: all of these tests must run async because the constructor
    requires an event loop.
    """

    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()

    async def test_initial_state(self):
        """Test all allowed initial_state values, both as enums and ints."""
        for initial_state in salobj.State:
            if initial_state == salobj.State.OFFLINE:
                continue
            with self.subTest(initial_state=initial_state):
                # Test initial_state as an enum.
                index = next(index_gen)
                async with salobj.TestCsc(
                    index=index, initial_state=initial_state
                ) as csc:
                    self.assertEqual(csc.summary_state, initial_state)

                # Test initial_state as an integer.
                index = next(index_gen)
                async with salobj.TestCsc(
                    index=index, initial_state=int(initial_state)
                ) as csc:
                    self.assertEqual(csc.summary_state, initial_state)

    async def test_invalid_config_dir(self):
        """Test that invalid integer initial_state is rejected."""
        with self.assertRaises(ValueError):
            salobj.TestCsc(
                index=next(index_gen),
                initial_state=salobj.State.STANDBY,
                config_dir=TEST_CONFIG_DIR / "not_a_directory",
            )

    async def test_invalid_config_pkg(self):
        with self.assertRaises(RuntimeError):
            InvalidPkgNameCsc(index=next(index_gen), initial_state=salobj.State.STANDBY)

    async def test_wrong_config_pkg(self):
        with self.assertRaises(RuntimeError):
            WrongConfigPkgCsc(index=next(index_gen), initial_state=salobj.State.STANDBY)

    async def test_invalid_initial_state(self):
        """Test that invalid integer initial_state is rejected."""
        for invalid_state in (min(salobj.State) - 1, max(salobj.State) + 1):
            with self.subTest(invalid_state=invalid_state):
                with self.assertRaises(ValueError):
                    salobj.TestCsc(index=next(index_gen), initial_state=invalid_state)


class SimulationModeTestCase(asynctest.TestCase):
    """Test simulation mode handling, including the --simulate
    command-line argument.
    """

    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()
        # Valid simulation modes that will exercise several things:
        # If 0 is present it is the default,
        # otherwise the first value is the default.
        # If 0 is present and there are two values then --simulate is a flag,
        # otherwise --simulate requires a value
        self.valid_simulation_modes_list = (
            # (0, 1),
            # (1, 0),
            # (0, 3),
            # (3, 0),
            (1, 2),
            (0, 1, 4),
            (4, 1, 0),
        )

    def make_csc_class(self, modes):
        """Make a subclass of TestCsc with specified valid simulation modes
        """

        class TestCscWithSimulation(salobj.TestCsc):
            valid_simulation_modes = modes

        return TestCscWithSimulation

    async def test_invalid_simulation_modes(self):
        index = next(index_gen)
        for valid_simulation_modes in self.valid_simulation_modes_list:
            csc_class = self.make_csc_class(valid_simulation_modes)
            for bad_simulation_mode in range(-1, 5):
                if bad_simulation_mode in csc_class.valid_simulation_modes:
                    continue
                with self.assertRaises(ValueError):
                    csc_class(index=index, simulation_mode=bad_simulation_mode)

    async def test_valid_simulation_modes(self):
        for valid_simulation_modes in self.valid_simulation_modes_list:
            csc_class = self.make_csc_class(valid_simulation_modes)
            for simulation_mode in csc_class.valid_simulation_modes:
                index = next(index_gen)
                async with csc_class(
                    index=index, simulation_mode=simulation_mode
                ) as csc:
                    self.assertEqual(csc.simulation_mode, simulation_mode)

    async def test_simulate_cmdline_arg(self):
        orig_argv = sys.argv[:]
        try:
            for valid_simulation_modes in self.valid_simulation_modes_list:
                print(f"valid_simulation_modes={valid_simulation_modes}")
                if 0 in valid_simulation_modes:
                    default_simulation_mode = 0
                else:
                    default_simulation_mode = valid_simulation_modes[0]

                index = next(index_gen)
                csc_class = self.make_csc_class(valid_simulation_modes)
                if len(valid_simulation_modes) != 2 or 0 not in valid_simulation_modes:
                    # This should fail with no value
                    sys.argv = [
                        "test_csc.py",  # irrelevant
                        str(index),
                        "--simulate",
                    ]
                    with self.assertRaises(SystemExit):
                        csc_class.make_from_cmd_line(index=True)

                    # Test invalid simulation modes
                    for bad_simulation_mode in range(-1, 5):
                        if bad_simulation_mode in valid_simulation_modes:
                            continue
                        sys.argv = [
                            "test_csc.py",  # irrelevant
                            str(index),
                            "--simulate",
                            str(bad_simulation_mode),
                        ]
                        with self.assertRaises(SystemExit):
                            csc_class.make_from_cmd_line(index=True)

                    # Test valid simulation modes
                    for good_simulation_mode in valid_simulation_modes:
                        sys.argv = [
                            "test_csc.py",  # irrelevant
                            str(index),
                            "--simulate",
                            str(good_simulation_mode),
                        ]
                        csc = csc_class.make_from_cmd_line(index=True)
                        try:
                            # The simulation mode isn't assigned
                            # until the CSC starts.
                            await csc.start_task
                            self.assertEqual(csc.simulation_mode, good_simulation_mode)
                        finally:
                            await csc.do_exitControl(data=None)
                            await asyncio.wait_for(csc.done_task, timeout=5)

                else:
                    # This should fail with any value, valid or not
                    for simulation_mode in (0, 1):
                        sys.argv = [
                            "test_csc.py",  # irrelevant
                            str(index),
                            "--simulate",
                            str(simulation_mode),
                        ]
                        with self.assertRaises(SystemExit):
                            csc_class.make_from_cmd_line(index=True)

                    if valid_simulation_modes[0] == 0:
                        nondefault_simulation_mode = valid_simulation_modes[1]
                    else:
                        nondefault_simulation_mode = valid_simulation_modes[0]

                    index = next(index_gen)
                    sys.argv = [
                        "test_csc.py",  # irrelevant
                        str(index),
                        "--simulate",
                    ]
                    csc = csc_class.make_from_cmd_line(index=True)
                    try:
                        # The simulation mode isn't assigned
                        # until the CSC starts.
                        await csc.start_task
                        self.assertEqual(
                            csc.simulation_mode, nondefault_simulation_mode
                        )
                    finally:
                        await csc.do_exitControl(data=None)
                        await asyncio.wait_for(csc.done_task, timeout=5)

                # In all cases no --simulate arg should give the default.
                index = next(index_gen)
                sys.argv = [
                    "test_csc.py",  # irrelevant
                    str(index),
                ]
                csc = csc_class.make_from_cmd_line(index=True)
                try:
                    # The simulation mode isn't assigned until the CSC starts
                    await csc.start_task
                    self.assertEqual(csc.simulation_mode, default_simulation_mode)
                finally:
                    await csc.do_exitControl(data=None)
                    await asyncio.wait_for(csc.done_task, timeout=5)

        finally:
            sys.argv[:] = orig_argv

    async def test_none_valid_simulation_modes_simulation_mode(self):
        """Test that a CSC that uses the deprecated valid_simulation_modes=None
        checks simulation mode in start, not the constructor.

        The only valid simulation_mode is 0 because that's what BaseCsc
        supports and I didn't override that support.
        """
        TestCscWithDeprecatedSimulation = self.make_csc_class(None)

        self.assertEqual(TestCscWithDeprecatedSimulation.valid_simulation_modes, None)

        for bad_simulation_mode in (1, 2):
            index = next(index_gen)
            with self.assertWarns(DeprecationWarning):
                csc = TestCscWithDeprecatedSimulation(
                    index=index, simulation_mode=bad_simulation_mode
                )
            with self.assertRaises(salobj.base.ExpectedError):
                await csc.start_task

        # Test the one valid simulation mode
        index = next(index_gen)
        with self.assertWarns(DeprecationWarning):
            csc = TestCscWithDeprecatedSimulation(index=index, simulation_mode=0)
        try:
            await csc.start_task
            self.assertEqual(csc.simulation_mode, 0)
        finally:
            await csc.do_exitControl(data=None)
            await asyncio.wait_for(csc.done_task, timeout=5)

    async def test_none_valid_simulation_modes_cmdline(self):
        """Test that when valid_simulation_modes=None that the command
        parser does not add the --simulate argument.
        """
        TestCscWithDeprecatedSimulation = self.make_csc_class(None)

        self.assertEqual(TestCscWithDeprecatedSimulation.valid_simulation_modes, None)

        orig_argv = sys.argv[:]
        try:
            index = next(index_gen)
            # Try 0, the only valid value. This will still fail
            # because there is no --simulate command-line argument.
            simulation_mode = 0
            sys.argv = ["test_csc.py", str(index), "--simulate", str(simulation_mode)]
            with self.assertRaises(SystemExit):
                TestCscWithDeprecatedSimulation.make_from_cmd_line(index=True)
        finally:
            sys.argv[:] = orig_argv


class ConfigurationTestCase(salobj.BaseCscTestCase, asynctest.TestCase):
    def setUp(self):
        # defaults hard-coded in <ts_salobj_root>/schema/Test.yaml
        self.default_dict = dict(
            string0="default value for string0",
            bool0=True,
            int0=5,
            float0=3.14,
            intarr0=[-1, 1],
        )
        self.config_fields = self.default_dict.keys()

    def basic_make_csc(self, initial_state, config_dir, simulation_mode):
        return salobj.TestCsc(
            self.next_index(),
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def check_settings_events(self, config_file):
        """Check the settingsApplied and appliedSettingsMatchStart events.

        Parameters
        ----------
        config_file : `str`
            The name of the config file, or "" if none specified.
        """
        # settingsVersion.settingsApplied should start with
        # the config file name followed by a colon
        data = await self.assert_next_sample(topic=self.remote.evt_settingsApplied,)
        desired_prefix = config_file + ":"
        self.assertEqual(data.settingsVersion[: len(desired_prefix)], desired_prefix)

        # appliedSettingsMatchStartIsTrue.appliedSettingsMatchStartIsTrue
        # should be True after being configured.
        await self.assert_next_sample(
            topic=self.remote.evt_appliedSettingsMatchStart,
            appliedSettingsMatchStartIsTrue=True,
        )

    async def test_no_config_specified(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)

            expected_settings_url = pathlib.Path(TEST_CONFIG_DIR).resolve().as_uri()
            expected_settings_labels = ",".join(
                (
                    "all_fields",
                    "empty",
                    "some_fields",
                    "long_label1_in_an_attempt_to_make_recommendedSettingsLabels_go_over_256_chars",
                    "long_label2_in_an_attempt_to_make_recommendedSettingsLabels_go_over_256_chars",
                    "long_label3_in_an_attempt_to_make_recommendedSettingsLabels_go_over_256_chars",
                    "long_label4_in_an_attempt_to_make_recommendedSettingsLabels_go_over_256_chars",
                    "long_label5_in_an_attempt_to_make_recommendedSettingsLabels_go_over_256_chars",
                )
            )
            data = await self.assert_next_sample(
                topic=self.remote.evt_settingVersions,
                settingsUrl=expected_settings_url,
                recommendedSettingsLabels=expected_settings_labels,
            )
            self.assertTrue(len(data.recommendedSettingsVersion) > 0)
            await self.remote.cmd_start.start(timeout=STD_TIMEOUT)
            await self.assert_next_summary_state(salobj.State.DISABLED)
            config = self.csc.config
            for key, expected_value in self.default_dict.items():
                self.assertEqual(getattr(config, key), expected_value)

            # Test the softwareVersions event.
            kwargs = dict()
            if self.remote.salinfo.metadata.xml_version is not None:
                kwargs["xmlVersion"] = self.remote.salinfo.metadata.xml_version
            if self.remote.salinfo.metadata.sal_version is not None:
                kwargs["salVersion"] = self.remote.salinfo.metadata.sal_version
            await self.assert_next_sample(
                topic=self.remote.evt_softwareVersions, **kwargs
            )

            await self.check_settings_events("")

    async def test_default_config_dir(self):
        async with self.make_csc(initial_state=salobj.State.STANDBY, config_dir=None):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            data = await self.remote.evt_settingVersions.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertTrue(len(data.recommendedSettingsVersion) > 0)
            self.assertEqual(data.settingsUrl[0:8], "file:///")
            config_path = pathlib.Path(data.settingsUrl[7:])
            self.assertTrue(config_path.samefile(self.csc.config_dir))

    async def test_empty_label(self):
        config_name = "empty"

        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start(
                settingsToApply=config_name, timeout=STD_TIMEOUT
            )
            await self.assert_next_summary_state(salobj.State.DISABLED)
            config = self.csc.config
            for key, expected_value in self.default_dict.items():
                self.assertEqual(getattr(config, key), expected_value)

            await self.check_settings_events("empty.yaml")

    async def test_some_fields_label(self):
        """Test a config with some fields set to valid values."""
        config_label = "some_fields"
        config_file = "some_fields.yaml"

        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start(
                settingsToApply=config_label, timeout=STD_TIMEOUT
            )
            await self.assert_next_summary_state(salobj.State.DISABLED)
            config = self.csc.config
            config_path = os.path.join(self.csc.config_dir, config_file)
            with open(config_path, "r") as f:
                config_yaml = f.read()
            config_from_file = yaml.safe_load(config_yaml)
            for key, default_value in self.default_dict.items():
                if key in config_from_file:
                    self.assertEqual(getattr(config, key), config_from_file[key])
                    self.assertNotEqual(getattr(config, key), default_value)
                else:
                    self.assertEqual(getattr(config, key), default_value)

            await self.check_settings_events(config_file)

    async def test_some_fields_file_no_hash(self):
        """Test a config specified by filename."""
        config_file = "some_fields.yaml"

        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start(
                settingsToApply=config_file, timeout=STD_TIMEOUT
            )
            await self.assert_next_summary_state(salobj.State.DISABLED)
            config = self.csc.config
            config_path = os.path.join(self.csc.config_dir, config_file)
            with open(config_path, "r") as f:
                config_yaml = f.read()
            config_from_file = yaml.safe_load(config_yaml)
            for key, default_value in self.default_dict.items():
                if key in config_from_file:
                    self.assertEqual(getattr(config, key), config_from_file[key])
                    self.assertNotEqual(getattr(config, key), default_value)
                else:
                    self.assertEqual(getattr(config, key), default_value)

            await self.check_settings_events(config_file)

    async def test_some_fields_file_with_hash(self):
        """Test a config specified by filename:hash."""
        config_file = "some_fields.yaml"

        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start(
                settingsToApply=f"{config_file}:HEAD", timeout=STD_TIMEOUT
            )
            await self.assert_next_summary_state(salobj.State.DISABLED)
            config = self.csc.config
            config_path = os.path.join(self.csc.config_dir, config_file)
            with open(config_path, "r") as f:
                config_yaml = f.read()
            config_from_file = yaml.safe_load(config_yaml)
            for key, default_value in self.default_dict.items():
                if key in config_from_file:
                    self.assertEqual(getattr(config, key), config_from_file[key])
                    self.assertNotEqual(getattr(config, key), default_value)
                else:
                    self.assertEqual(getattr(config, key), default_value)

            await self.check_settings_events(config_file)

    async def test_all_fields_label(self):
        """Test a config with all fields set to valid values."""
        config_name = "all_fields"
        config_file = "all_fields.yaml"

        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            await self.remote.cmd_start.set_start(
                settingsToApply=config_name, timeout=STD_TIMEOUT
            )
            await self.assert_next_summary_state(salobj.State.DISABLED)
            config = self.csc.config
            config_path = os.path.join(self.csc.config_dir, config_file)
            with open(config_path, "r") as f:
                config_yaml = f.read()
            config_from_file = yaml.safe_load(config_yaml)
            for key in self.config_fields:
                self.assertEqual(getattr(config, key), config_from_file[key])

            await self.check_settings_events(config_file)

    async def test_invalid_configs(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.STANDBY)
            for name in ("all_bad_types", "bad_format", "one_bad_type", "extra_field"):
                config_file = f"invalid_{name}.yaml"
                with self.subTest(config_file=config_file):
                    with self.assertRaises(salobj.AckError):
                        await self.remote.cmd_start.set_start(
                            settingsToApply=config_file, timeout=STD_TIMEOUT
                        )
                    data = self.remote.evt_summaryState.get()
                    self.assertEqual(self.csc.summary_state, salobj.State.STANDBY)
                    self.assertEqual(data.summaryState, salobj.State.STANDBY)


class FailedCallbackCsc(salobj.TestCsc):
    """A CSC whose do_wait command raises a RuntimeError"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exc_msg = "do_wait raised an exception on purpose"

    async def do_wait(self, data):
        raise RuntimeError(self.exc_msg)


class ControllerCommandLoggingTestCase(salobj.BaseCscTestCase, asynctest.TestCase):
    def basic_make_csc(self, initial_state, config_dir, simulation_mode):
        return FailedCallbackCsc(
            initial_state=initial_state,
            index=self.next_index(),
            config_dir=config_dir,
            simulation_mode=simulation_mode,
        )

    async def test_logging(self):
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=TEST_CONFIG_DIR
        ):
            logLevel = await self.remote.evt_logLevel.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(logLevel.level, logging.INFO)

            # purge any existing messages
            self.remote.evt_logMessage.flush()

            info_message = "test info message"
            self.csc.log.info(info_message)
            msg = await self.remote.evt_logMessage.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(msg.message, info_message)
            self.assertEqual(msg.level, logging.INFO)
            self.assertEqual(msg.traceback, "")
            self.assertTrue(
                msg.filePath.endswith("tests/test_csc.py"),
                f"{msg.filePath} does not end with " f"'tests/test_csc.py'",
            )
            self.assertEqual(msg.functionName, "test_logging")
            self.assertGreater(msg.lineNumber, 0)
            self.assertEqual(msg.process, os.getpid())

            warn_message = "test warn message"
            self.csc.log.warning(warn_message)
            msg = await self.remote.evt_logMessage.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(msg.message, warn_message)
            self.assertEqual(msg.level, logging.WARNING)
            self.assertEqual(msg.traceback, "")

            with self.assertRaises(asyncio.TimeoutError):
                await self.remote.evt_logMessage.next(
                    flush=False, timeout=NODATA_TIMEOUT
                )

            await self.remote.cmd_setLogLevel.set_start(
                level=logging.ERROR, timeout=STD_TIMEOUT
            )

            logLevel = await self.remote.evt_logLevel.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(logLevel.level, logging.ERROR)

            info_message = "test info message"
            self.csc.log.info(info_message)
            with self.assertRaises(asyncio.TimeoutError):
                await self.remote.evt_logMessage.next(
                    flush=False, timeout=NODATA_TIMEOUT
                )

            warn_message = "test warn message"
            self.csc.log.warning(warn_message)
            with self.assertRaises(asyncio.TimeoutError):
                await self.remote.evt_logMessage.next(
                    flush=False, timeout=NODATA_TIMEOUT
                )

            with salobj.assertRaisesAckError():
                await self.remote.cmd_wait.set_start(duration=5, timeout=STD_TIMEOUT)

            msg = await self.remote.evt_logMessage.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertIn(self.csc.exc_msg, msg.traceback)
            self.assertIn("Traceback", msg.traceback)
            self.assertIn("RuntimeError", msg.traceback)
            self.assertEqual(msg.level, logging.ERROR)
            self.assertTrue(msg.filePath.endswith("topics/controller_command.py"))
            self.assertNotEqual(msg.functionName, "")
            self.assertGreater(msg.lineNumber, 0)
            self.assertEqual(msg.process, os.getpid())


class BaseCscMakeFromCmdLineTestCase(asynctest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()
        self.original_argv = sys.argv[:]

    def tearDown(self):
        sys.argv = self.original_argv

    async def test_no_index(self):
        for index in (0, None):
            with self.subTest(index=index):
                sys.argv = [sys.argv[0]]
                arg1 = "astring"
                arg2 = 2.75
                async with NoIndexCsc.make_from_cmd_line(
                    index=index, arg1=arg1, arg2=arg2
                ) as csc:
                    self.assertEqual(csc.arg1, arg1)
                    self.assertEqual(csc.arg2, arg2)
                    await csc.do_exitControl(data=None)
                    await asyncio.wait_for(csc.done_task, timeout=5)

    async def test_specified_index(self):
        sys.argv = [sys.argv[0]]
        index = next(index_gen)
        async with salobj.TestCsc.make_from_cmd_line(index=index) as csc:
            self.assertEqual(csc.salinfo.index, index)
            await csc.do_exitControl(data=None)
            await asyncio.wait_for(csc.done_task, timeout=5)

    async def test_index_from_argument_and_default_config_dir(self):
        index = next(index_gen)
        sys.argv = [sys.argv[0], str(index)]
        async with salobj.TestCsc.make_from_cmd_line(index=True) as csc:
            self.assertEqual(csc.salinfo.index, index)

            desired_config_pkg_name = "ts_config_ocs"
            desired_config_env_name = desired_config_pkg_name.upper() + "_DIR"
            desird_config_pkg_dir = os.environ[desired_config_env_name]
            desired_config_dir = pathlib.Path(desird_config_pkg_dir) / "Test/v1"
            self.assertEqual(csc.get_config_pkg(), desired_config_pkg_name)
            self.assertEqual(csc.config_dir, desired_config_dir)
            await csc.do_exitControl(data=None)
            await asyncio.wait_for(csc.done_task, timeout=5)

    async def test_config_from_argument(self):
        index = next(index_gen)
        sys.argv = [sys.argv[0], str(index), "--config", str(TEST_CONFIG_DIR)]
        async with salobj.TestCsc.make_from_cmd_line(index=True) as csc:
            self.assertEqual(csc.salinfo.index, index)
            self.assertEqual(csc.config_dir, TEST_CONFIG_DIR)
            await csc.do_exitControl(data=None)
            await asyncio.wait_for(csc.done_task, timeout=5)


if __name__ == "__main__":
    unittest.main()

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
import logging
import os
import subprocess
import unittest
import warnings

import asynctest
import yaml

from lsst.ts import salobj
from lsst.ts.idl.enums.Script import ScriptState

# Long enough to perform any reasonable operation
# including starting a CSC or loading a script (seconds)
STD_TIMEOUT = 60

index_gen = salobj.index_generator()


class NonConfigurableScript(salobj.BaseScript):
    """A script that takes no configuration.

    In other words get_schema returns None.
    """

    def __init__(self, index):
        super().__init__(index=index, descr="Non-configurable script")
        self.config = None
        self.run_called = False
        self.set_metadata_called = False

    @classmethod
    def get_schema(cls):
        return None

    async def configure(self, config):
        self.config = config

    async def run(self):
        self.run_called = True

    def set_metadata(self, metadata):
        self.set_metadata_called = True


class BaseScriptTestCase(asynctest.TestCase):
    """Test `BaseScript` using simple subclasses `TestScript` and
    `NonConfigurableScript`.
    """

    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()
        self.datadir = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
        self.index = next(index_gen)

    async def configure_and_check(
        self, script, log_level=0, pause_checkpoint="", stop_checkpoint="", **kwargs
    ):
        """Configure a script by calling ``do_configure`` and set group ID
        and check the result.

        Parameters
        ----------
        script : `ts.salobj.TestScript`
            A test script
        log_level : `int`, optional
            Log level as a `logging` level,
            or 0 to leave the script's log level unchanged.
        pause_checkpoint : `str`, optional
            Checkpoint(s) at which to pause, as a regular expression.
            "" to not pause at any checkpoint; "*" to pause at all checkpoints.
        stop_checkpoint : `str`, optional
            Checkpoint(s) at which to stop, as a regular expression.
            "" to not stop at any checkpoint; "*" to stop at all checkpoints.
        kwargs : `dict`
            A dict with one or more of the following keys:

            * ``wait_time`` (a float): how long to wait, in seconds
            * ``fail_run`` (bool): fail before waiting?
            * ``fail_cleanup`` (bool): fail in cleanup?

            If no values are specified then ``script.do_configure``
            is called with an empty string.

        Raises
        ------
        AssertionError
            If the script's ``config``, log level, or checkpoints
            do not match what was commanded.

        salobj.ExpectedError
            If ``kwargs`` includes other keywords than those
            documented above.
        """
        if kwargs:
            # strip to remove final trailing newline
            config = yaml.safe_dump(kwargs).strip()
        else:
            config = ""
        configure_data = script.cmd_configure.DataType()
        configure_data.config = config
        configure_data.logLevel = log_level
        configure_data.pauseCheckpoint = pause_checkpoint
        configure_data.stopCheckpoint = stop_checkpoint
        await script.do_configure(configure_data)
        self.assertEqual(script.config.wait_time, kwargs.get("wait_time", 0))
        self.assertEqual(script.config.fail_run, kwargs.get("fail_run", False))
        self.assertEqual(script.config.fail_cleanup, kwargs.get("fail_cleanup", False))
        if log_level != 0:
            self.assertEqual(script.log.getEffectiveLevel(), log_level)
        self.assertEqual(script.evt_checkpoints.data.pause, pause_checkpoint)
        self.assertEqual(script.evt_checkpoints.data.stop, stop_checkpoint)
        self.assertEqual(script.state.state, ScriptState.CONFIGURED)

        # Cannot run: groupId is not set.
        self.assertEqual(script.group_id, "")
        run_data = script.cmd_run.DataType()
        with self.assertRaises(salobj.ExpectedError):
            await script.do_run(run_data)

        # Set and check group ID.
        group_id = "arbitrary group ID"
        group_id_data = script.cmd_setGroupId.DataType()
        group_id_data.groupId = group_id
        await script.do_setGroupId(group_id_data)
        self.assertEqual(script.group_id, group_id)
        self.assertEqual(script.evt_state.data.groupId, group_id)

    def test_get_schema(self):
        schema = salobj.TestScript.get_schema()
        self.assertTrue(isinstance(schema, dict))
        for name in ("$schema", "$id", "title", "description", "type", "properties"):
            self.assertIn(name, schema)
        self.assertFalse(schema["additionalProperties"])

    def test_non_configurable_script_get_schema(self):
        schema = NonConfigurableScript.get_schema()
        self.assertIsNone(schema)

    async def test_non_configurable_script_empty_config(self):
        """Test configuring the script with no data. This should work.

        Also test that creating the script sets the master priority
        environment variable to "0".
        """
        async with NonConfigurableScript(index=self.index) as script:
            self.assertEqual(os.environ[salobj.MASTER_PRIORITY_ENV_VAR], "0")
            data = script.cmd_configure.DataType()
            await script.do_configure(data)
            self.assertEqual(len(script.config.__dict__), 0)
            self.assertTrue(script.set_metadata_called)
            self.assertFalse(script.run_called)

    async def test_non_configurable_script_invalid_config(self):
        async with NonConfigurableScript(index=self.index) as script:
            data = script.cmd_configure.DataType()
            data.config = "invalid: should be empty"
            with self.assertRaises(salobj.ExpectedError):
                await script.do_configure(data)
            self.assertIsNone(script.config)

    async def test_setCheckpoints(self):
        async with salobj.TestScript(index=self.index) as script:

            # try valid values
            data = script.cmd_setCheckpoints.DataType()
            for pause, stop in (
                ("something", ""),
                ("", "something_else"),
                (".*", "start|end"),
            ):
                data.pause = pause
                data.stop = stop
                await script.do_setCheckpoints(data)
                self.assertEqual(script.checkpoints.pause, pause)
                self.assertEqual(script.checkpoints.stop, stop)

            # try with at least one checkpoint not a valid regex;
            # do_setCheckpoints should raise and not change the checkpoints
            initial_pause = "initial_pause"
            initial_stop = "initial_stop"
            data.pause = initial_pause
            data.stop = initial_stop
            await script.do_setCheckpoints(data)
            for bad_pause, bad_stop in (("(", ""), ("", "("), ("[", "[")):
                data.pause = bad_pause
                data.stop = bad_stop
                with self.assertRaises(salobj.ExpectedError):
                    await script.do_setCheckpoints(data)
                self.assertEqual(script.checkpoints.pause, initial_pause)
                self.assertEqual(script.checkpoints.stop, initial_stop)

    async def test_set_state_and_attributes(self):
        async with salobj.TestScript(index=self.index) as script:
            # check keep_old_reason argument of set_state
            reason = "initial reason"
            additional_reason = "check append"
            script.set_state(reason=reason)
            script.set_state(reason=additional_reason, keep_old_reason=True)
            self.assertEqual(script.state.reason, reason + "; " + additional_reason)

            bad_state = 1 + max(s.value for s in ScriptState)
            with self.assertRaises(ValueError):
                script.set_state(bad_state)
            script.state.state = bad_state
            self.assertEqual(script.state_name, f"UNKNOWN({bad_state})")
            self.assertFalse(script._is_exiting)

            script.set_state(ScriptState.CONFIGURED)
            self.assertEqual(script.state_name, "CONFIGURED")

            # check assert_states
            all_states = set(ScriptState)
            for state in ScriptState:
                script.set_state(state)
                self.assertEqual(script.state_name, state.name)
                with self.assertRaises(salobj.ExpectedError):
                    script.assert_state(
                        "should fail because state not in allowed states",
                        all_states - set([state]),
                    )

                script.assert_state("should pass", [state])
                script._is_exiting = True
                with self.assertRaises(salobj.ExpectedError):
                    script.assert_state("should fail because exiting", [state])
                script._is_exiting = False

                # check that checkpoint is prohibited
                # unless state is RUNNING
                if state == ScriptState.RUNNING:
                    continue
                with self.assertRaises(RuntimeError):
                    await script.checkpoint("foo")

            self.assertFalse(script.done_task.done())

    async def test_next_supplemented_group_id(self):
        async with salobj.TestScript(index=self.index) as script:
            await self.configure_and_check(script)
            group_id = script.group_id
            for i in range(5):
                # Format some other way than an f-string,
                # in order to have a different implementation than Script
                desired_supplemented_id = "%s#%s" % (group_id, i + 1)
                supplemented_id = script.next_supplemented_group_id()
                self.assertEqual(supplemented_id, desired_supplemented_id)

            # Set a new group ID. This should reset the subgroup counter.
            new_group_id = group_id + " modified"
            group_id_data = script.cmd_setGroupId.DataType()
            group_id_data.groupId = new_group_id
            await script.do_setGroupId(group_id_data)

            for i in range(5):
                desired_supplemented_id = "%s#%s" % (new_group_id, i + 1)
                supplemented_id = script.next_supplemented_group_id()
                self.assertEqual(supplemented_id, desired_supplemented_id)

            # Clear the group ID; getting a supplemened group ID should fail
            group_id_data = script.cmd_setGroupId.DataType()
            group_id_data.groupId = ""
            await script.do_setGroupId(group_id_data)
            with self.assertRaises(RuntimeError):
                script.next_supplemented_group_id()

    async def test_pause(self):
        async with salobj.TestScript(index=self.index) as script:
            # Cannot run in UNCONFIGURED state.
            run_data = script.cmd_run.DataType()
            with self.assertRaises(salobj.ExpectedError):
                await script.do_run(run_data)

            # Test configure with data for a non-existent argument.
            configure_data = script.cmd_configure.DataType()
            configure_data.config = "no_such_arg: 1"
            with self.assertRaises(salobj.ExpectedError):
                await script.do_configure(configure_data)
            self.assertEqual(script.state.state, ScriptState.UNCONFIGURED)

            # Test configure with invalid yaml.
            configure_data = script.cmd_configure.DataType()
            configure_data.config = "a : : 2"
            with self.assertRaises(salobj.ExpectedError):
                await script.do_configure(configure_data)
            self.assertEqual(script.state.state, ScriptState.UNCONFIGURED)

            # Test configure with yaml that makes a string, not a dict.
            configure_data = script.cmd_configure.DataType()
            configure_data.config = "just_a_string"
            with self.assertRaises(salobj.ExpectedError):
                await script.do_configure(configure_data)
            self.assertEqual(script.state.state, ScriptState.UNCONFIGURED)

            # Test configure with yaml that makes a list, not a dict.
            configure_data = script.cmd_configure.DataType()
            configure_data.config = "['not', 'a', 'dict']"
            with self.assertRaises(salobj.ExpectedError):
                await script.do_configure(configure_data)
            self.assertEqual(script.state.state, ScriptState.UNCONFIGURED)

            # Now test valid configuration; specify nonexistent checkpoints
            # to test that the configure command handles checkpoints at all.
            wait_time = 0.5
            # Specify a log level that is not the default (which is INFO)
            # and is only slightly more verbose than INFO.
            log_level = logging.INFO - 1
            prelim_pause_checkpoint = "preliminary nonexistent pause checkpoint"
            prelim_stop_checkpoint = "preliminary nonexistent stop checkpoint"
            await self.configure_and_check(
                script,
                wait_time=wait_time,
                log_level=log_level,
                pause_checkpoint=prelim_pause_checkpoint,
                stop_checkpoint=prelim_stop_checkpoint,
            )

            # Set a pause checkpoint that exists.
            setCheckpoints_data = script.cmd_setCheckpoints.DataType()
            checkpoint_named_start = "start"
            checkpoint_that_does_not_exist = "nonexistent checkpoint"
            setCheckpoints_data.pause = checkpoint_named_start
            setCheckpoints_data.stop = checkpoint_that_does_not_exist
            await script.do_setCheckpoints(setCheckpoints_data)
            self.assertEqual(script.checkpoints.pause, checkpoint_named_start)
            self.assertEqual(script.checkpoints.stop, checkpoint_that_does_not_exist)

            # Run the script.
            run_data = script.cmd_run.DataType()
            run_task = asyncio.create_task(script.do_run(run_data))
            niter = 0
            while script.state.state != ScriptState.PAUSED:
                niter += 1
                await asyncio.sleep(0)
            self.assertEqual(script.state.lastCheckpoint, checkpoint_named_start)
            self.assertEqual(script.checkpoints.pause, checkpoint_named_start)
            self.assertEqual(script.checkpoints.stop, checkpoint_that_does_not_exist)
            resume_data = script.cmd_resume.DataType()
            await script.do_resume(resume_data)
            await asyncio.wait_for(run_task, 2)
            await asyncio.wait_for(script.done_task, timeout=STD_TIMEOUT)
            duration = (
                script.timestamps[ScriptState.ENDING]
                - script.timestamps[ScriptState.RUNNING]
            )
            desired_duration = wait_time
            print(f"test_pause duration={duration:0.2f}")
            self.assertLess(abs(duration - desired_duration), 0.2)

    async def test_stop_at_checkpoint(self):
        async with salobj.TestScript(index=self.index) as script:
            wait_time = 0.1
            await self.configure_and_check(script, wait_time=wait_time)

            # set a stop checkpoint
            setCheckpoints_data = script.cmd_setCheckpoints.DataType()
            checkpoint_named_end = "end"
            setCheckpoints_data.stop = checkpoint_named_end
            await script.do_setCheckpoints(setCheckpoints_data)
            self.assertEqual(script.checkpoints.pause, "")
            self.assertEqual(script.checkpoints.stop, checkpoint_named_end)

            run_data = script.cmd_run.DataType()
            await asyncio.wait_for(script.do_run(run_data), 2)
            await asyncio.wait_for(script.done_task, timeout=STD_TIMEOUT)
            self.assertEqual(script.state.lastCheckpoint, checkpoint_named_end)
            self.assertEqual(script.state.state, ScriptState.STOPPED)
            duration = (
                script.timestamps[ScriptState.STOPPING]
                - script.timestamps[ScriptState.RUNNING]
            )
            # waited and then stopped at the "end" checkpoint
            desired_duration = wait_time
            print(f"test_stop_at_checkpoint duration={duration:0.2f}")
            self.assertLess(abs(duration - desired_duration), 0.2)

    async def test_stop_while_paused(self):
        async with salobj.TestScript(index=self.index) as script:
            wait_time = 5
            await self.configure_and_check(script, wait_time=wait_time)

            # set a stop checkpoint
            setCheckpoints_data = script.cmd_setCheckpoints.DataType()
            checkpoint_named_start = "start"
            setCheckpoints_data.pause = checkpoint_named_start
            await script.do_setCheckpoints(setCheckpoints_data)
            self.assertEqual(script.checkpoints.pause, checkpoint_named_start)
            self.assertEqual(script.checkpoints.stop, "")

            run_data = script.cmd_run.DataType()
            asyncio.create_task(script.do_run(run_data))
            while script.state.lastCheckpoint != "start":
                await asyncio.sleep(0)
            self.assertEqual(script.state.state, ScriptState.PAUSED)
            stop_data = script.cmd_stop.DataType()
            await script.do_stop(stop_data)
            await asyncio.wait_for(script.done_task, timeout=STD_TIMEOUT)
            self.assertEqual(script.state.lastCheckpoint, checkpoint_named_start)
            self.assertEqual(script.state.state, ScriptState.STOPPED)
            duration = (
                script.timestamps[ScriptState.STOPPING]
                - script.timestamps[ScriptState.RUNNING]
            )
            # the script ran quickly because we stopped the script
            # just as soon as it paused at the "start" checkpoint
            desired_duration = 0
            print(f"test_stop_while_paused duration={duration:0.2f}")
            self.assertGreater(duration, 0.0)
            self.assertLess(abs(duration - desired_duration), 0.2)

    async def test_stop_while_running(self):
        async with salobj.TestScript(index=self.index) as script:
            wait_time = 5
            pause_time = 0.5
            await self.configure_and_check(script, wait_time=wait_time)

            checkpoint_named_start = "start"
            run_data = script.cmd_run.DataType()
            asyncio.create_task(script.do_run(run_data))
            while script.state.lastCheckpoint != checkpoint_named_start:
                await asyncio.sleep(0)
            self.assertEqual(script.state.state, ScriptState.RUNNING)
            await asyncio.sleep(pause_time)
            stop_data = script.cmd_stop.DataType()
            await script.do_stop(stop_data)
            await asyncio.wait_for(script.done_task, timeout=STD_TIMEOUT)
            self.assertEqual(script.state.lastCheckpoint, checkpoint_named_start)
            self.assertEqual(script.state.state, ScriptState.STOPPED)
            duration = (
                script.timestamps[ScriptState.STOPPING]
                - script.timestamps[ScriptState.RUNNING]
            )
            # we waited `pause_time` seconds after the "start" checkpoint
            desired_duration = pause_time
            print(f"test_stop_while_running duration={duration:0.2f}")
            self.assertLess(abs(duration - desired_duration), 0.2)

    async def check_fail(self, fail_run):
        """Check failure in run or cleanup.

        Parameters
        ----------
        fail_run : `bool`
            If True then fail in the script's ``run`` method,
            else fail in the script's ``cleanup`` method.
        """
        wait_time = 0.1
        async with salobj.TestScript(index=self.index) as script:
            if fail_run:
                await self.configure_and_check(script, fail_run=True)
            else:
                await self.configure_and_check(script, fail_cleanup=True)

            run_data = script.cmd_run.DataType()
            await asyncio.wait_for(script.do_run(run_data), 2)
            if fail_run:
                await asyncio.wait_for(script.done_task, timeout=STD_TIMEOUT)
                self.assertEqual(script.state.lastCheckpoint, "start")
                self.assertEqual(script.state.state, ScriptState.FAILED)
                end_run_state = ScriptState.FAILING
            else:
                with self.assertRaises(salobj.ExpectedError):
                    await asyncio.wait_for(script.done_task, timeout=STD_TIMEOUT)
                self.assertEqual(script.state.lastCheckpoint, "end")
                end_run_state = ScriptState.ENDING
            duration = (
                script.timestamps[end_run_state]
                - script.timestamps[ScriptState.RUNNING]
            )
            # if fail_run then failed before waiting,
            # otherwise failed after
            desired_duration = 0 if fail_run else wait_time
            print(f"test_fail duration={duration:0.3f} with fail_run={fail_run}")
            self.assertLess(abs(duration - desired_duration), 0.2)

    async def test_fail_run(self):
        await self.check_fail(fail_run=True)

    async def test_fail_cleanup(self):
        await self.check_fail(fail_run=False)

    async def test_zero_index(self):
        with self.assertRaises(ValueError):
            salobj.TestScript(index=0)

    async def test_remote(self):
        """Test a script with remotes.

        Check that the remote_names attribute of the description event
        is properly set, and that the remotes have started when the
        script has started.
        """

        class ScriptWithRemotes(salobj.TestScript):
            def __init__(self, index, remote_indices):
                super().__init__(index, descr="Script with remotes")
                remotes = []
                # use remotes that read history here, to check that
                # script.start_task waits for the start_task in each remote.
                for rind in remote_indices:
                    remotes.append(
                        salobj.Remote(domain=self.domain, name="Test", index=rind)
                    )
                self.remotes = remotes

        remote_indices = [5, 7]
        async with ScriptWithRemotes(self.index, remote_indices) as script:
            remote_name_list = [f"Test:{ind}" for ind in remote_indices]
            desired_remote_names = ",".join(sorted(remote_name_list))
            self.assertEqual(script.evt_description.data.remotes, desired_remote_names)
            for remote in script.remotes:
                self.assertTrue(remote.start_task.done())

    async def test_script_process(self):
        """Test running a script as a subprocess.
        """
        script_path = os.path.join(self.datadir, "script1")

        for fail in (None, "fail_run", "fail_cleanup"):
            with self.subTest(fail=fail):
                async with salobj.Domain() as domain:
                    index = next(index_gen)
                    remote = salobj.Remote(
                        domain=domain, name="Script", index=index, evt_max_history=0,
                    )
                    await asyncio.wait_for(remote.start_task, timeout=STD_TIMEOUT)

                    def logcallback(data):
                        print(f"message={data.message}")

                    remote.evt_logMessage.callback = logcallback

                    process = await asyncio.create_subprocess_exec(
                        script_path, str(index)
                    )
                    try:
                        self.assertIsNone(process.returncode)

                        state = await remote.evt_state.next(
                            flush=False, timeout=STD_TIMEOUT
                        )
                        self.assertEqual(state.state, ScriptState.UNCONFIGURED)
                        self.assertEqual(state.groupId, "")

                        logLevel_data = await remote.evt_logLevel.next(
                            flush=False, timeout=STD_TIMEOUT
                        )
                        self.assertEqual(logLevel_data.level, logging.INFO)

                        wait_time = 0.1
                        config = f"wait_time: {wait_time}"
                        if fail:
                            config = config + f"\n{fail}: True"
                        await remote.cmd_configure.set_start(
                            config=config, timeout=STD_TIMEOUT
                        )
                        state = await remote.evt_state.next(
                            flush=False, timeout=STD_TIMEOUT
                        )
                        self.assertEqual(state.state, ScriptState.CONFIGURED)
                        self.assertEqual(state.groupId, "")

                        metadata = await remote.evt_metadata.next(
                            flush=False, timeout=STD_TIMEOUT
                        )
                        self.assertEqual(metadata.duration, wait_time)

                        group_id = "a non-blank group ID"
                        await remote.cmd_setGroupId.set_start(
                            groupId=group_id, timeout=STD_TIMEOUT
                        )
                        state = await remote.evt_state.next(
                            flush=False, timeout=STD_TIMEOUT
                        )
                        self.assertEqual(state.groupId, group_id)

                        await remote.cmd_run.start(timeout=STD_TIMEOUT)

                        await asyncio.wait_for(process.wait(), timeout=STD_TIMEOUT)
                        if fail:
                            self.assertEqual(process.returncode, 1)
                        else:
                            self.assertEqual(process.returncode, 0)
                    finally:
                        if process.returncode is None:
                            process.terminate()
                            warnings.warn(
                                "Killed a process that was not properly terminated"
                            )

    async def test_script_schema_process(self):
        """Test running a script with --schema as a subprocess.
        """
        script_path = os.path.join(self.datadir, "script1")
        index = 1  # index is ignored
        process = await asyncio.create_subprocess_exec(
            script_path,
            str(index),
            "--schema",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=STD_TIMEOUT
            )
            schema = yaml.safe_load(stdout)
            self.assertEqual(schema, salobj.TestScript.get_schema())
            await asyncio.wait_for(process.wait(), timeout=STD_TIMEOUT)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.returncode is None:
                process.terminate()
                warnings.warn("Killed a process that was not properly terminated")


if __name__ == "__main__":
    unittest.main()

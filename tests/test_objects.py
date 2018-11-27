import asyncio
import logging
import sys
import time
import unittest

import numpy as np

try:
    import SALPY_Test
except ImportError:
    SALPY_Test = None
import lsst.ts.salobj as salobj

np.random.seed(47)

index_gen = salobj.index_generator()


class Harness:
    def __init__(self, initial_state):
        index = next(index_gen)
        salobj.test_utils.set_random_lsst_dds_domain()
        self.csc = salobj.test_utils.TestCsc(index=index, initial_state=initial_state)
        self.remote = salobj.Remote(SALPY_Test, index)


@unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
class CommunicateTestCase(unittest.TestCase):
    def test_heartbeat(self):
        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            start_time = time.time()
            await harness.remote.evt_heartbeat.next(timeout=2)
            await harness.remote.evt_heartbeat.next(timeout=2)
            duration = time.time() - start_time
            self.assertLess(abs(duration - 2), 0.5)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_main(self):
        async def doit():
            index = next(index_gen)
            salobj.test_utils.set_random_lsst_dds_domain()
            process = await asyncio.create_subprocess_exec("run_test_csc.py", str(index))
            try:
                remote = salobj.Remote(SALPY_Test, index)
                summaryState_data = await remote.evt_summaryState.next(flush=False, timeout=10)
                self.assertEqual(summaryState_data.summaryState, salobj.State.STANDBY)

                id_ack = await remote.cmd_exitControl.start(remote.cmd_exitControl.DataType(), timeout=2)
                self.assertEqual(id_ack.ack.ack, remote.salinfo.lib.SAL__CMD_COMPLETE)
                summaryState_data = await remote.evt_summaryState.next(flush=False, timeout=10)
                self.assertEqual(summaryState_data.summaryState, salobj.State.OFFLINE)

                await asyncio.wait_for(process.wait(), 2)
            except Exception:
                if process.returncode is None:
                    process.terminate()
                raise

        asyncio.get_event_loop().run_until_complete(doit())

    def test_setArrays_command(self):
        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            # until the controller gets its first setArrays
            # it will not send any arrays events or telemetry
            self.assertIsNone(harness.remote.evt_arrays.get())
            self.assertIsNone(harness.remote.tel_arrays.get())

            # send the setArrays command with random data
            cmd_data_sent = harness.csc.make_random_cmd_arrays()
            await harness.remote.cmd_setArrays.start(cmd_data_sent, timeout=1)

            # by default log level does not include INFO messages, so expect nothing
            log_message = harness.remote.evt_logMessage.get()
            self.assertIsNone(log_message)

            # see if new data was broadcast correctly
            evt_data = await harness.remote.evt_arrays.next(flush=False, timeout=1)
            harness.csc.assert_arrays_equal(cmd_data_sent, evt_data)
            tel_data = await harness.remote.tel_arrays.next(flush=False, timeout=1)
            harness.csc.assert_arrays_equal(cmd_data_sent, tel_data)

            # also test get
            harness.csc.assert_arrays_equal(cmd_data_sent, harness.remote.tel_arrays.get())
            harness.csc.assert_arrays_equal(cmd_data_sent, harness.remote.evt_arrays.get())

        asyncio.get_event_loop().run_until_complete(doit())

    def test_setScalars_command(self):
        async def doit():
            harness = Harness(initial_state=salobj.State.ENABLED)
            # until the controller gets its first setArrays
            # it will not send any arrays events or telemetry
            self.assertIsNone(harness.remote.evt_scalars.get())
            self.assertIsNone(harness.remote.tel_scalars.get())

            # enable info level messages
            set_logging_data = harness.remote.cmd_setLogging.DataType()
            set_logging_data.level = logging.INFO
            await harness.remote.cmd_setLogging.start(set_logging_data, timeout=2)

            # send the setScalars command with random data
            cmd_data_sent = harness.csc.make_random_cmd_scalars()
            await harness.remote.cmd_setScalars.start(cmd_data_sent, timeout=1)
            log_message = harness.remote.evt_logMessage.get()
            self.assertIsNotNone(log_message)
            self.assertEqual(log_message.level, logging.INFO)
            self.assertIn("setscalars", log_message.message.lower())

            # see if new data is being broadcast correctly
            evt_data = await harness.remote.evt_scalars.next(flush=False, timeout=1)
            harness.csc.assert_scalars_equal(cmd_data_sent, evt_data)
            tel_data = await harness.remote.tel_scalars.next(flush=False, timeout=1)
            harness.csc.assert_scalars_equal(cmd_data_sent, tel_data)

            # also test get
            harness.csc.assert_scalars_equal(cmd_data_sent, harness.remote.tel_scalars.get())
            harness.csc.assert_scalars_equal(cmd_data_sent, harness.remote.evt_scalars.get())

        asyncio.get_event_loop().run_until_complete(doit())

    async def set_and_get_scalars(self, harness, num_commands):
        # until the controller gets its first setArrays
        # it will not send any scalars events or telemetry
        self.assertIsNone(harness.remote.evt_scalars.get())
        self.assertIsNone(harness.remote.tel_scalars.get())

        # send the setScalars command with random data
        cmd_data_list = [harness.csc.make_random_cmd_scalars() for i in range(num_commands)]
        for cmd_data in cmd_data_list:
            await harness.remote.cmd_setScalars.start(cmd_data, timeout=1)
        return cmd_data_list

    def test_remote_get_oldest(self):
        async def doit():
            num_commands = 3
            harness = Harness(initial_state=salobj.State.ENABLED)
            cmd_data_list = await self.set_and_get_scalars(harness, num_commands=num_commands)

            evt_data_list = []
            while True:
                data = harness.remote.evt_scalars.get_oldest()
                if data is None:
                    break
                evt_data_list.append(data)
            self.assertEqual(len(evt_data_list), num_commands)
            for cmd_data, evt_data in zip(cmd_data_list, evt_data_list):
                harness.csc.assert_scalars_equal(cmd_data, evt_data)

            tel_data_list = []
            while True:
                data = harness.remote.tel_scalars.get_oldest()
                if data is None:
                    break
                tel_data_list.append(data)
            self.assertEqual(len(tel_data_list), num_commands)
            for cmd_data, tel_data in zip(cmd_data_list, tel_data_list):
                harness.csc.assert_scalars_equal(cmd_data, tel_data)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_remote_get(self):
        async def doit():
            num_commands = 3
            harness = Harness(initial_state=salobj.State.ENABLED)
            cmd_data_list = await self.set_and_get_scalars(harness, num_commands=num_commands)

            # get should return the last value seen,
            # no matter now many times it is called
            evt_data_list = [harness.remote.evt_scalars.get() for i in range(5)]
            for evt_data in evt_data_list:
                self.assertIsNotNone(evt_data)
                harness.csc.assert_scalars_equal(cmd_data_list[-1], evt_data)

            # get should return the last value seen,
            # no matter now many times it is called
            tel_data_list = [harness.remote.tel_scalars.get() for i in range(5)]
            for tel_data in tel_data_list:
                self.assertIsNotNone(tel_data)
                harness.csc.assert_scalars_equal(cmd_data_list[-1], tel_data)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_remote_next(self):
        async def doit():
            num_commands = 3
            harness = Harness(initial_state=salobj.State.ENABLED)
            cmd_data_list = await self.set_and_get_scalars(harness, num_commands=num_commands)

            evt_data_list = []
            while True:
                try:
                    evt_data = await harness.remote.evt_scalars.next(flush=False, timeout=0.01)
                    self.assertIsNotNone(evt_data)
                    evt_data_list.append(evt_data)
                except asyncio.TimeoutError:
                    break
            self.assertEqual(len(evt_data_list), num_commands)
            for cmd_data, evt_data in zip(cmd_data_list, evt_data_list):
                harness.csc.assert_scalars_equal(cmd_data, evt_data)

            tel_data_list = []
            while True:
                try:
                    tel_data = await harness.remote.tel_scalars.next(flush=False, timeout=0.01)
                    self.assertIsNotNone(tel_data)
                    tel_data_list.append(tel_data)
                except asyncio.TimeoutError:
                    break
            self.assertEqual(len(tel_data_list), num_commands)
            for cmd_data, tel_data in zip(cmd_data_list, tel_data_list):
                harness.csc.assert_scalars_equal(cmd_data, tel_data)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_remote_callbacks(self):
        async def doit():
            evt_data_list = []

            def evt_callback(data):
                evt_data_list.append(data)

            tel_data_list = []

            def tel_callback(data):
                tel_data_list.append(data)

            num_commands = 3
            harness = Harness(initial_state=salobj.State.ENABLED)
            harness.remote.evt_scalars.callback = evt_callback
            harness.remote.tel_scalars.callback = tel_callback

            with self.assertRaises(RuntimeError):
                harness.remote.evt_scalars.get_oldest()
            with self.assertRaises(RuntimeError):
                harness.remote.tel_scalars.get_oldest()
            with self.assertRaises(RuntimeError):
                harness.remote.evt_scalars.flush()
            with self.assertRaises(RuntimeError):
                harness.remote.tel_scalars.flush()
            with self.assertRaises(RuntimeError):
                await harness.remote.evt_scalars.next()
            with self.assertRaises(RuntimeError):
                await harness.remote.tel_scalars.next()

            cmd_data_list = await self.set_and_get_scalars(harness, num_commands=num_commands)
            await asyncio.sleep(0.2)  # give the wait loops time to finish

            self.assertEqual(len(evt_data_list), num_commands)
            for cmd_data, evt_data in zip(cmd_data_list, evt_data_list):
                harness.csc.assert_scalars_equal(cmd_data, evt_data)

            self.assertEqual(len(tel_data_list), num_commands)
            for cmd_data, tel_data in zip(cmd_data_list, tel_data_list):
                harness.csc.assert_scalars_equal(cmd_data, tel_data)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_bad_put(self):
        """Try to put invalid data types.
        """
        harness = Harness(initial_state=salobj.State.ENABLED)

        async def doit():
            with self.assertRaises(TypeError):
                # telemetry/event mismatch
                harness.csc.evt_scalars.put(harness.csc.tel_scalars.DataType())
            with self.assertRaises(TypeError):
                # telemetry/event mismatch
                harness.csc.tel_scalars.put(harness.csc.evt_scalars.DataType())
            with self.assertRaises(TypeError):
                await harness.remote.cmd_wait.start(harness.csc.cmd_setScalars.DataType())

        asyncio.get_event_loop().run_until_complete(doit())

    def test_command_timeout(self):
        harness = Harness(initial_state=salobj.State.ENABLED)
        sallib = harness.remote.salinfo.lib

        async def doit():
            wait_data = harness.remote.cmd_wait.DataType()
            wait_data.duration = 5
            wait_data.ack = sallib.SAL__CMD_COMPLETE
            with salobj.test_utils.assertRaisesAckError(
                    ack=harness.remote.salinfo.lib.SAL__CMD_NOACK):
                await harness.remote.cmd_wait.start(wait_data, timeout=0.5)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_controller_command_get_next(self):
        """Test ControllerCommand get and next methods.

        This requires unsetting the callback function for a command.
        """
        harness = Harness(initial_state=salobj.State.ENABLED)

        async def doit():
            # get and next fail if there is a callback
            with self.assertRaises(RuntimeError):
                harness.csc.cmd_wait.get()
            with self.assertRaises(RuntimeError):
                harness.csc.cmd_wait.next()

            harness.csc.cmd_wait.callback = None

            wait_data = harness.remote.cmd_wait.DataType()
            wait_data.duration = 1
            task1 = asyncio.ensure_future(harness.remote.cmd_wait.start(wait_data))
            await asyncio.sleep(0.5)
            get_iddata = harness.csc.cmd_wait.get()
            self.assertIsNotNone(get_iddata)
            self.assertEqual(get_iddata.data.duration, wait_data.duration)

            wait_data.duration = 2
            task2 = asyncio.ensure_future(harness.remote.cmd_wait.start(wait_data))
            next_iddata = await asyncio.wait_for(harness.csc.cmd_wait.next(), 2)
            self.assertIsNotNone(next_iddata)
            self.assertEqual(next_iddata.data.duration, wait_data.duration)

            task1.cancel()
            task2.cancel()

        asyncio.get_event_loop().run_until_complete(doit())

    def test_controller_command_callback(self):
        """Test getting and setting a callback for a ControllerCommand.
        """
        harness = Harness(initial_state=salobj.State.ENABLED)

        async def doit():
            self.assertTrue(harness.csc.cmd_wait.has_callback)
            self.assertEqual(harness.csc.cmd_wait.callback, harness.csc.do_wait)

            # replace callback
            with self.assertRaises(TypeError):
                harness.csc.cmd_wait.callback = "not callable"
            self.assertEqual(harness.csc.cmd_wait.callback, harness.csc.do_wait)

            def foo():
                pass
            harness.csc.cmd_wait.callback = foo
            self.assertEqual(harness.csc.cmd_wait.callback, foo)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_multiple_commands(self):
        """Test that we can have multiple instances of the same command
            running at the same time.
            """
        harness = Harness(initial_state=salobj.State.ENABLED)
        sallib = harness.remote.salinfo.lib
        self.assertTrue(harness.csc.cmd_wait.has_callback)
        self.assertTrue(harness.csc.cmd_wait.allow_multiple_callbacks)
        wait_data = harness.remote.cmd_wait.DataType()
        durations = (0.4, 0.3)  # seconds

        async def doit():
            futures = []
            for duration in durations:
                wait_data.duration = duration
                wait_data.ack = sallib.SAL__CMD_COMPLETE
                futures.append(harness.remote.cmd_wait.start(wait_data, timeout=5))
            results = await asyncio.gather(*futures)
            for result in results:
                self.assertEqual(result.ack.ack, sallib.SAL__CMD_COMPLETE)

        start_time = time.time()
        asyncio.get_event_loop().run_until_complete(doit())
        duration = time.time() - start_time
        self.assertLess(duration, np.sum(durations))

    def test_multiple_sequential_commands(self):
        """Test that commands prohibig multiple callbacks are executed
        one after the other.
        """
        harness = Harness(initial_state=salobj.State.ENABLED)
        sallib = harness.remote.salinfo.lib
        self.assertTrue(harness.csc.cmd_wait.has_callback)
        # make the wait commands execute sequentially
        harness.csc.cmd_wait.allow_multiple_callbacks = False
        self.assertFalse(harness.csc.cmd_wait.allow_multiple_callbacks)
        wait_data = harness.remote.cmd_wait.DataType()
        durations = (0.4, 0.3)  # seconds

        async def doit():
            futures = []
            for duration in durations:
                wait_data.duration = duration
                wait_data.ack = sallib.SAL__CMD_COMPLETE
                futures.append(harness.remote.cmd_wait.start(wait_data, timeout=5))
            results = await asyncio.gather(*futures)
            for result in results:
                self.assertEqual(result.ack.ack, sallib.SAL__CMD_COMPLETE)

        start_time = time.time()
        asyncio.get_event_loop().run_until_complete(doit())
        duration = time.time() - start_time
        self.assertGreaterEqual(duration, np.sum(durations))

    def test_asynchronous_event_callback(self):
        harness = Harness(initial_state=salobj.State.ENABLED)
        cmd_scalars_data = harness.csc.make_random_cmd_scalars()
        # just making it variable doesn't work;
        # the callback can declare it global, but setting it
        # still doesn't affect the value
        self.event_seen = False

        async def scalars_callback(scalars):
            harness.csc.assert_scalars_equal(scalars, cmd_scalars_data)
            self.event_seen = True

        async def doit():
            # send the setScalars command with random data
            # but first start looking for the event that should be triggered
            harness.remote.evt_scalars.callback = scalars_callback
            await harness.remote.cmd_setScalars.start(cmd_scalars_data, timeout=1)

        asyncio.get_event_loop().run_until_complete(doit())
        self.assertTrue(self.event_seen)

    def test_remote_command_next_ack(self):
        harness = Harness(initial_state=salobj.State.ENABLED)

        async def doit():
            wait_data = harness.remote.cmd_wait.DataType()
            wait_data.duration = 0.1
            id_ack1 = await harness.remote.cmd_wait.start(wait_data, wait_done=False, timeout=2)
            self.assertEqual(id_ack1.ack.ack, SALPY_Test.SAL__CMD_ACK)
            id_ack2 = await harness.remote.cmd_wait.next_ack(id_ack1, wait_done=False, timeout=2)
            self.assertEqual(id_ack2.ack.ack, SALPY_Test.SAL__CMD_INPROGRESS)
            id_ack3 = await harness.remote.cmd_wait.next_ack(id_ack2, wait_done=True, timeout=2)
            self.assertEqual(id_ack3.ack.ack, SALPY_Test.SAL__CMD_COMPLETE)

            # now try a timeout
            wait_data.duration = 5
            id_ack1 = await harness.remote.cmd_wait.start(wait_data, wait_done=False, timeout=2)
            self.assertEqual(id_ack1.ack.ack, SALPY_Test.SAL__CMD_ACK)
            with salobj.test_utils.assertRaisesAckError(ack=SALPY_Test.SAL__CMD_NOACK):
                await harness.remote.cmd_wait.next_ack(id_ack1, wait_done=True, timeout=0.1)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_synchronous_event_callback(self):
        harness = Harness(initial_state=salobj.State.ENABLED)
        cmd_scalars_data = harness.csc.make_random_cmd_scalars()
        self.event_seen = False

        def scalars_callback(scalars):
            harness.csc.assert_scalars_equal(scalars, cmd_scalars_data)
            self.event_seen = True

        async def doit():
            # send the setScalars command with random data
            # but first start looking for the event that should be triggered
            harness.remote.evt_scalars.callback = scalars_callback
            await harness.remote.cmd_setScalars.start(cmd_scalars_data, timeout=1)

        asyncio.get_event_loop().run_until_complete(doit())
        self.assertTrue(self.event_seen)

    def test_fault_state_transitions(self):
        """Test CSC state transitions into fault and out again.

        The initial state is STANDBY.
        The standard commands and associated state transitions are:

        * start: STANDBY to DISABLED
        * enable: DISABLED to ENABLED

        * disable: ENABLED to DISABLED
        * standby: DISABLED or FAULT to STANDBY
        * exitControl: STANDBY or FAULT to OFFLINE (quit)
        """
        async def doit():
            harness = Harness(initial_state=salobj.State.STANDBY)
            fault_data = harness.csc.cmd_fault.DataType()
            standby_data = harness.csc.cmd_standby.DataType()
            exitControl_data = harness.csc.cmd_exitControl.DataType()

            for state in salobj.State:
                if state == salobj.State.OFFLINE:
                    continue
                harness.csc._summary_state = state
                self.assertEqual(harness.csc.summary_state, state)

                # make sure we can go from any non-OFFLINE state to FAULT
                await harness.remote.cmd_fault.start(fault_data, timeout=2)
                self.assertEqual(harness.csc.summary_state, salobj.State.FAULT)
                log_message = harness.remote.evt_logMessage.get()
                self.assertIsNotNone(log_message)
                self.assertEqual(log_message.level, logging.WARNING)
                self.assertIn("fault", log_message.message.lower())

                await harness.remote.cmd_standby.start(standby_data, timeout=2)
                self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)

            # send exitControl; new state is OFFLINE
            await harness.remote.cmd_exitControl.start(exitControl_data, timeout=2)
            self.assertEqual(harness.csc.summary_state, salobj.State.OFFLINE)

            await asyncio.wait_for(harness.csc.done_task, 2)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_standard_state_transitions(self):
        """Test standard CSC state transitions.

        The initial state is STANDBY.
        The standard commands and associated state transitions are:

        * start: STANDBY to DISABLED
        * enable: DISABLED to ENABLED

        * disable: ENABLED to DISABLED
        * standby: DISABLED or FAULT to STANDBY
        * exitControl: STANDBY to OFFLINE (quit)
        """
        async def doit():
            harness = Harness(initial_state=salobj.State.STANDBY)
            commands = ("start", "enable", "disable", "exitControl", "standby",
                        "setArrays", "setScalars")
            self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)

            for bad_command in commands:
                if bad_command in ("start", "exitControl"):
                    continue  # valid command in STANDBY state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with salobj.test_utils.assertRaisesAckError(
                            ack=harness.remote.salinfo.lib.SAL__CMD_FAILED):
                        await cmd_attr.start(cmd_attr.DataType())

            # send start; new state is DISABLED
            cmd_attr = getattr(harness.remote, f"cmd_start")
            state_coro = harness.remote.evt_summaryState.next()
            id_ack = await cmd_attr.start(cmd_attr.DataType())
            state = await state_coro
            self.assertEqual(id_ack.ack.ack, harness.remote.salinfo.lib.SAL__CMD_COMPLETE)
            self.assertEqual(id_ack.ack.error, 0)
            self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)
            self.assertEqual(state.summaryState, salobj.State.DISABLED)

            for bad_command in commands:
                if bad_command in ("enable", "standby"):
                    continue  # valid command in DISABLED state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with salobj.test_utils.assertRaisesAckError(
                            ack=harness.remote.salinfo.lib.SAL__CMD_FAILED):
                        await cmd_attr.start(cmd_attr.DataType())

            # send enable; new state is ENABLED
            cmd_attr = getattr(harness.remote, f"cmd_enable")
            state_coro = harness.remote.evt_summaryState.next()
            id_ack = await cmd_attr.start(cmd_attr.DataType())
            state = await state_coro
            self.assertEqual(id_ack.ack.ack, harness.remote.salinfo.lib.SAL__CMD_COMPLETE)
            self.assertEqual(id_ack.ack.error, 0)
            self.assertEqual(harness.csc.summary_state, salobj.State.ENABLED)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)

            for bad_command in commands:
                if bad_command in ("disable", "setArrays", "setScalars"):
                    continue  # valid command in DISABLED state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with salobj.test_utils.assertRaisesAckError(
                            ack=harness.remote.salinfo.lib.SAL__CMD_FAILED):
                        await cmd_attr.start(cmd_attr.DataType())

            # send disable; new state is DISABLED
            cmd_attr = getattr(harness.remote, f"cmd_disable")
            id_ack = await cmd_attr.start(cmd_attr.DataType())
            self.assertEqual(id_ack.ack.ack, harness.remote.salinfo.lib.SAL__CMD_COMPLETE)
            self.assertEqual(id_ack.ack.error, 0)
            self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)

            # send standby; new state is STANDBY
            cmd_attr = getattr(harness.remote, f"cmd_standby")
            id_ack = await cmd_attr.start(cmd_attr.DataType())
            self.assertEqual(id_ack.ack.ack, harness.remote.salinfo.lib.SAL__CMD_COMPLETE)
            self.assertEqual(id_ack.ack.error, 0)
            self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)

            # send exitControl; new state is OFFLINE
            cmd_attr = getattr(harness.remote, f"cmd_exitControl")
            id_ack = await cmd_attr.start(cmd_attr.DataType())
            self.assertEqual(id_ack.ack.ack, harness.remote.salinfo.lib.SAL__CMD_COMPLETE)
            self.assertEqual(id_ack.ack.error, 0)
            self.assertEqual(harness.csc.summary_state, salobj.State.OFFLINE)

            await asyncio.wait_for(harness.csc.done_task, 2)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_topic_repr(self):
        harness = Harness(initial_state=salobj.State.ENABLED)
        salinfo = harness.remote.salinfo

        for obj, classSuffix in (
            (harness.csc, "Controller"),
            (harness.remote, "Remote"),
        ):
            with self.subTest(obj=obj, classSuffix=classSuffix):
                for cmd_name in salinfo.manager.getCommandNames():
                    cmd = getattr(obj, "cmd_" + cmd_name)
                    cmd_repr = repr(cmd)
                    self.assertIn(cmd_name, cmd_repr)
                    self.assertIn("Test", cmd_repr)
                    self.assertIn(classSuffix + "Command", cmd_repr)
                for evt_name in salinfo.manager.getEventNames():
                    evt = getattr(obj, "evt_" + evt_name)
                    evt_repr = repr(evt)
                    self.assertIn(evt_name, evt_repr)
                    self.assertIn("Test", evt_repr)
                    self.assertIn(classSuffix + "Event", evt_repr)
                for tel_name in salinfo.manager.getTelemetryNames():
                    tel = getattr(obj, "tel_" + tel_name)
                    tel_repr = repr(tel)
                    self.assertIn(tel_name, tel_repr)
                    self.assertIn("Test", tel_repr)
                    self.assertIn(classSuffix + "Telemetry", tel_repr)


@unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
class RemoteConstructorTestCase(unittest.TestCase):
    def test_remote_include_exclude(self):
        """Test the include and exclude arguments for salobj.Remote"""
        index = next(index_gen)
        salinfo = salobj.SalInfo(SALPY_Test, index)
        manager = salinfo.manager

        # all possible expected topic names
        all_command_topic_names = set(manager.getCommandNames())
        all_event_topic_names = set(manager.getEventNames())
        all_telemetry_topic_names = set(manager.getTelemetryNames())

        # the associated method names
        all_command_method_names = set(f"cmd_{name}" for name in all_command_topic_names)
        all_event_method_names = set(f"evt_{name}" for name in all_event_topic_names)
        all_telemetry_method_names = set(f"tel_{name}" for name in all_telemetry_topic_names)

        # remote0 specifies neither include nor exclude; it should have everything
        remote0 = salobj.Remote(SALPY_Test, index)
        remote_command_names = set([name for name in dir(remote0) if name.startswith("cmd_")])
        self.assertEqual(remote_command_names, all_command_method_names)
        remote_event_names = set([name for name in dir(remote0) if name.startswith("evt_")])
        self.assertEqual(remote_event_names, all_event_method_names)
        remote_telemetry_names = set([name for name in dir(remote0) if name.startswith("tel_")])
        self.assertEqual(remote_telemetry_names, all_telemetry_method_names)

        # remote1 uses the include argument
        include = ["errorCode", "scalars"]
        remote1 = salobj.Remote(SALPY_Test, index=index, include=include)
        remote1_command_names = set([name for name in dir(remote1) if name.startswith("cmd_")])
        self.assertEqual(remote1_command_names, all_command_method_names)
        remote1_event_names = set([name for name in dir(remote1) if name.startswith("evt_")])
        self.assertEqual(remote1_event_names, set(f"evt_{name}" for name in include
                                                  if name in all_event_topic_names))
        remote1_telemetry_names = set([name for name in dir(remote1) if name.startswith("tel_")])
        self.assertEqual(remote1_telemetry_names, set(f"tel_{name}" for name in include
                                                      if name in all_telemetry_topic_names))

        # remote2 uses the exclude argument
        exclude = ["appliedSettingsMatchStart", "arrays"]
        remote2 = salobj.Remote(SALPY_Test, index=index, exclude=exclude)
        remote2_command_names = set([name for name in dir(remote2) if name.startswith("cmd_")])
        self.assertEqual(remote2_command_names, all_command_method_names)
        remote2_event_names = set([name for name in dir(remote2) if name.startswith("evt_")])
        self.assertEqual(remote2_event_names, set(f"evt_{name}" for name in all_event_topic_names
                                                  if name not in exclude))
        remote2_telemetry_names = set([name for name in dir(remote2) if name.startswith("tel_")])
        self.assertEqual(remote2_telemetry_names, set(f"tel_{name}" for name in all_telemetry_topic_names
                                                      if name not in exclude))

        # remote3 omits commands
        remote3 = salobj.Remote(SALPY_Test, index=index, readonly=True)
        remote_command_names = set([name for name in dir(remote3) if name.startswith("cmd_")])
        self.assertEqual(remote_command_names, set())
        remote_event_names = set([name for name in dir(remote3) if name.startswith("evt_")])
        self.assertEqual(remote_event_names, all_event_method_names)
        remote_telemetry_names = set([name for name in dir(remote3) if name.startswith("tel_")])
        self.assertEqual(remote_telemetry_names, all_telemetry_method_names)

        # make sure one cannot specify both include and exclude
        with self.assertRaises(ValueError):
            salobj.Remote(SALPY_Test, index=index, include=include, exclude=exclude)


class ControllerWithDoMethods(salobj.Controller):
    """A Test controller with a trivial do_<name> method for each
    specified command name.

    Parameters
    ----------
    command_names : `iterable` of `str`
        List of command names for which to make trivial ``do_<name>``
        methods.
    """
    def __init__(self, command_names):
        def amethod(self, *args, **kwargs):
            pass

        index = next(index_gen)
        for name in command_names:
            setattr(self, f"do_{name}", amethod)
        super().__init__(SALPY_Test, index, do_callbacks=True)


@unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
class ControllerConstructorTestCase(unittest.TestCase):
    def setUp(self):
        salobj.test_utils.set_random_lsst_dds_domain()

    def test_do_callbacks_false(self):
        index = next(index_gen)
        controller = salobj.Controller(SALPY_Test, index, do_callbacks=False)
        command_names = controller.salinfo.manager.getCommandNames()
        for name in command_names:
            cmd = getattr(controller, "cmd_" + name)
            self.assertFalse(cmd.has_callback)

    def test_do_callbacks_true(self):
        index = next(index_gen)
        salinfo = salobj.SalInfo(SALPY_Test, index)
        command_names = salinfo.manager.getCommandNames()

        # make sure I can build one
        good_controller = ControllerWithDoMethods(command_names)
        for cmd_name in command_names:
            cmd = getattr(good_controller, "cmd_" + cmd_name)
            self.assertTrue(cmd.has_callback)

        for missing_name in command_names:
            if missing_name in salobj.OPTIONAL_COMMAND_NAMES:
                continue
            bad_names = [name for name in command_names if name != missing_name]
            with self.assertRaises(TypeError):
                ControllerWithDoMethods(bad_names)

        extra_names = command_names + ["extra_command"]
        with self.assertRaises(TypeError):
            ControllerWithDoMethods(extra_names)


class NoIndexCsc(salobj.test_utils.TestCsc):
    def __init__(self, arg1, arg2):
        super().__init__(index=next(index_gen))
        self.arg1 = arg1
        self.arg2 = arg2


@unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
class BaseCscMainTestCase(unittest.TestCase):
    def setUp(self):
        salobj.test_utils.set_random_lsst_dds_domain()

    def test_no_index(self):
        async def doit(index):
            arg1 = "astring"
            arg2 = 2.75
            csc = NoIndexCsc.main(index=index, arg1=arg1, arg2=arg2, run_loop=False)
            self.assertEqual(csc.arg1, arg1)
            self.assertEqual(csc.arg2, arg2)
            csc.do_exitControl(salobj.CommandIdData(cmd_id=1, data=None))
            await csc.done_task

        for index in (False, None):
            with self.subTest(index=index):
                asyncio.get_event_loop().run_until_complete(doit(index=index))

    def test_specified_index(self):
        async def doit():
            index = next(index_gen)
            csc = salobj.test_utils.TestCsc.main(index=index, run_loop=False)
            self.assertEqual(csc.salinfo.index, index)
            csc.do_exitControl(salobj.CommandIdData(cmd_id=1, data=None))
            await csc.done_task

        asyncio.get_event_loop().run_until_complete(doit())

    def test_index_from_argument(self):
        async def doit():
            index = next(index_gen)
            original_argv = sys.argv[:]
            try:
                sys.argv[:] = [sys.argv[0], str(index)]
                csc = salobj.test_utils.TestCsc.main(index=True, run_loop=False)
                self.assertEqual(csc.salinfo.index, index)
                csc.do_exitControl(salobj.CommandIdData(cmd_id=1, data=None))
                await csc.done_task
            finally:
                sys.argv[:] = original_argv

        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()

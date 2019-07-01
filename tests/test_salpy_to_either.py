import asyncio
import pathlib
import unittest
import warnings

from lsst.ts import salobj

import SALPY_Test

STD_TIMEOUT = 5
START_TIMEOUT = 60
STOP_TIMEOUT = 5
INITIAL_LOG_LEVEL = 20
SAL__CMD_COMPLETE = 303

index_gen = salobj.index_generator()


class SALPYTestCase(unittest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_domain()
        self.datadir = pathlib.Path(__file__).resolve().parent / "data"
        self.index = next(index_gen)

    def test_salpy_remote_salobj_controller(self):
        self.check_salpy_remote("minimal_salobj_controller.py")

    def test_salpy_remote_salpy_controller(self):
        self.check_salpy_remote("minimal_salpy_controller.py")

    def check_salpy_remote(self, exec_name):
        async def doit():
            print(f"Remote: start {exec_name} in a subprocess")
            script_path = self.datadir / exec_name
            process = await asyncio.create_subprocess_exec(
                str(script_path), str(self.index), str(INITIAL_LOG_LEVEL))

            try:
                print(f"Remote: create SALPY remote with index={self.index}")
                manager = SALPY_Test.SAL_Test(self.index)
                manager.setDebugLevel(0)
                manager.salEventSub("Test_logevent_logLevel")
                manager.salTelemetrySub("Test_scalars")
                manager.salCommand("Test_command_setLogLevel")

                async def get_logLevel():
                    data = SALPY_Test.Test_logevent_logLevelC()
                    while True:
                        retcode = manager.getEvent_logLevel(data)
                        if retcode == SALPY_Test.SAL__OK:
                            return data
                        elif retcode != SALPY_Test.SAL__NO_UPDATES:
                            raise RuntimeError(f"Unexpected return code {retcode}")
                        await asyncio.sleep(0.1)

                async def get_scalars():
                    data = SALPY_Test.Test_scalarsC()
                    while True:
                        retcode = manager.getNextSample_scalars(data)
                        if retcode == SALPY_Test.SAL__OK:
                            return data
                        elif retcode != SALPY_Test.SAL__NO_UPDATES:
                            raise RuntimeError(f"Unexpected return code {retcode}")
                        await asyncio.sleep(0.1)

                async def send_setLogLevel(level):
                    done_ack_codes = frozenset((
                        SALPY_Test.SAL__CMD_ABORTED,
                        SALPY_Test.SAL__CMD_COMPLETE,
                        SALPY_Test.SAL__CMD_FAILED,
                        SALPY_Test.SAL__CMD_NOACK,
                        SALPY_Test.SAL__CMD_NOPERM,
                        SALPY_Test.SAL__CMD_STALLED,
                        SALPY_Test.SAL__CMD_TIMEOUT,
                    ))

                    cmd_data = SALPY_Test.Test_command_setLogLevelC()
                    cmd_data.level = level
                    cmd_id = manager.issueCommand_setLogLevel(cmd_data)
                    if cmd_id <= 0:
                        raise RuntimeError(f"Invalid cmd_id={cmd_id}")

                    ack_data = SALPY_Test.Test_ackcmdC()
                    while True:
                        response_id = manager.getResponse_setLogLevel(ack_data)
                        if response_id == cmd_id:
                            if ack_data.ack == SALPY_Test.SAL__CMD_COMPLETE:
                                return ack_data
                            elif ack_data.ack in done_ack_codes:
                                raise RuntimeError(f"Remote: command failed; ack={ack_data.ack}")
                        await asyncio.sleep(0.1)

                print("Remote: wait for initial logLevel")
                data = await asyncio.wait_for(get_logLevel(), timeout=START_TIMEOUT)
                print(f"Remote: read logLevel.level={data.level}")
                self.assertEqual(data.level, INITIAL_LOG_LEVEL)
                print("Remote: wait for initial scalars")
                data = await asyncio.wait_for(get_scalars(), timeout=STD_TIMEOUT)
                print(f"Remote: read scalars.int0={data.int0}")
                self.assertEqual(data.int0, INITIAL_LOG_LEVEL)

                for level in (10, 52, 0):
                    print(f"Remote: sending setLogLevel(level={level})")
                    await asyncio.wait_for(send_setLogLevel(level), timeout=STD_TIMEOUT)

                    print("Remote: wait for logLevel")
                    data = await asyncio.wait_for(get_logLevel(), timeout=STD_TIMEOUT)
                    print(f"Remote: read logLevel.level={data.level}")
                    self.assertEqual(data.level, level)
                    print("Remote: wait for scalars")
                    data = await asyncio.wait_for(get_scalars(), timeout=STD_TIMEOUT)
                    print(f"Remote: read scalars.int0={data.int0}")
                    self.assertEqual(data.int0, level)
                    await asyncio.sleep(0.1)

                await asyncio.wait_for(process.wait(), timeout=STOP_TIMEOUT)
            finally:
                print("Remote: done")
                if process.returncode is None:
                    process.terminate()
                    warnings.warn("Killed a process that was not properly terminated")

        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
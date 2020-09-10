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
import pathlib
import time
import unittest
import warnings

import asynctest

from lsst.ts import salobj

try:
    import SALPY_Test
except ImportError:
    SALPY_Test = None

# Long enough to perform any reasonable operation
# including starting a CSC or loading a script (seconds)
STD_TIMEOUT = 60

INITIAL_LOG_LEVEL = 20
SAL__CMD_COMPLETE = 303

index_gen = salobj.index_generator()


class SALPYTestCase(asynctest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()
        self.datadir = pathlib.Path(__file__).resolve().parent / "data"
        self.index = next(index_gen)

    @unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
    async def test_salpy_remote_salobj_controller(self):
        await self.check_salpy_remote("minimal_salobj_controller.py")

    @unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
    async def test_salpy_remote_salpy_controller(self):
        await self.check_salpy_remote("minimal_salpy_controller.py")

    async def check_salpy_remote(self, exec_name):
        # Create at least the scalars telemetry reader before creating
        # the subprocess, to be sure the remote sees telemetry from the
        # subprocess (telemetry is volatile, so has no historical data).
        print(f"Remote: create SALPY object and topics with index={self.index}")
        t0 = time.monotonic()
        manager = SALPY_Test.SAL_Test(self.index)
        manager.setDebugLevel(0)
        manager.salEventSub("Test_logevent_logLevel")
        manager.salTelemetrySub("Test_scalars")
        manager.salCommand("Test_command_setLogLevel")
        dt = time.monotonic() - t0
        print(f"Remote: took {dt:0.2f} seconds to create topics")

        print(f"Remote: start {exec_name} in a subprocess")
        script_path = self.datadir / exec_name
        process = await asyncio.create_subprocess_exec(
            str(script_path), str(self.index), str(INITIAL_LOG_LEVEL)
        )

        try:

            async def get_logLevel():
                data = SALPY_Test.Test_logevent_logLevelC()
                while True:
                    retcode = manager.getEvent_logLevel(data)
                    if retcode == SALPY_Test.SAL__OK:
                        return data
                    elif retcode != SALPY_Test.SAL__NO_UPDATES:
                        raise RuntimeError(f"Unexpected return code {retcode}")
                    await asyncio.sleep(0.01)

            async def get_scalars():
                data = SALPY_Test.Test_scalarsC()
                while True:
                    retcode = manager.getNextSample_scalars(data)
                    if retcode == SALPY_Test.SAL__OK:
                        return data
                    elif retcode != SALPY_Test.SAL__NO_UPDATES:
                        raise RuntimeError(f"Unexpected return code {retcode}")
                    await asyncio.sleep(0.01)

            async def send_setLogLevel(level):
                done_ack_codes = frozenset(
                    (
                        SALPY_Test.SAL__CMD_ABORTED,
                        SALPY_Test.SAL__CMD_COMPLETE,
                        SALPY_Test.SAL__CMD_FAILED,
                        SALPY_Test.SAL__CMD_NOACK,
                        SALPY_Test.SAL__CMD_NOPERM,
                        SALPY_Test.SAL__CMD_STALLED,
                        SALPY_Test.SAL__CMD_TIMEOUT,
                    )
                )

                cmd_data = SALPY_Test.Test_command_setLogLevelC()
                cmd_data.level = level
                cmd_id = manager.issueCommand_setLogLevel(cmd_data)
                if cmd_id <= 0:
                    raise RuntimeError(f"Invalid cmd_id={cmd_id}")
                await asyncio.sleep(0.001)

                ack_data = SALPY_Test.Test_ackcmdC()
                while True:
                    response_id = manager.getResponse_setLogLevel(ack_data)
                    if response_id == cmd_id:
                        self.assertEqual(ack_data.identity, f"Test:{self.index}")
                        if ack_data.ack == SALPY_Test.SAL__CMD_COMPLETE:
                            return ack_data
                        elif ack_data.ack in done_ack_codes:
                            raise RuntimeError(
                                f"Remote: command failed; ack={ack_data.ack}"
                            )
                    await asyncio.sleep(0.01)

            print("Remote: wait for initial logLevel event")
            data = await asyncio.wait_for(get_logLevel(), timeout=STD_TIMEOUT)
            print(f"Remote: read logLevel.level={data.level}")
            self.assertEqual(data.level, INITIAL_LOG_LEVEL)
            print("Remote: wait for initial scalars telemetry")
            data = await asyncio.wait_for(get_scalars(), timeout=STD_TIMEOUT)
            print(f"Remote: read scalars.int0={data.int0}")
            self.assertEqual(data.int0, INITIAL_LOG_LEVEL)

            for level in (10, 52, 0):
                print(f"Remote: send setLogLevel(level={level}) command")
                await asyncio.wait_for(send_setLogLevel(level), timeout=STD_TIMEOUT)

                print("Remote: wait for logLevel event")
                data = await asyncio.wait_for(get_logLevel(), timeout=STD_TIMEOUT)
                print(f"Remote: read logLevel.level={data.level}")
                self.assertEqual(data.level, level)
                print("Remote: wait for scalars telemetry")
                data = await asyncio.wait_for(get_scalars(), timeout=STD_TIMEOUT)
                print(f"Remote: read scalars.int0={data.int0}")
                self.assertEqual(data.int0, level)
                await asyncio.sleep(0.1)

            await asyncio.wait_for(process.wait(), timeout=STD_TIMEOUT)
        finally:
            print("Remote: done")
            if manager is not None:
                manager.salShutdown()
            if process.returncode is None:
                process.terminate()
                warnings.warn("Killed a process that was not properly terminated")


if __name__ == "__main__":
    unittest.main()

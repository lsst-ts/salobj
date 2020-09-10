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

    async def test_salobj_remote_salobj_controller(self):
        await self.check_salobj_remote("minimal_salobj_controller.py")

    @unittest.skipIf(SALPY_Test is None, "Could not import SALPY_Test")
    async def test_salobj_remote_salpy_controller(self):
        await self.check_salobj_remote("minimal_salpy_controller.py")

    async def check_salobj_remote(self, exec_name):
        # Create the remote before the subprocess
        # to be sure the remote sees telemetry from the subprocess
        # (telemetry is volatile, so has no historical data).
        print(f"Remote: create salobj remote with index={self.index}")
        t0 = time.monotonic()
        async with salobj.Domain() as domain, salobj.Remote(
            domain=domain, name="Test", index=self.index, evt_max_history=1,
        ) as remote:
            dt = time.monotonic() - t0
            print(
                f"Remote: creating topics and waiting for historical data took {dt:0.2f} seconds"
            )
            remote.salinfo.log.addHandler(logging.StreamHandler())

            print(f"Remote: start {exec_name} in a subprocess")
            script_path = self.datadir / exec_name
            process = await asyncio.create_subprocess_exec(
                str(script_path), str(self.index), str(INITIAL_LOG_LEVEL)
            )

            try:
                print("Remote: wait for initial logLevel event")
                data = await remote.evt_logLevel.next(flush=False, timeout=STD_TIMEOUT)
                print(f"Remote: read initial logLevel.level={data.level}")
                self.assertEqual(data.level, INITIAL_LOG_LEVEL)
                print("Remote: wait for initial scalars telemetry")
                data = await remote.tel_scalars.next(flush=False, timeout=STD_TIMEOUT)
                print(f"Remote: read initial scalars.int0={data.int0}")
                self.assertEqual(data.int0, INITIAL_LOG_LEVEL)

                for level in (10, 52, 0):
                    # remote.cmd_setLogLevel.put()
                    # print(f"Remote: put setLogLevel(level={level})")
                    print(f"Remote: send setLogLevel(level={level}) command")
                    ackcmd = await remote.cmd_setLogLevel.set_start(
                        level=level, timeout=STD_TIMEOUT
                    )
                    self.assertEqual(ackcmd.identity, remote.salinfo.identity)
                    print("Remote: wait for logLevel event")
                    data = await remote.evt_logLevel.next(
                        flush=False, timeout=STD_TIMEOUT
                    )
                    print(f"Remote: read logLevel={data.level}")
                    self.assertEqual(data.level, level)
                    print("Remote: wait for scalars telemetry")
                    data = await remote.tel_scalars.next(
                        flush=False, timeout=STD_TIMEOUT
                    )
                    print(f"Remote: read scalars.int0={data.int0}")
                    self.assertEqual(data.int0, level)
                    await asyncio.sleep(0.1)

                await asyncio.wait_for(process.wait(), timeout=STD_TIMEOUT)
            finally:
                print("Remote: done")
                if process.returncode is None:
                    process.terminate()
                    warnings.warn("Killed a process that was not properly terminated")


if __name__ == "__main__":
    unittest.main()

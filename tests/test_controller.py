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

import unittest

import asynctest
import numpy as np

from lsst.ts import salobj

np.random.seed(47)

index_gen = salobj.index_generator()


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
        index = next(index_gen)
        for name in command_names:
            setattr(self, f"do_{name}", self.mock_do_method)
        super().__init__("Test", index, do_callbacks=True)

    def mock_do_method(self, *args, **kwargs):
        pass


class ControllerConstructorTestCase(asynctest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()

    async def test_do_callbacks_false(self):
        index = next(index_gen)
        async with salobj.Controller("Test", index, do_callbacks=False) as controller:
            command_names = controller.salinfo.command_names
            for name in command_names:
                with self.subTest(name=name):
                    cmd = getattr(controller, "cmd_" + name)
                    self.assertFalse(cmd.has_callback)

            self.assertEqual(controller.salinfo.identity, f"Test:{index}")

    async def test_do_callbacks_true(self):
        index = next(index_gen)
        async with salobj.Domain() as domain, salobj.SalInfo(
            domain=domain, name="Test", index=index
        ) as salinfo:
            command_names = salinfo.command_names

        # Build a controller and check that callbacks are asigned.
        async with ControllerWithDoMethods(command_names) as controller:
            for cmd_name in command_names:
                with self.subTest(cmd_name=cmd_name):
                    cmd = getattr(controller, "cmd_" + cmd_name)
                    self.assertTrue(cmd.has_callback)

        skip_names = salobj.OPTIONAL_COMMAND_NAMES.copy()
        # do_setAuthList and do_setLogLevel are provided by Controller
        skip_names |= {"setAuthList", "setLogLevel"}
        for missing_name in command_names:
            if missing_name in skip_names:
                continue
            with self.subTest(missing_name=missing_name):
                bad_names = [name for name in command_names if name != missing_name]
                with self.assertRaises(TypeError):
                    ControllerWithDoMethods(bad_names)

        extra_names = list(command_names) + ["extra_command"]
        with self.assertRaises(TypeError):
            ControllerWithDoMethods(extra_names)


if __name__ == "__main__":
    unittest.main()

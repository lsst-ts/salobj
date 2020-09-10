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

from lsst.ts import salobj


class DdsUtilsTestCase(unittest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()

    def test_get_dds_version(self):
        for dds_file, desired_version in (
            ("dds-6.9.181127OSS-py3.7-linux-x86_64.egg/dds.so", "6.9.181127"),
            ("other-6.9.181127OSS-py3.7/dds.so", "6.9.181127"),
            ("dds-6.9.181 -py3.7-linux-x86_64.egg/dds.so", "6.9.181"),
            # Invalid format
            ("6.9.OSS-py3.7-linux-x86_64.egg/dds.so", "?"),
            # Only one level deep
            ("dds-6.9.181127OSS-py3.7-linux-x86_64.egg", "?"),
        ):
            with self.subTest(dds_file=dds_file):
                with unittest.mock.patch("dds.__file__", dds_file):
                    dds_version = salobj.get_dds_version()
                    self.assertEqual(dds_version, desired_version)


if __name__ == "__main__":
    unittest.main()

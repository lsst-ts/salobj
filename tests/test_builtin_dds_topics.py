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

from lsst.ts import idl
from lsst.ts import salobj


class DDSTopicsTestCase(asynctest.TestCase):
    """Test the standard DDS topics.
    """

    async def test_parse_nonsal_idl(self):
        idl_path = idl.get_idl_dir() / "DDS.idl"
        metadata = salobj.parse_nonsal_idl(name="DDS", idl_path=idl_path)
        self.assertEqual(metadata.name, "DDS")
        self.assertTrue(idl_path.samefile(metadata.idl_path))
        self.assertIsNone(metadata.sal_version)
        self.assertIsNone(metadata.xml_version)
        some_known_topic_names = (
            "ParticipantBuiltinTopicData",
            "TopicBuiltinTopicData",
            "PublicationBuiltinTopicData",
            "SubscriptionBuiltinTopicData",
        )
        self.assertTrue(
            set(metadata.topic_info).issuperset(set(some_known_topic_names))
        )
        for topic_metadata in metadata.topic_info.values():
            self.assertEqual(topic_metadata.field_info, {})

    async def test_remote(self):
        idl_path = idl.get_idl_dir() / "DDS.idl"
        metadata = salobj.parse_nonsal_idl(name="DDS", idl_path=idl_path)

        async with salobj.Domain() as domain, salobj.Remote(
            domain=domain, name="DDS"
        ) as remote:
            self.assertFalse(remote.salinfo.is_sal)
            self.assertEqual(
                metadata.topic_info.keys(), remote.salinfo.metadata.topic_info.keys()
            )
            for name in remote.salinfo.telemetry_names:
                self.assertTrue(hasattr(remote, f"tel_{name}"))
            print(remote.salinfo.telemetry_names)


if __name__ == "__main__":
    unittest.main()

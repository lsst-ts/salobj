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

__all__ = ["RemoteTelemetry"]

import warnings

from ..domain import DDS_READ_QUEUE_LEN
from . import read_topic


class RemoteTelemetry(read_topic.ReadTopic):
    """Read a specific telemetry topic.

    Parameters
    ----------
    salinfo : `.SalInfo`
        SAL component information
    name : `str`
        Telemetry topic name
    max_history : `int`, optional
        Deprecated because historical telemetry data is no longer available.
        Must be 0 (or None, but please don't do that) if specified.
    queue_len : `int`, optional
        Number of elements that can be queued for `get_oldest`.
    """

    def __init__(self, salinfo, name, max_history=None, queue_len=DDS_READ_QUEUE_LEN):
        # TODO DM-26474: remove the max_history argument and this code block.
        if max_history is not None:
            if max_history == 0:
                warnings.warn("max_history is deprecated", DeprecationWarning)
            else:
                raise ValueError(
                    f"max_history={max_history} is deprecated "
                    "and must be 0 (or None, but please don't do that) if specified"
                )

        super().__init__(
            salinfo=salinfo,
            name=name,
            sal_prefix="",
            max_history=0,
            queue_len=queue_len,
        )

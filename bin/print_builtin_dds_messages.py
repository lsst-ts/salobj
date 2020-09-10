#!/usr/bin/env python
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

"""A simple service to print OpenSplice's built-in DDS topics to stdout.
"""
import asyncio
import functools
import signal

from lsst.ts import salobj


def make_data_list(data):
    """Convert a DDS message into a list of key=value strings.

    Parameters
    ----------
    data : DDS message type
        Message data.
    """
    data_dict = data.get_vars()
    strlist = []
    for key, value in data_dict.items():
        if hasattr(value, "get_vars"):
            sublist = make_data_list(value)
            strlist += [f"{key}.{item}" for item in sublist]
        else:
            strlist.append(f"{key} = {value!r}")
    return strlist


def print_message(data, name):
    """Print a DDS message.

    Parameters
    ----------
    data : DDS message type
        Message data.
    name : `str`
        Topic name.
    """
    data_list = make_data_list(data)
    data_str = "; ".join(data_list)
    print(f"{name}: {data_str}")


class DDSMessagePrinter:
    """Read and print OpenSplice built-in DDS topics.
    """

    def __init__(self):
        self.run_task = asyncio.create_task(self.run())
        self.stop_future = asyncio.Future()

    async def run(self):
        """Created a remote, assign callbacks and wait for a stop_future.
        """
        print("Creating the remote")
        async with salobj.Domain() as domain, salobj.Remote(
            domain=domain, name="DDS"
        ) as remote:
            print("Assigning callbacks")
            for name in remote.salinfo.telemetry_names:
                topic = getattr(remote, f"tel_{name}")
                topic.callback = functools.partial(print_message, name=name)

            loop = asyncio.get_running_loop()
            for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                loop.add_signal_handler(s, self.signal_handler)

            print("Running")
            await self.stop_future

    def signal_handler(self):
        """Set stop_future done.
        """
        print("Stopping")
        if not self.stop_future.done():
            self.stop_future.set_result(None)

    @classmethod
    async def amain(cls):
        """Create a DDSMessagePrinter and wait for it to finish.
        """
        message_printer = cls()
        await message_printer.run_task


asyncio.run(DDSMessagePrinter.amain())

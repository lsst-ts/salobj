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

__all__ = ["BaseTopic"]

import abc

import ddsutil

# dict of sal_prefix: attr_prefix: the prefix used for
# Controller and Remote topic attributes.
_ATTR_PREFIXES = {"": "tel_", "logevent_": "evt_", "command_": "cmd_"}


class BaseTopic(abc.ABC):
    r"""Base class for topics.

    Parameters
    ----------
    salinfo : `.SalInfo`
        SAL component information
    name : `str`
        Topic name, without a "command\_" or "logevent\_" prefix.
    sal_prefix : `str`
        SAL topic prefix: one of "command\_", "logevent\_" or ""

    Raises
    ------
    RuntimeError
        If the topic cannot be constructed.

    Attributes
    ----------
    salinfo : `.SalInfo`
        The ``salinfo`` constructor argument.
    name : `str`
        The ``name`` constructor argument.
    sal_name : `str`
        The topic name used by SAL.
        For example: "logevent_summaryState".
    log : `logging.Logger`
        A logger.
    volatile : `bool`
        Is this topic volatile (in which case it has no historical data)?
    attr_name : `str`
        Name of topic attribute in `Controller` and `Remote`.
        For example: "evt_summaryState".
    rev_code : `str`
        Revision hash code for the topic.
        This code changes whenever the schema for the topic changes,
        and it is part of the DDS topic name. For example: "90255bf1"
    dds_name : `str`
        Name of topic seen by DDS.
        For example: "Test_logevent_summaryState_90255bf1".
    """

    def __init__(self, *, salinfo, name, sal_prefix):
        try:
            self.salinfo = salinfo
            self.name = str(name)
            self.sal_name = sal_prefix + self.name
            self.log = salinfo.log.getChild(self.sal_name)
            self.volatile = sal_prefix in ("", "command_")

            attr_prefix = "ack_" if name == "ackcmd" else _ATTR_PREFIXES.get(sal_prefix)
            if attr_prefix is None:
                raise ValueError(f"Uknown sal_prefix {sal_prefix!r}")
            self.attr_name = attr_prefix + name

            revname = salinfo.revnames.get(self.sal_name)
            if revname is None:
                raise ValueError(
                    f"Could not find {self.salinfo.name} topic {self.sal_name}"
                )
            self.dds_name = revname.replace("::", "_")
            if self.salinfo.is_sal:
                self.rev_code = self.dds_name.rsplit("_", 1)[1]
            else:
                self.rev_code = ""

            self._type = ddsutil.get_dds_classes_from_idl(
                salinfo.metadata.idl_path, revname
            )
            qos = (
                salinfo.domain.volatile_topic_qos
                if self.volatile
                else salinfo.domain.topic_qos
            )
            self._topic = self._type.register_topic(
                salinfo.domain.participant, self.dds_name, qos
            )

        except Exception as e:
            raise RuntimeError(f"Failed to create topic {salinfo.name}.{name}") from e

    @property
    def DataType(self):
        """The type (class) for a message of this topic.

        When you read or write a message for this topic you are reading
        or writing an instance of `DataType`.

        Notes
        -----
        The preferred way to write a message for a topic is:

        * `RemoteCommand.set_start` to start a command.
        * `CommandEvent.set_put` to write an event.
        * `CommandTelemetry.set_put` to write a telemetry message.

        However, it is also possible to use `DataType` to create a message,
        then write, it as separate operations. For example,
        assuming we have a `Remote` for SAL component "Test"::

            # The preferred way to issue a command:
            await = remote.cmd_wait.set_put(duration=2, timeout=5)

            # But an alternative is to first create the command,
            # then send it, as two separate operations:
            message = remote.cmd_wait.DataType(duration=2)
            await remote.cmd_wait.start(message, timeout=5)

            # Or, even more verbosely:
            message = remote.cmd_wait.DataType()
            message.duration = 2
            await remote.cmd_wait.start(message, timeout=5)
        """
        return self._type.topic_data_class

    @property
    def metadata(self):
        """Get topic metadata as a `TopicMetadata`, if available, else `None`.
        """
        return self.salinfo.metadata.topic_info.get(self.sal_name)

    def __repr__(self):
        return f"{type(self).__name__}({self.salinfo.name}, {self.salinfo.index}, {self.name})"

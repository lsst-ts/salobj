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

__all__ = ["Domain", "DDS_READ_QUEUE_LEN"]

import asyncio
import os
import weakref
import warnings

import dds

from lsst.ts import idl
from . import base

DDS_READ_QUEUE_LEN = 100
"""Length of DDS read queue

Warning: this must be equal to or greater than the queue length in the
OpenSplice configuration file (pointed to by $OSPL_URI).
This information is not available from ``dds`` objects, so I set queue depth
instead of using the value specified in the QoS XML file.
"""

MAX_RANDOM_HOST = (1 << 31) - 1


class Domain:
    r"""dds domain participant and quality of service information.

    Attributes
    ----------
    participant : ``dds.DomainParticipant``
        DDS domain participant.
    origin : `int`
        Process ID. Used to set the ``private_origin`` field of output samples.
    default_identity : `str`
        Default value used for the identity field of `SalInfo`.
        Initalized to ``user_host`` but `Controller`\ 's constructor
        sets it to `SalInfo.user_index` so that all `Remote`\ s
        constructed with the controller's domain will have the
        controller's identity.
        For testing purposes, it is allowed to change this field
        before constructing a `Remote`.
    user_host : `str`
        username@host. This will match ``identity`` unless the latter
        is set to a CSC name.
    idl_dir : `pathlib.Path`
        Root directory of the ``ts_idl`` package.
    qos_provider : ``dds.QosProvider``
        Quality of service provider.
    topic_qos : ``dds.Qos``
        Quality of service for non-volatile DDS topics (those that want
        late-joiner data).
    volatile_topic_qos : ``dds.Qos``
        Quality of service for volatile topics (those that do not want any
        late-joiner data).
        Note: we cannot just make readers volatile to avoid late-joiner data,
        as volatile readers receive late-joiner data from non-volatile writers.
        So we make readers, writers, and topics all volatile.
        According to ADLink it is a feature, not a bug.
    reader_qos : ``dds.Qos``
        Quality of service for non-volatile DDS readers.
    volatile_reader_qos : ``dds.Qos``
        Quality of service for volatile DDS readers.
    writer_qos : ``dds.Qos``
        Quality of service for non-volatile DDS writers.
    volatile_writer_qos : ``dds.Qos``
        Quality of service for volatile DDS writers.

    Notes
    -----
    Reads the following `Environment Variables
    <https://ts-salobj.lsst.io/configuration.html#environment_variables>`_;
    follow the link for details:

    * OSPL_MASTER_PRIORITY, optional is used to set the Master Priority.
      If present, it must be a value between 0 and 255.

    **Cleanup**

    It is important to close a `Domain` when you are done with it, especially
    in unit tests, because otherwise unreleased resources may cause problems.
    To make this easier `Domain` is a context manager.

    `Domain` contains a registry of `SalInfo` instances, so that it can close
    them when the domain is closed. The registry uses weak references to avoid
    circular dependencies (since SalInfo stores the domain). `SalInfo`
    instances automatically register themselves with the provided domain.

    To conserve resources you should have only one `Domain` per process.
    Thus:

    * `Controller` creates its own Domain as attribute ``domain``
      and closes it when the controller is closed. To create a
      `Remote` for a controller, use the domain from the controller, e.g.::

        controller = Controller(name="Test", index=47)
        try:
            remote = Remote(domain=controller.domain, name="Test", index=47)
            ...
        finally:
            await controller.close()

        # or if you only want the objects for the duration of a function,
        # e.g in a unit test:
        async with Controller(name="Test", index=47) as controller:
            remote = Remote(domain=controller.domain, name="Test", index=47)
            ...

    * If you are creating `Remote`\ s without a `Controller` then you must
      create the Domain yourself and close it when you are finished, e.g.::

        domain = salobj.Domain()
        try:
            remote = salobj.Remote(domain=domain, name="Test", index=47)
            ...
        finally:
            await domain.close()

        # or if you only want the objects for the duration of a function,
        # e.g in a unit test:
        async with salobj.Domain() as domain:
            test_remote = salobj.Remote(domain=domain, name="Test", index=5)
    """

    def __init__(self):
        self.participant = None

        self.user_host = base.get_user_host()
        self.default_identity = self.user_host

        # Accumulators for verifying that close is working.
        self.num_read_loops = 0
        self.num_read_threads = 0

        self.done_task = asyncio.Future()

        # Set of SalInfo.
        self._salinfo_set = weakref.WeakSet()

        self.origin = os.getpid()
        self.idl_dir = idl.get_idl_dir()

        qos_path = idl.get_qos_path()
        self.qos_provider = dds.QosProvider(qos_path.as_uri(), "DDS DefaultQosProfile")

        participant_qos = self.qos_provider.get_participant_qos()
        self.participant = dds.DomainParticipant(qos=participant_qos)

        # Create quality of service objects that do not depend on
        # the DDS partition. The two that do (publisher and subscriber)
        # are created in SalInfo, so that different SalInfo can be used
        # with different partitions.
        try:
            volatile_policy = dds.DurabilityQosPolicy(dds.DDSDurabilityKind.VOLATILE)

            self.topic_qos = self.qos_provider.get_topic_qos()

            self.volatile_topic_qos = self.qos_provider.get_topic_qos()
            self.volatile_topic_qos.set_policies([volatile_policy])

            self.writer_qos = self.qos_provider.get_writer_qos()
            self.volatile_writer_qos = self.qos_provider.get_writer_qos()
            self.volatile_writer_qos.set_policies([volatile_policy])

            read_queue_policy = dds.HistoryQosPolicy(
                depth=DDS_READ_QUEUE_LEN, kind=dds.DDSHistoryKind.KEEP_LAST
            )
            self.reader_qos = self.qos_provider.get_reader_qos()
            self.reader_qos.set_policies([read_queue_policy])
            self.volatile_reader_qos = self.qos_provider.get_reader_qos()
            self.volatile_reader_qos.set_policies([read_queue_policy, volatile_policy])
        except Exception:
            # Very unlikely, but just in case...
            self.participant.close()
            raise

    @property
    def salinfo_set(self):
        return self._salinfo_set

    def add_salinfo(self, salinfo):
        """Add the specified salinfo to the internal registry.

        Parameters
        ----------
        salinfo : `SalInfo`
            SAL component information

        Raises
        ------
        RuntimeError
            If the salinfo is already present
        """
        if salinfo in self._salinfo_set:
            raise RuntimeError(f"salinfo {salinfo} already added")
        self._salinfo_set.add(salinfo)

    def remove_salinfo(self, salinfo):
        """Remove the specified salinfo from the internal registry.

        Parameters
        ----------
        salinfo : `SalInfo`
            SAL component information

        Returns
        -------
        removed : `boolean`
            True if removed, False if not found
        """
        try:
            self._salinfo_set.remove(salinfo)
            return True
        except KeyError:
            return False

    async def close(self):
        """Close all registered `SalInfo` and the dds domain participant.

        May be called multiple times. The first call closes the Domain;
        subsequent calls wait until the Domain is closed.
        """
        if self.participant is None:
            await self.done_task
            return
        try:
            while self._salinfo_set:
                salinfo = self._salinfo_set.pop()
                await salinfo.close()
        finally:
            self.close_dds()
        if self.num_read_loops != 0 or self.num_read_threads != 0:
            warnings.warn(
                f"After Domain.close num_read_loops={self.num_read_loops} and "
                f"num_read_threads={self.num_read_threads}; both should be 0"
            )
        self.done_task.set_result(None)

    def close_dds(self):
        """Close the dds DomainParticipant."""
        participant = getattr(self, "participant", None)
        if participant is not None:
            participant.close()
            self.participant = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, type, value, traceback):
        await self.close()

    def __del__(self):
        """Last-ditch effort to clean up critical resources.

        Users should call `close` instead, because it does more,
        and because ``__del__`` is not reliably called.
        """
        self.close_dds()

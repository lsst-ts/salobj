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

__all__ = ["QueueCapacityChecker", "ReadTopic"]

import asyncio
import bisect
import collections
import inspect

import dds

from .base_topic import BaseTopic
from ..domain import DDS_READ_QUEUE_LEN
from .. import base


class QueueCapacityChecker:
    """Log warnings for a fixed-length queue that should contain
    no more than one item.

    Call `check_nitems` to check the number of items in the queue.
    This will log a warning or error, if appropriate.

    Parameters
    ----------
    descr : `str`
        Brief description of queue, e.g. "python read queue"
        or "DDS read queue".
    log : `logging.Logger`
        Logger to which to write messages.
    queue_len : `int`
        Length of queue

    Attributes
    ----------
    warn_thresholds : `List` [`int`]
        Values for ``warn_threshold`` (see next item). Set to:

        * 5-10 elements, whichever is closest to ``queue_len/10``
        * 1/2 full, but only if ``queue_len >= 20``
        * 9/10 full
        * full

        The corresponding reset thresholds are 1/2 these values.

    warn_threshold : `int` or `None`
        A call to ``check_nitems(n)`` with ``n > warn_threshold``
        will produce a log message and update ``warn_threshold``
        and ``reset__threshold`` as follows:

        *  ``warn_threshold`` is set to the largest warn threshold <= n
           in ``warn_thresholds``, or `None` if the queue is full.
        * ``reset_threshold`` is set to the half of the next lower
          warning threshold.
    reset_threshold : `int` or `None`
        A call to ``check_nitems(n)`` with ``n < reset_threshold``
        will reduce ``warn_threshold`` and ``reset_threshold`` as follows:

        * ``reset_threshold`` is set to the largest reset threshold <= n,
          or `None` if the queue is empty.
        * ``warn_threshold`` is set to the warning threshold
          corresponding to one reset higher reset level.

    Notes
    -----
    Once a message has been logged for a particular threshold,
    no more messages are sent until either the queue fills enough
    to cross the next warning threshold or empties enough to reduce
    the warning threshold.

    Log messages are warnings unless the queue is full. A full queue
    produces an error because data is likely to have been lost.
    """

    def __init__(self, descr, log, queue_len):
        if queue_len < 10:
            raise ValueError(f"queue_len {queue_len} must be >= 10")
        self.descr = descr
        self.log = log
        self.queue_len = queue_len
        warn_thresholds = [
            min(10, max(5, queue_len // 10)),
            queue_len * 9 // 10,
            queue_len,
        ]
        if queue_len >= 20:
            warn_thresholds.append(queue_len // 2)
        self.warn_thresholds = tuple(sorted(warn_thresholds))
        self._reset_thresholds = tuple(
            warn_thresh // 2 for warn_thresh in self.warn_thresholds
        )
        self.warn_threshold = self.warn_thresholds[0]
        self.reset_threshold = None

    def check_nitems(self, nitems):
        """Check the number of items in the queue and log a message
        if appropriate.

        Parameters
        ----------
        nitems : `int`
            Number of elements in the queue.

        Returns
        -------
        did_log: `bool`
            True if a message was logged.
        """
        if self.warn_threshold is not None and nitems >= self.warn_threshold:
            # Issue a warning or error log message
            # and set new warning and reset thresholds.
            if nitems >= self.queue_len:
                self.warn_threshold = None
                self.reset_threshold = self._reset_thresholds[-1]
                self.log.error(
                    f"{self.descr} is full ({self.queue_len} elements); data may be lost"
                )
            else:
                index = bisect.bisect_right(self.warn_thresholds, nitems)
                self.warn_threshold = self.warn_thresholds[index]
                self.reset_threshold = self._reset_thresholds[index - 1]
                self.log.warning(
                    f"{self.descr} is filling: {nitems} of {self.queue_len} elements"
                )
            return True
        elif self.reset_threshold is not None and nitems <= self.reset_threshold:
            # Reset to lower warning and reset thresholds
            index = bisect.bisect_right(self._reset_thresholds, nitems - 1)
            self.warn_threshold = self.warn_thresholds[index]
            if index > 0:
                self.reset_threshold = self._reset_thresholds[index - 1]
            else:
                self.reset_threshold = None
        return False


class ReadTopic(BaseTopic):
    r"""Base class for reading a topic.

    Parameters
    ----------
    salinfo : `.SalInfo`
        SAL component information
    name : `str`
        Topic name, without a "command\_" or "logevent\_" prefix.
    sal_prefix : `str`
        SAL topic prefix: one of "command\_", "logevent\_" or ""
    max_history : `int`
        Maximum number of historical items to read:

        * 0 is required for commands and the ackcmd reader
        * 1 is recommended for events and telemetry
    queue_len : `int`, optional
        The maximum number of messages that can be read and not dealt with
        by a callback function or `next` before older messages will be dropped.
    filter_ackcmd : `bool`, optional
        Filter out cmdack topics so we only see responses to commands
        that we sent? This is normally what you want, but it is not wanted
        for SAL/Kafka producers.
        Ignored if ``name`` != "ackcmd".

    Raises
    ------
    ValueError
        If max_history < 0.
    ValueError
        If max_history > 0 and the topic is volatile (command or ackcmd).
    ValueError
        If queue_len <= 0.
    ValueError
        If max_history > queue_len.

    Attributes
    ----------
    isopen : `bool`
        Is this read topic open? `True` until `close` is called.
    dds_queue_length_checker : `QueueCapacityChecker`
        Queue length checker for the DDS queue.
    python_queue_length_checker : `QueueCapacityChecker`:
        Queue length checker for the Python queue.

    Notes
    -----
    **Queues**

    There are actually two queues: an internal queue whose length
    is set by ``queue_len`` and a dds queue whose length is set by
    low level configuration. Data can be lost in two ways:

    - If this class cannot read messages from the dds queue fast enough,
      then older messages will be dropped from the dds queue. You will get
      a warning log message if the reader starts to fall behind.
    - As messages are read they are put on the internal queue.
      If a callback function or `next` does not process data quickly enough
      then older messages are dropped from the internal queue.
      If you have a callback function then you will get several
      warning log messages as this internal queue fills up.
      You get no warning otherwise because this class has no way of knowing
      whether or not you intend to read all messages.

    **Reading**

    Reading is performed by the `.SalInfo` which has single read loop that
    reads messages for all topics. This is more efficient than having each
    `ReadTopic` read its own messages.

    **Modifying Messages**

    All functions that return messages return from an internal cache.
    This cached value is replaced by all read operations. So as long as
    no other code modifies a message, the returned message will not change.

    To safely modify a returned message, make your own copy
    with ``copy.copy(data)``.
    """

    def __init__(
        self,
        *,
        salinfo,
        name,
        sal_prefix,
        max_history,
        queue_len=DDS_READ_QUEUE_LEN,
        filter_ackcmd=True,
    ):
        super().__init__(salinfo=salinfo, name=name, sal_prefix=sal_prefix)
        self.isopen = True
        self._allow_multiple_callbacks = False
        if max_history < 0:
            raise ValueError(f"max_history={max_history} must be >= 0")
        if max_history > 0 and self.volatile:
            raise ValueError(f"max_history={max_history} must be 0 for volatile topics")
        if queue_len <= 0:
            raise ValueError(f"queue_len={queue_len} must be positive")
        if max_history > queue_len:
            raise ValueError(
                f"max_history={max_history} must be <= queue_len={queue_len}"
            )
        self._max_history = int(max_history)
        self._data_queue = collections.deque(maxlen=queue_len)
        self._current_data = None
        # task that `next` waits on
        self._next_task = base.make_done_future()
        self._callback = None
        self._callback_tasks = set()
        self._callback_loop_task = base.make_done_future()
        self.dds_queue_length_checker = QueueCapacityChecker(
            descr=f"{name} DDS read queue", log=self.log, queue_len=DDS_READ_QUEUE_LEN
        )
        self.python_queue_length_checker = QueueCapacityChecker(
            descr=f"{name} python read queue", log=self.log, queue_len=queue_len
        )
        qos = (
            salinfo.domain.volatile_reader_qos
            if self.volatile
            else salinfo.domain.reader_qos
        )
        if sal_prefix == "command_":
            subscriber = salinfo.cmd_subscriber
        else:
            subscriber = salinfo.data_subscriber
        self._reader = subscriber.create_datareader(self._topic, qos)
        # TODO DM-26411: replace ANY_INSTANCE_STATE with ALIVE_INSTANCE_STATE
        # once the OpenSplice issue 00020647 is fixed.
        read_mask = [
            dds.DDSStateKind.NOT_READ_SAMPLE_STATE,
            dds.DDSStateKind.ANY_INSTANCE_STATE,
        ]
        queries = []
        if salinfo.index > 0:
            queries.append(f"{salinfo.name}ID = {salinfo.index}")
        if name == "ackcmd" and filter_ackcmd:
            queries += [
                f"origin = {salinfo.domain.origin}",
                f"identity = '{salinfo.identity}'",
            ]
        if queries:
            full_query = " AND ".join(queries)
            try:
                read_condition = dds.QueryCondition(self._reader, read_mask, full_query)
            except Exception as e:
                raise RuntimeError(
                    f"Could not create QueryCondition using full_query={full_query!r}"
                ) from e
        else:
            read_condition = self._reader.create_readcondition(read_mask)
        self._read_condition = read_condition

        salinfo.add_reader(self)

    @property
    def allow_multiple_callbacks(self):
        """Can callbacks can run simultaneously?

        Notes
        -----
        Ignored for synchronous callbacks because those block
        while running. In particular, if the callback is
        synchronous but launches one or more background jobs
        then the number of those jobs cannot be limited by
        this class.
        """
        return self._allow_multiple_callbacks

    @allow_multiple_callbacks.setter
    def allow_multiple_callbacks(self, allow):
        self._allow_multiple_callbacks = bool(allow)

    @property
    def callback(self):
        """Callback function, or None if there is not one.

        The callback function is called when a new message is received;
        it receives one argument: the message (an object of type
        `topics.BaseTopic.DataType`).

        Raises
        ------
        TypeError
            When setting a new callback if the callback is not None
            and is not callable.

        Notes
        -----
        The callback function can be synchronous or asynchronous
        (e.g. defined with ``async def``).

        Setting a callback flushes the queue, and it will remain empty
        as long as there is a callback.

        `get_oldest` and `next` are prohibited if there is a callback function.
        Technically they could both work, but `get_oldest` would always return
        `None` and `next` would miss messages if they arrived while waiting
        for something else. It seemed safer to just raise an exception.
        """
        return self._callback

    @callback.setter
    def callback(self, func):
        self._cancel_callbacks()

        if func is None:
            # clear the existing callback
            self._callback = None
            return

        # flush the queue, set a new callback and restart the callback loop
        if not callable(func):
            raise TypeError(f"func={func} not callable")
        self._data_queue.clear()
        self._callback = func
        self._callback_loop_task = asyncio.create_task(self._callback_loop())

    @property
    def has_callback(self):
        """Return True if there is a callback function."""
        return self._callback is not None

    @property
    def has_data(self):
        """Has any data been seen for this topic?

        Raises
        ------
        RuntimeError
            If the ``salinfo`` has not started reading.
        """
        self.salinfo.assert_started()
        return self._current_data is not None

    @property
    def max_history(self):
        return self._max_history

    async def close(self):
        """Shut down and release resources.

        Intended to be called by SalInfo.close(),
        since that tracks all topics.
        """
        if not self.isopen:
            return
        self.isopen = False
        self._cancel_callbacks()
        self._callback = None
        self._next_task.cancel()
        self._reader.close()
        self._data_queue.clear()

    async def aget(self, timeout=None):
        """Get the current message, if any, else wait for the next message.

        Parameters
        ----------
        timeout : `float`, optional
            Time limit, in seconds. If None then no time limit.

        Returns
        -------
        data : `DataType`
            The current or next message.

        Raises
        ------
        RuntimeError
            If a callback function is present,
            or if the ``salinfo`` has not started reading.

        Notes
        -----
        Do not modify the returned data. To make a copy that you can
        safely modify, use ``copy.copy(data)``.
        """
        self.salinfo.assert_started()
        if self.has_callback:
            raise RuntimeError("Not allowed because there is a callback function")
        if self._current_data is not None:
            return self._current_data
        return await self._next(timeout=timeout)

    def flush(self):
        """Flush the queue of unread data.

        Raises
        ------
        RuntimeError
            If a callback function is present.
        """
        if self.has_callback:
            raise RuntimeError("Not allowed because there is a callback function")
        self._data_queue.clear()

    def get(self, flush=True):
        """Get the most recently seen message, or `None` if no data ever seen.

        Parameters
        ----------
        flush : `bool`, optional
            Flush the queue? Defaults to `True` for backwards compatibility.
            This only affects the next message returned by `next`
            and is ignored if there is a callback function.

        Returns
        -------
        data : ``self.DataType`` or `None`
            Return ``self.data`` if data has been read, else `None`.

        Raises
        ------
        RuntimeError
            If the ``salinfo`` has not started reading.
        """
        self.salinfo.assert_started()
        if flush and not self.has_callback:
            self.flush()
        return self._current_data

    def get_oldest(self):
        """Pop and return the oldest message from the queue, or `None`
        if the queue is empty.

        Returns
        -------
        data : ``self.DataType`` or `None`
            The oldest message found on the queue, if any, else `None`.

        Raises
        ------
        RuntimeError
            If a callback function is present,
            or if the ``salinfo`` has not started reading.

        Notes
        -----
        Use with caution when mixing with `next`, since that also
        consumes data from the queue.
        """
        self.salinfo.assert_started()
        if self.has_callback:
            raise RuntimeError("Not allowed because there is a callback function")
        if self._data_queue:
            return self._data_queue.popleft()
        return None

    async def next(self, *, flush, timeout=None):
        """Wait for a message, possibly returning the oldest queued message.

        Parameters
        ----------
        flush : `bool`
            If True then flush the queue before starting a read.
            If False then pop and return the oldest message from the queue,
            if any, else wait for new data.
        timeout : `float`, optional
            Time limit, in seconds. If None then no time limit.

        Returns
        -------
        data : `DataType`
            The message data.

        Raises
        ------
        RuntimeError
            If a callback function is present,
            or if the ``salinfo`` has not started reading.

        Notes
        -----
        Do not modify the returned data. To make a copy that you can
        safely modify, use ``copy.copy(data)``.
        """
        self.salinfo.assert_started()
        if self.has_callback:
            raise RuntimeError("Not allowed because there is a callback function")
        if flush:
            self.flush()
        return await self._next(timeout=timeout)

    async def _next(self, *, timeout=None):
        """Implement next.

        Unlike `next`, this can be called while using a callback function.

        Raises
        ------
        RuntimeError
            If code is already waiting for the next message.
        """
        self.python_queue_length_checker.check_nitems(len(self._data_queue))
        if self._data_queue:
            return self._data_queue.popleft()
        if self._next_task.done():
            self._next_task = asyncio.Future()
        return await asyncio.wait_for(self._next_task, timeout=timeout)

    async def _callback_loop(self):
        while True:
            if not self.has_callback:
                return
            data = await self._next()
            result = self._run_callback(data)
            if self.allow_multiple_callbacks:
                # Purge done callback tasks and add a new one.
                self._callback_tasks = {
                    task for task in self._callback_tasks if not task.done()
                }
                self._callback_tasks.add(asyncio.create_task(result))
            else:
                await result

    def _cancel_callbacks(self):
        """Cancel the callback loop and all existing callback tasks.
        """
        self._callback_loop_task.cancel()
        while self._callback_tasks:
            task = self._callback_tasks.pop()
            task.cancel()

    async def _run_callback(self, data):
        try:
            result = self._callback(data)
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not isinstance(e, base.ExpectedError):
                self.log.exception(f"Callback {self.callback} failed with data={data}")

    def _queue_data(self, data_list):
        """Queue multiple one or more messages.

        This is a no-op if ``data_list`` is empty.

        Also update ``self._current_data`` and fire `self._next_task`
        (if pending).
        """
        if not data_list:
            return
        for data in data_list:
            self._queue_one_item(data)
        self._current_data = data
        if not self._data_queue:
            self.log.warning(
                f"{self.name}: queue empty after queuing {len(data_list)} items; "
                "not setting _next_task done."
            )
        elif not self._next_task.done():
            oldest_message = self._data_queue.popleft()
            self._next_task.set_result(oldest_message)

    def _queue_one_item(self, data):
        """Add a single message to the internal queue.

        Subclasses may override to massage the message before queuing.
        `ControllerCommand` does this.
        """
        self._data_queue.append(data)

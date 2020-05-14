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

__all__ = [
    "LOCAL_HOST",
    "MASTER_PRIORITY_ENV_VAR",
    "MAX_SAL_INDEX",
    "MJD_MINUS_UNIX_SECONDS",
    "SECONDS_PER_DAY",
    "AckError",
    "AckTimeoutError",
    "ExpectedError",
    "astropy_time_from_tai_unix",
    "index_generator",
    "make_done_future",
    "name_to_name_index",
    "current_tai",
    "tai_from_utc",
    "tai_from_utc_unix",
]

import asyncio
import bisect
import datetime
import logging
import math
import re
import threading
import time

import astropy.time
import astropy.utils.iers

from . import sal_enums

LOCAL_HOST = "127.0.0.1"

# Name of the environment variable that specifies the Master Priority.
# See the `Domain` doc string for details.
MASTER_PRIORITY_ENV_VAR = "OSPL_MASTER_PRIORITY"

# Maximum allowed SAL index (inclusive)
MAX_SAL_INDEX = (1 << 31) - 1

SECONDS_PER_DAY = 24 * 60 * 60

# MJD - unix seconds, in seconds
MJD_MINUS_UNIX_SECONDS = (
    astropy.time.Time(0, scale="utc", format="unix").utc.mjd * SECONDS_PER_DAY
)

# Regex for a SAL componet name encoded as <name>[:<index>]
_NAME_REGEX = re.compile(r"(?P<name>[a-zA-Z_-][a-zA-Z0-9_-]*)(:(?P<index>\d+))?$")

# A table of leap seconds used by `tai_from_utc_unix`.
# The table is automatically updated by `_update_leap_second_table`.
_LEAP_SECOND_TABLE = None
# A threading timer that schedules automatic update of the leap second table.
_LEAP_SECOND_TABLE_UPDATE_TIMER = None
# When to update the leap second table, in days before expiration.
_LEAP_SECOND_TABLE_UPDATE_MARGIN_DAYS = 10


def _ackcmd_str(ackcmd):
    """Format an Ack as a string"""
    return (
        f"(ackcmd private_seqNum={ackcmd.private_seqNum}, "
        f"ack={sal_enums.as_salRetCode(ackcmd.ack)!r}, error={ackcmd.error}, result={ackcmd.result!r})"
    )


class AckError(Exception):
    """Exception raised if a command fails.

    Parameters
    ----------
    msg : `str`
        Error message
    ackcmd : ``AckType``
        Command acknowledgement.
    """

    def __init__(self, msg, ackcmd):
        super().__init__(msg)
        self.ackcmd = ackcmd
        """Command acknowledgement."""

    def __str__(self):
        return f"msg={self.args[0]!r}, ackcmd={_ackcmd_str(self.ackcmd)}"

    def __repr__(self):
        return f"{type(self).__name__}({self!s})"


class AckTimeoutError(AckError):
    """Exception raised if waiting for a command acknowledgement times out.

    The ``ackcmd`` attribute is the last ackcmd seen.
    If no command acknowledgement was received then
    the ack code will be `SalRetCode.CMD_NOACK`.
    """

    pass


class ExpectedError(Exception):
    """Report an error that does not benefit from a traceback.

    For example, a command is invalid in the current state.
    """

    pass


def astropy_time_from_tai_unix(tai_unix):
    """Get astropy time from TAI in unix seconds.

    Parameters
    ----------
    tai_unix : `float`
        TAI time as unix seconds, e.g. the time returned by CLOCK_TAI
        on linux systems.
    """
    tai_mjd = (MJD_MINUS_UNIX_SECONDS + tai_unix) / SECONDS_PER_DAY
    return astropy.time.Time(tai_mjd, scale="tai", format="mjd")


def index_generator(imin=1, imax=MAX_SAL_INDEX, i0=None):
    """Sequential index generator.

    Returns values i0, i0+1, i0+2, ..., max, min, min+1, ...

    Parameters
    ----------
    imin : `int` (optional)
        Minimum index (inclusive).
    imax : `int` (optional)
        Maximum index (inclusive).
    i0 : `int` (optional)
        Initial index; if None then use ``imin``.

    Raises
    ------
    ValueError
        If imin >= imax
    """
    imin = int(imin)
    imax = int(imax)
    i0 = imin if i0 is None else int(i0)
    if imax <= imin:
        raise ValueError(f"imin={imin} must be less than imax={imax}")
    if not imin <= i0 <= imax:
        raise ValueError(f"i0={i0} must be >= imin={imin} and <= imax={imax}")

    # define an inner generator and return that
    # in order to get immediate argument checking
    def index_impl():
        index = i0 - 1
        while True:
            index += 1
            if index > imax:
                index = imin

            yield index

    return index_impl()


def make_done_future():
    future = asyncio.Future()
    future.set_result(None)
    return future


def name_to_name_index(name):
    """Parse a SAL component name of the form name[:index].

    Parameters
    ----------
    name : `str`
        Component name of the form ``name`` or ``name:index``.
        The default index is 0.

    Raises
    ------
    ValueError
        If the name cannot be parsed.

    Notes
    -----
    Examples:

    * ``"Script" -> ("Script", 0)``
    * ``"Script:0" -> ("Script", 0)``
    * ``"Script:15" -> ("Script", 15)``
    * ``" Script:15" -> raise ValueError (leading space)``
    * ``"Script:15 " -> raise ValueError (trailing space)``
    * ``"Script:" -> raise ValueError (colon with no index)``
    * ``"Script:zero" -> raise ValueError (index not an integer)``
    """
    match = _NAME_REGEX.match(name)
    if not match:
        raise ValueError(f"name {name!r} is not of the form 'name' or 'name:index'")
    name = match["name"]
    index = match["index"]
    index = 0 if index is None else int(index)
    return (name, index)


def current_tai():
    """Return the current TAI in unix seconds.

    TODO: DM-21097: improve accuracy near a leap second transition.
    """
    return tai_from_utc_unix(time.time())


def tai_from_utc(utc, format="unix"):
    """Return TAI in unix seconds, given UTC or any `astropy.time.Time`.

    Parameters
    ----------
    utc : `float`, `str` or `astropy.time.Time`
        UTC time in the specified format.
    format : `str` or `None`
        Format of the UTC time, as an `astropy.time` format name,
        or `None` to have astropy guess.
        Ignored if ``utc`` is an instance of `astropy.time.Time`.

    Returns
    -------
    tai_unix : `float`
        TAI time in unix seconds.

    Raises
    ------
    ValueError
        If the date is earlier than 1972 (which is before integer leap seconds)
        or within one day of the expiration date of the leap second table
        (which is automatically updated).

    Notes
    -----
    If you have UTC in floating point format and performance is an issue,
    please call `tai_from_utc_unix` to avoid the overhead of converting
    your time to an `astropy.time.Time`.

    This function will be deprecated once we upgrade to a version of
    ``astropy`` that supports TAI seconds. `tai_from_utc_unix` will remain.

    **Leap Seconds on the Day Before a Leap Second**

    This routine may not behave as you expect on the day before a leap second.
    Specify the date in ISO format if you want the correct answer.

    When UTC is expressed as unix time, Julian Day, or Modified Julian Day
    the answer is ambiguous, so the result can be off by up to a second from
    what you might expect. This function follows `astropy.time` and
    Standards of Fundamental Astronomy (SOFA) by shrinking or stretching
    unix time, Julian Day, and Modified Julian Day, as needed, so that
    exactly one day of 86400 seconds (of modified duration) elapses.
    This leads to TAI-UTC varying continuously on that day,
    instead of being an integer number of seconds.
    See https://github.com/astropy/astropy/issues/10055

    Also note that the behavior of the unix clock is not well defined
    on the day before a leap second. Both ntp and ptp can be configured
    to make the clock jump or smear in some way.
    https://developers.redhat.com/blog/2016/12/28/leap-second-i-belong-to-you/

    In theory the datetime format could work as well as ISO format,
    but in practice it does not. The `datetime` library does not handle
    leap seconds, and the datetime representation in `astropy.time`
    raises an exception if the date has 60 in the seconds field.

    On Linux an excellent way to get *current* TAI on the day of a leap second
    is to configure ntp or ptp to maintain a leap second table, then use
    the ``CLOCK_TAI`` clock (which is only available on Linux).

    The leap second table is automatically updated.
    """
    if isinstance(utc, float) and format == "unix":
        utc_unix = utc
    elif isinstance(utc, astropy.time.Time):
        utc_unix = utc.unix
    else:
        utc_unix = astropy.time.Time(utc, scale="utc", format=format).unix
    return tai_from_utc_unix(utc_unix)


def tai_from_utc_unix(utc_unix):
    """Return TAI in unix seconds, given UTC in unix seconds.

    Parameters
    ----------
    utc_unix : `float`
        UTC time in unix seconds.

    Returns
    -------
    tai_unix : `float`
        TAI time in unix seconds.

    Raises
    ------
    ValueError
        If the date is earlier than 1972 (which is before integer leap seconds)
        or within one day of the expiration date of the leap second table
        (which is automatically updated).

    Notes
    -----
    See the notes for `tai_from_utc` for information about
    possibly unexpected behavior on the day before a leap second.
    """
    # Use a local pointer, to prevent race conditions while the
    # global table is being replaced by `_update_leap_second_table`.
    leap_second_table = _LEAP_SECOND_TABLE
    if utc_unix > leap_second_table[-1][0] - SECONDS_PER_DAY:
        raise ValueError(
            f"{utc_unix} > expiry date of leap second table - 1 day "
            f"= {leap_second_table[-1][0] - SECONDS_PER_DAY}"
        )
    i = bisect.bisect(leap_second_table, (utc_unix, math.inf))
    if i == 0:
        raise ValueError(
            f"{utc_unix} < start of integer leap seconds "
            f"= {leap_second_table[0][0]}"
        )
    utc0, tai_minus_utc0 = leap_second_table[i - 1]
    utc1, tai_minus_utc1 = leap_second_table[i]
    if utc_unix + SECONDS_PER_DAY > utc1 and tai_minus_utc1 is not None:
        # Assume unix seconds is smeared uniformly on the day before a
        # leap second, so that there are exactly 86400 seconds in the day.
        # Otherwise unix seconds is ambiguous at the leap second.
        # This matches AstroPy and Standards of Fundamental Astronomy (SOFA).
        utc_days = utc_unix / SECONDS_PER_DAY
        frac_day = utc_days - math.floor(utc_days)
        tai_minus_utc = tai_minus_utc0 + (tai_minus_utc1 - tai_minus_utc0) * frac_day
    else:
        tai_minus_utc = tai_minus_utc0
    return utc_unix + tai_minus_utc


_log = logging.getLogger("lsst.ts.salobj.base")


def _update_leap_second_table():
    """Update the leap second table.

    Notes
    -----
    This should be called when this module is loaded.
    When called, it obtains the current table from AstroPy,
    then schedules a background (daemon) thread to call itself
    to update the table ``_LEAP_SECOND_TABLE_UPDATE_MARGIN_DAYS``
    before the table expires.

    The leap table will typically have an expiry date that is
    many months away, so it will be rare for auto update to occur.
    """
    _log.info("Update leap second table")
    global _LEAP_SECOND_TABLE, _LEAP_SECOND_TABLE_UPDATE_TIMER
    ap_table = astropy.utils.iers.LeapSeconds.auto_open()
    lp_list = [
        (
            astropy.time.Time(
                datetime.datetime(row["year"], row["month"], 1, 0, 0, 0), scale="utc"
            ).unix,
            row["tai_utc"],
        )
        for row in ap_table
        if row["year"] >= 1972
    ]
    expiry_date_utc_unix = ap_table.expires.unix
    lp_list.append((expiry_date_utc_unix, None))
    _LEAP_SECOND_TABLE = lp_list

    update_date = (
        expiry_date_utc_unix - _LEAP_SECOND_TABLE_UPDATE_MARGIN_DAYS * SECONDS_PER_DAY
    )
    update_delay = update_date - time.time()
    if _LEAP_SECOND_TABLE_UPDATE_TIMER is not None:
        _LEAP_SECOND_TABLE_UPDATE_TIMER.cancel()
    _log.debug(
        f"Schedule a timer to call _update_leap_second_table in {update_delay} seconds"
    )
    _LEAP_SECOND_TABLE_UPDATE_TIMER = threading.Timer(
        update_delay, _update_leap_second_table
    )
    _LEAP_SECOND_TABLE_UPDATE_TIMER.daemon = True
    _LEAP_SECOND_TABLE_UPDATE_TIMER.start()


_update_leap_second_table()

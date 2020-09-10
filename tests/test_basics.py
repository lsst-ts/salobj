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

import datetime
import getpass
import os
import random
import socket
import time
import unittest

import asynctest

import astropy.time
from astropy.coordinates import Angle
import astropy.units as u

from lsst.ts import salobj
import lsst.ts.salobj.base


def alternate_tai_from_utc_unix(utc_unix):
    """Compute TAI in unix seconds given UTC in unix seconds.

    Parameters
    ----------
    utc_unix : `float`

    This is not the implementation in base.py for two reasons:

    * It is too slow; it slows tests/test_speed.py by a factor of 8.
    * It blocks while downloading a leap second table.
    """
    ap_time = astropy.time.Time(utc_unix, scale="utc", format="unix")
    return ap_time.tai.mjd * salobj.SECONDS_PER_DAY - salobj.MJD_MINUS_UNIX_SECONDS


class BasicsTestCase(asynctest.TestCase):
    def setUp(self):
        salobj.set_random_lsst_dds_partition_prefix()

    async def test_assert_raises_ack_error(self):
        """Test the assertRaisesAckError function.
        """
        async with salobj.Domain() as domain:
            salinfo = salobj.SalInfo(domain, "Test", index=1)
            private_seqNum = 5
            ack = 23
            error = -6
            result = "a result"
            err = salobj.AckError(
                "a message",
                ackcmd=salinfo.make_ackcmd(
                    private_seqNum=private_seqNum, ack=ack, error=error, result=result
                ),
            )
            self.assertEqual(err.ackcmd.private_seqNum, private_seqNum)
            self.assertEqual(err.ackcmd.ack, ack)
            self.assertEqual(err.ackcmd.error, error)
            self.assertEqual(err.ackcmd.result, result)

            for ExceptionClass in (
                Exception,
                TypeError,
                KeyError,
                RuntimeError,
                AssertionError,
            ):
                with self.assertRaises(ExceptionClass):
                    with salobj.assertRaisesAckError():
                        raise ExceptionClass(
                            "assertRaisesAckError should ignore other exception types"
                        )

            with self.assertRaises(AssertionError):
                with salobj.assertRaisesAckError(ack=5):
                    raise salobj.AckError(
                        "mismatched ack",
                        ackcmd=salinfo.make_ackcmd(private_seqNum=1, ack=1),
                    )

            with self.assertRaises(AssertionError):
                with salobj.assertRaisesAckError(error=47):
                    raise salobj.AckError(
                        "mismatched error",
                        ackcmd=salinfo.make_ackcmd(private_seqNum=2, ack=25, error=2),
                    )

            with salobj.assertRaisesAckError():
                raise salobj.AckError(
                    "no ack or error specified",
                    ackcmd=salinfo.make_ackcmd(private_seqNum=3, ack=1, error=2),
                )

            result = "result for this exception"
            # test result_contains with the full result string
            with salobj.assertRaisesAckError(ack=1, error=2, result_contains=result):
                raise salobj.AckError(
                    "match ack, error and full result",
                    ackcmd=salinfo.make_ackcmd(
                        private_seqNum=4, ack=1, error=2, result=result
                    ),
                )
            # test result_contains with a substring of the result string
            with salobj.assertRaisesAckError(
                ack=1, error=2, result_contains=result[2:-2]
            ):
                raise salobj.AckError(
                    "match ack, error and a substring of result",
                    ackcmd=salinfo.make_ackcmd(
                        private_seqNum=4, ack=1, error=2, result=result
                    ),
                )

    async def test_ack_error_repr(self):
        """Test AckError.__str__ and AckError.__repr__"""
        async with salobj.Domain() as domain:
            salinfo = salobj.SalInfo(domain, "Test", index=1)
            msg = "a message"
            private_seqNum = 5
            ack = 23
            error = -6
            result = "a result"
            err = salobj.AckError(
                msg,
                ackcmd=salinfo.make_ackcmd(
                    private_seqNum=private_seqNum, ack=ack, error=error, result=result
                ),
            )
            str_err = str(err)
            for item in (msg, private_seqNum, ack, error, result):
                self.assertIn(str(item), str_err)
            self.assertNotIn("AckError", str_err)
            repr_err = repr(err)
            for item in ("AckError", msg, private_seqNum, ack, error, result):
                self.assertIn(str(item), repr_err)

    def test_astropy_time_from_tai_unix(self):
        # Check the function at a leap second transition,
        # since that is likely to cause problems
        unix_time0 = datetime.datetime.fromisoformat("2017-01-01").timestamp()
        for dt in (-1, -0.5, -0.1, 0, 0.1, 1):
            with self.subTest(dt=dt):
                utc_unix = unix_time0 + dt
                tai_unix = salobj.tai_from_utc(utc_unix)
                astropy_time1 = salobj.astropy_time_from_tai_unix(tai_unix)
                self.assertIsInstance(astropy_time1, astropy.time.Time)
                self.assertEqual(astropy_time1.scale, "tai")
                tai_unix_round_trip1 = salobj.tai_from_utc(astropy_time1)
                self.assertAlmostEqual(tai_unix, tai_unix_round_trip1, delta=1e-6)

    async def test_get_opensplice_version(self):
        ospl_version = salobj.get_opensplice_version()
        self.assertRegex(ospl_version, r"^\d+\.\d+\.\d+")

    async def test_get_user_host(self):
        expected_user_host = getpass.getuser() + "@" + socket.getfqdn()
        user_host = salobj.get_user_host()
        self.assertEqual(expected_user_host, user_host)

    async def test_long_ack_result(self):
        async with salobj.Domain() as domain:
            salinfo = salobj.SalInfo(domain, "Test", index=1)
            ack = salobj.SalRetCode.CMD_FAILED
            error = 15
            long_result = (
                "this string is longer than MAX_RESULT_LEN characters "
                "this string is longer than MAX_RESULT_LEN characters "
                "this string is longer than MAX_RESULT_LEN characters "
                "this string is longer than MAX_RESULT_LEN characters "
                "this string is longer than MAX_RESULT_LEN characters "
            )
            self.assertGreater(len(long_result), salobj.MAX_RESULT_LEN)
            with self.assertRaises(ValueError):
                salinfo.make_ackcmd(
                    private_seqNum=1,
                    ack=ack,
                    error=error,
                    result=long_result,
                    truncate_result=False,
                )
            ackcmd = salinfo.make_ackcmd(
                private_seqNum=2,
                ack=ack,
                error=error,
                result=long_result,
                truncate_result=True,
            )
            self.assertEqual(ackcmd.result, long_result[0 : salobj.MAX_RESULT_LEN])
            self.assertEqual(ackcmd.ack, ack)
            self.assertEqual(ackcmd.error, error)

    def test_set_random_lsst_dds_domain(self):
        """Test that set_random_lsst_dds_domain is a deprecated
        alias for set_random_lsst_dds_partition_prefix.
        """
        old_prefix = os.environ["LSST_DDS_PARTITION_PREFIX"]
        with self.assertWarns(DeprecationWarning):
            salobj.set_random_lsst_dds_domain()
        new_prefix = os.environ["LSST_DDS_PARTITION_PREFIX"]
        self.assertNotEqual(old_prefix, new_prefix)

    def test_set_random_lsst_dds_partition_prefix(self):
        random.seed(42)
        NumToTest = 1000
        names = set()
        for i in range(NumToTest):
            salobj.set_random_lsst_dds_partition_prefix()
            name = os.environ.get("LSST_DDS_PARTITION_PREFIX")
            self.assertTrue(name)
            names.add(name)
        # any duplicate names will reduce the size of names
        self.assertEqual(len(names), NumToTest)

    async def test_domain_attr(self):
        async with salobj.Domain() as domain:
            self.assertEqual(domain.origin, os.getpid())

            self.assertEqual(domain.user_host, salobj.get_user_host())
            self.assertEqual(domain.default_identity, domain.user_host)

    def test_index_generator(self):
        with self.assertRaises(ValueError):
            salobj.index_generator(1, 1)  # imin >= imax
        with self.assertRaises(ValueError):
            salobj.index_generator(1, 0)  # imin >= imax
        with self.assertRaises(ValueError):
            salobj.index_generator(0, 5, -1)  # i0 < imin
        with self.assertRaises(ValueError):
            salobj.index_generator(0, 5, 6)  # i0 > imax

        imin = -2
        imax = 5
        gen = salobj.index_generator(imin=imin, imax=imax)
        expected_values = [-2, -1, 0, 1, 2, 3, 4, 5, -2, -1, 0, 1, 2, 3, 4, 5, -2]
        values = [next(gen) for i in range(len(expected_values))]
        self.assertEqual(values, expected_values)

        imin = -2
        imax = 5
        i0 = 5
        expected_values = [5, -2, -1, 0, 1, 2, 3, 4, 5, -2]
        gen = salobj.index_generator(imin=imin, imax=imax, i0=i0)
        values = [next(gen) for i in range(len(expected_values))]
        self.assertEqual(values, expected_values)

    def test_name_to_name_index(self):
        for name, expected_result in (
            ("Script", ("Script", 0)),
            ("Script:0", ("Script", 0)),
            ("Script:15", ("Script", 15)),
            ("MTM1M3", ("MTM1M3", 0)),
            ("MTM1M3:47", ("MTM1M3", 47)),
        ):
            with self.subTest(name=name):
                result = salobj.name_to_name_index(name)
                self.assertEqual(result, expected_result)

        for bad_name in (
            (" Script:15"),  # leading space
            ("Script:15 "),  # trailing space
            ("Script:"),  # colon with no index
            ("Script:zero"),  # index is not an integer
        ):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ValueError):
                    salobj.name_to_name_index(bad_name)

    def check_tai_from_utc(self, utc_ap):
        """Check tai_from_utc at a specific UTC date.

        Parameters
        ----------
        utc_ap : `astropy.time.Time`
            UTC date as an astropy time.
        """
        tai = salobj.tai_from_utc(utc_ap.utc.unix)

        tai_alt = alternate_tai_from_utc_unix(utc_ap.utc.unix)
        self.assertAlmostEqual(tai, tai_alt, delta=1e-6)

        tai2 = salobj.tai_from_utc(utc_ap.utc.iso, format="iso")
        self.assertAlmostEqual(tai, tai2, delta=1e-6)

        tai3 = salobj.tai_from_utc(utc_ap.utc.iso, format=None)
        self.assertAlmostEqual(tai, tai3, delta=1e-6)

        tai4 = salobj.tai_from_utc(utc_ap.utc.mjd, format="mjd")
        self.assertAlmostEqual(tai, tai4, delta=1e-6)

        tai_mjd = (tai + salobj.MJD_MINUS_UNIX_SECONDS) / salobj.SECONDS_PER_DAY
        tai_mjd_ap = astropy.time.Time(tai_mjd, scale="tai", format="mjd")
        tai5 = salobj.tai_from_utc(tai_mjd_ap)
        self.assertAlmostEqual(tai, tai5, delta=1e-6)

        tai_iso_ap = astropy.time.Time(utc_ap.tai.iso, scale="tai", format="iso")
        tai6 = salobj.tai_from_utc(tai_iso_ap)
        self.assertAlmostEqual(tai, tai6, delta=1e-6)

        tai7 = salobj.tai_from_utc(utc_ap)
        self.assertAlmostEqual(tai, tai7, delta=1e-6)

    def test_leap_second_table(self):
        """Check that the leap second table is set and an update is scheduled.
        """
        self.assertIsNotNone(lsst.ts.salobj.base._LEAP_SECOND_TABLE)
        update_timer = lsst.ts.salobj.base._LEAP_SECOND_TABLE_UPDATE_TIMER
        self.assertTrue(update_timer.is_alive())
        self.assertTrue(update_timer.daemon)
        self.assertIs(
            update_timer.function, lsst.ts.salobj.base._update_leap_second_table
        )
        update_margin = (
            lsst.ts.salobj.base._LEAP_SECOND_TABLE_UPDATE_MARGIN_DAYS
            * salobj.SECONDS_PER_DAY
        )
        current_duration = (
            time.time() - lsst.ts.salobj.base._LEAP_SECOND_TABLE[-1][0] - update_margin
        )
        self.assertGreater(update_timer.interval, current_duration)

    def test_tai_from_utc(self):
        """Test tai_from_utc.
        """
        # Check tai_from_utc at leap second transition just before 2017-01-01
        # when leap seconds went from 36 to 37.
        utc0_ap = astropy.time.Time("2017-01-01", scale="utc", format="iso")
        for utc_ap in (
            (utc0_ap - 0.5 * u.day),
            (utc0_ap - 1 * u.second),
            (utc0_ap - 0.1 * u.second),
            (utc0_ap),
            (utc0_ap + 0.1 * u.second),
            (utc0_ap + 1 * u.second),
        ):
            with self.subTest(utc_ap=utc_ap):
                self.check_tai_from_utc(utc_ap=utc_ap)

        # Test values near the limits, which are at 1972-01-01T00:00:00
        # and one day before the current leap second table expires.
        min_utc_unix = astropy.time.Time("1972-01-01", scale="utc", format="iso").unix
        max_utc_unix = (
            lsst.ts.salobj.base._LEAP_SECOND_TABLE[-1][0] - salobj.SECONDS_PER_DAY
        )
        min_tai_unix = salobj.tai_from_utc(min_utc_unix)
        self.assertAlmostEqual(min_tai_unix, min_utc_unix + 10)
        max_tai_unix = salobj.tai_from_utc(max_utc_unix)
        # Final value of TAI-UTC in the table.
        # Note that the last entry in the table has TAI-UTC = None.
        final_tai_minus_utc = lsst.ts.salobj.base._LEAP_SECOND_TABLE[-2][1]
        self.assertAlmostEqual(max_tai_unix, max_utc_unix + final_tai_minus_utc)
        with self.assertRaises(ValueError):
            salobj.tai_from_utc(min_utc_unix - 0.001)
        with self.assertRaises(ValueError):
            salobj.tai_from_utc(max_utc_unix + 0.001)

    def test_current_tai(self):
        utc0 = time.time()
        tai0 = salobj.tai_from_utc(utc0)
        # salobj.base.current_tai_from_utc uses tai_from_utc,
        # so it should give the same answer.
        tai1 = salobj.base.current_tai_from_utc()
        # salobj.current_tai uses the system TAI clock, if available.
        # This gives the correct answer (if your operating system
        # is correctly configured) and can differ from the answer given by
        # tai_from_utc by as much as a second on the day of a leap second.
        tai2 = salobj.current_tai()
        print(f"tai1-tai0={tai1-tai0:0.4f}")
        # The difference should be much less than 0.1
        # but pytest can introduce unexpected delays.
        self.assertLess(abs(tai1 - tai0), 0.1)
        self.assertGreaterEqual(tai1, tai0)
        # The difference between the value returned by current_tai
        # and current_tai_from_utc
        self.assertLess(abs(tai2 - tai0), 1.1)
        self.assertIs(type(tai0), float)
        self.assertIs(type(tai1), float)
        self.assertIs(type(tai2), float)

    def test_angle_diff(self):
        for angle1, angle2, expected_diff in (
            (5.15, 0, 5.15),
            (5.21, 359.20, 6.01),
            (270, -90, 0),
        ):
            with self.subTest(
                angle1=angle1, angle2=angle2, expected_diff=expected_diff
            ):
                diff = salobj.angle_diff(angle1, angle2)
                self.assertAlmostEqual(diff.deg, expected_diff)
                diff = salobj.angle_diff(angle2, angle1)
                self.assertAlmostEqual(diff.deg, -expected_diff)
                diff = salobj.angle_diff(Angle(angle1, u.deg), angle2)
                self.assertAlmostEqual(diff.deg, expected_diff)
                diff = salobj.angle_diff(angle1, Angle(angle2, u.deg))
                self.assertAlmostEqual(diff.deg, expected_diff)
                diff = salobj.angle_diff(Angle(angle1, u.deg), Angle(angle2, u.deg))
                self.assertAlmostEqual(diff.deg, expected_diff)

    def test_angle_wrap_center(self):
        for base_angle, expected_result in (
            (-180.001, 179.999),
            (-180, -180),
            (0, 0),
            (179.999, 179.999),
            (180, -180),
        ):
            for nwraps in (-2, -1, 0, 1, 2):
                with self.subTest(
                    base_angle=base_angle,
                    expected_result=expected_result,
                    nwraps=nwraps,
                ):
                    angle = base_angle + 360 * nwraps
                    result = salobj.angle_wrap_center(angle)
                    self.assertAlmostEqual(result.deg, expected_result)
                    result = salobj.angle_wrap_center(Angle(angle, u.deg))
                    self.assertAlmostEqual(result.deg, expected_result)

    def test_angle_wrap_nonnegative(self):
        for base_angle, expected_result in (
            (-0.001, 359.999),
            (0, 0),
            (180, 180),
            (359.999, 359.999),
            (360, 0),
        ):
            for nwraps in (-2, -1, 0, 1, 2):
                with self.subTest(
                    base_angle=base_angle,
                    expected_result=expected_result,
                    nwraps=nwraps,
                ):
                    angle = base_angle + 360 * nwraps
                    result = salobj.angle_wrap_nonnegative(angle)
                    self.assertAlmostEqual(result.deg, expected_result)
                    result = salobj.angle_wrap_nonnegative(Angle(angle, u.deg))
                    self.assertAlmostEqual(result.deg, expected_result)

    def test_assertAnglesAlmostEqual(self):
        for angle1, angle2 in ((5.15, 5.14), (-0.20, 359.81), (270, -90.1)):
            epsilon = Angle(1e-15, u.deg)
            with self.subTest(angle1=angle1, angle2=angle2):
                diff = abs(salobj.angle_diff(angle1, angle2))
                bad_diff = diff - epsilon
                self.assertGreater(bad_diff.deg, 0)
                with self.assertRaises(AssertionError):
                    salobj.assertAnglesAlmostEqual(angle1, angle2, bad_diff)
                with self.assertRaises(AssertionError):
                    salobj.assertAnglesAlmostEqual(angle1, angle2, bad_diff.deg)
                with self.assertRaises(AssertionError):
                    salobj.assertAnglesAlmostEqual(angle2, angle1, bad_diff)
                with self.assertRaises(AssertionError):
                    salobj.assertAnglesAlmostEqual(
                        Angle(angle1, u.deg), angle2, bad_diff
                    )
                with self.assertRaises(AssertionError):
                    salobj.assertAnglesAlmostEqual(
                        angle1, Angle(angle2, u.deg), bad_diff
                    )
                with self.assertRaises(AssertionError):
                    salobj.assertAnglesAlmostEqual(
                        Angle(angle1, u.deg), Angle(angle2, u.deg), bad_diff
                    )

                good_diff = diff + epsilon
                salobj.assertAnglesAlmostEqual(angle1, angle2, good_diff)
                salobj.assertAnglesAlmostEqual(angle1, angle2, good_diff.deg)
                salobj.assertAnglesAlmostEqual(angle2, angle1, good_diff)
                salobj.assertAnglesAlmostEqual(Angle(angle1, u.deg), angle2, good_diff)
                salobj.assertAnglesAlmostEqual(angle1, Angle(angle2, u.deg), good_diff)
                salobj.assertAnglesAlmostEqual(
                    Angle(angle1, u.deg), Angle(angle2, u.deg), good_diff
                )


if __name__ == "__main__":
    unittest.main()

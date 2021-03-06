#! /usr/bin/python3
# -*- coding: utf8 -*-
# --------------------------------------------------------------------------------------------------
# pylint: disable=C0413, C0111, C0103
# --------------------------------------------------------------------------------------------------
def _SetupPath():
    import sys
    import pathlib
    root = str(pathlib.Path(__file__).parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
_SetupPath()
# --------------------------------------------------------------------------------------------------
import unittest
from datetime import datetime, timedelta, time
import sunrise
import base
from config import * # pylint: disable=W0614; unused import
# --------------------------------------------------------------------------------------------------
sdata = (
    # day, sunrise, sunset
    ( datetime(2018, 1,  1, 10, 0), time(7, 55), time(16,  5) ),
    ( datetime(2018, 3, 25,  1, 0), time(6, 54), time(19, 19) ),
    ( datetime(2018, 3, 25,  5, 0), time(6, 54), time(19, 19) ),
    ( datetime(2018, 6, 19, 12, 1), time(5,  5), time(21, 20) ),
    ( datetime(2018, 12, 31, 5, 5), time(8,  0), time(16,  0) ),
    ( datetime(2020, 2, 29, 5, 5),  time(6, 57), time(17, 40) ),
)
# --------------------------------------------------------------------------------------------------
allowed_delta = timedelta(minutes = 3)
# --------------------------------------------------------------------------------------------------
def in_range(dt, expected):
    """
    Gibt zurück, ob der Zeitpunkt `dt` im Bereich `expected` +- `allowed_delta`
    liegt.
    """
    return (dt >= expected - allowed_delta) and (dt <= expected + allowed_delta)
# --------------------------------------------------------------------------------------------------
def _norm(dt):
    """
    Entfernt Mikro- und Sekunden aus `dt` und gibt das Ergebnis zurück.
    """
    return dt.replace(second = 0, microsecond = 0)
# --------------------------------------------------------------------------------------------------
def _exp_times(today, dawn, dusk):
    """
    Liefert die erwarteten Öffnungs- / -schießzeiten am Tag `today` zu den
    Sonnenaufgangs- / -untergangszeiten `dusk` und `dawn`.
    """
    h, m = EARLIEST_OPEN_TIMES[today.weekday()]

    earliest_open_time = datetime.combine(today, time(hour = h, minute = m))
    expected_open_time = dawn + timedelta(seconds = DAWN_OFFSET)

    if expected_open_time < earliest_open_time:
        expected_open_time = earliest_open_time

    expected_close_time = dusk + timedelta(seconds = DUSK_OFFSET)
    return (expected_open_time, expected_close_time)
# --------------------------------------------------------------------------------------------------
class Test_SunriseConsistency(base.TestCase):
    def _ConsistencyTest(self, day):
        """
        Prüft die Konsistenz der Sonnenaufgangs- / -untergangszeiten über jede Minute
        des Tages `day`.
        """
        exp_dawn, exp_dusk = sunrise.CalculateSunTimes(day)
        for hour in range(0, 23):
            for minute in range(0, 59):
                t = time(hour = hour, minute = minute)
                dt = datetime.combine(day.date(), t)
                dawn, dusk = sunrise.CalculateSunTimes(dt)
                self.assertEqual(
                    dawn, exp_dawn,
                    "Dawn result at {} differs: expected {}, got {}.".format(dt, exp_dawn, dawn)
                )
                self.assertEqual(
                    dusk, exp_dusk,
                    "Dusk result at {} differs: expected {}, got {}.".format(dt, exp_dusk, dusk)
                )

    def test_Consistency(self):
        for day in (datetime(2018, 3, 25, 14, 23),
                    datetime(2018, 10, 28, 1, 1),
                    datetime(2018, 8, 25, 11, 16)):
            self._ConsistencyTest(day)
# --------------------------------------------------------------------------------------------------
class Test_SunriseTimes(base.TestCase):
    def test_Times(self):
        """
        Prüft die Berechnung der Sonnenaufgangs- / -untergangszeiten gegen
        sdate.
        """
        for day, dawn, dusk in sdata:
            today = day.date()
            dawn = datetime.combine(today, dawn)
            dusk = datetime.combine(today, dusk)
            (expected_open_time, expected_close_time) = _exp_times(today, dawn, dusk)
            open_time, close_time = sunrise.GetSuntimes(day)
            open_time = _norm(open_time)
            close_time = _norm(close_time)

            self.assertTrue(
                in_range(open_time, expected_open_time),
                "At {} open time {} is in range ({} +- {})".format(
                    today, open_time, expected_open_time, allowed_delta
                )
            )

            self.assertTrue(
                in_range(close_time, expected_close_time),
                "At {} close time {} is in range ({} +- {})".format(
                    today, close_time, expected_close_time, allowed_delta
                )
            )
# --------------------------------------------------------------------------------------------------
class Test_DoorActions(base.TestCase):
    def test_DoorActions(self):
        """
        Prüft sunrise.GetDoorAction():
            - kein Zustandswechsel innerhalb eines 5 Stunden Fensters
            - Öffnungszeit zwischen Sonnenauf- und -untergang (angepasst)
            - geprüft wird minütlich in den Tagen aus sdate
        """
        for day, dawn, dusk in sdata:
            prev_action = DOOR_CLOSED
            lastchange = day.replace(hour = 0, minute = 0, second = 0, microsecond = 0)
            today = day.date()
            dawn = datetime.combine(today, dawn)
            dusk = datetime.combine(today, dusk)
            (open_time, close_time) = _exp_times(today, dawn, dusk)
            for hour in range(0, 23):
                for minute in range(0, 59):
                    t = time(hour = hour, minute = minute)
                    dt = datetime.combine(today, t)
                    action = sunrise.GetDoorAction(dt, open_time, close_time)
                    if dt >= open_time and dt < close_time:
                        expected_action = DOOR_OPEN
                    else:
                        expected_action = DOOR_CLOSED

                    self.assertTrue(
                        expected_action == action,
                        "At {} expected door to be {}, but is {}".format(
                            dt, expected_action, action
                        )
                    )
                    if action == prev_action:
                        continue

                    self.assertGreater(
                        dt, lastchange + timedelta(hours = 5),
                        "Unexpected door state switch within 5 hours at {}".format(dt)
                    )
# --------------------------------------------------------------------------------------------------
class Test_NextActions(base.TestCase):
    def test_NextActions(self):
        """
        Prüft die Ermittlung der nächsten Aktionen (sunrise.GetNextActions):
            - geprüft wird minütlich in den Tagen aus sdate
            - die jeweils nächste Operation muss mit den Zeiten aus sdate übereinstimmen
        """
        for day, dawn, dusk in sdata:
            today = day.date()
            dawn = datetime.combine(today, dawn)
            dusk = datetime.combine(today, dusk)
            (open_time, close_time) = _exp_times(today, dawn, dusk)
            for hour in range(0, 23):
                for minute in range(0, 59):
                    t = time(hour = hour, minute = minute)
                    dt = datetime.combine(today, t)
                    next_actions = sunrise.GetNextActions(dt, open_time, close_time)
                    self.assertEqual(
                        len(next_actions), 2,
                        "Expected 2 actions as result of GetNextActions(), " +
                        "got: {}".format(next_actions)
                    )

                    a1, a2 = next_actions

                    self.assertEqual(
                        len(a1), 2,
                        "Expected 2 items in step, got: {}".format(a1)
                    )

                    self.assertEqual(
                        len(a2), 2,
                        "Expected 2 items in step, got: {}".format(a2)
                    )

                    ntime, naction = a1
                    ntime = _norm(ntime)

                    if dt < open_time:
                        self.assertEqual(
                            naction, DOOR_OPEN,
                            "(1) Expected {} as next action at {}, got: {}".format(
                                DOOR_OPEN, dt, naction
                            )
                        )
                        self.assertEqual(
                            open_time, ntime,
                            "(1) Expected {} as next action time at {}, got: {}".format(
                                open_time, dt, ntime
                            )
                        )
                        continue

                    if dt < close_time:
                        self.assertEqual(
                            naction, DOOR_CLOSED,
                            "(2) Expected {} as next action at {}, got: {}".format(
                                DOOR_CLOSED, dt, naction
                            )
                        )
                        self.assertEqual(
                            close_time, ntime,
                            "(2) Expected {} as next action time at {}, got: {}".format(
                                close_time, dt, ntime
                            )
                        )
                        continue

                    # jetzt sind wir schon am Folgetag
                    self.assertEqual(
                        naction, DOOR_OPEN,
                        "(3) Expected {} as next action at {}, got: {}.".format(
                            DOOR_OPEN, dt, a1
                        )
                    )
# --------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()
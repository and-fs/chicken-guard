#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import * # pylint: disable=W0614
from datetime import datetime, timedelta, time, date
import sunrise
# ---------------------------------------------------------------------------------------
sdata = (
    # day, sunrise, sunset
    ( datetime(2018, 1,  1, 10, 0), time(7, 55), time(16,  5) ),
    ( datetime(2018, 3, 25,  1, 0), time(6, 54), time(19, 19) ),
    ( datetime(2018, 3, 25,  5, 0), time(6, 54), time(19, 19) ),
    ( datetime(2018, 6, 19, 12, 1), time(5,  5), time(21, 20) ),
    ( datetime(2018, 12, 31, 5, 5), time(8,  0), time(16,  0) ),
    ( datetime(2020, 2, 29, 5, 5),  time(6, 57), time(17, 40) ),    
)
# ---------------------------------------------------------------------------------------
allowed_delta = timedelta(minutes = 3)
# ---------------------------------------------------------------------------------------
def in_range(dt, expected):
    """
    Gibt zurück, ob der Zeitpunkt `dt` im Bereich `expected` +- `allowed_delta`
    liegt.
    """
    return (dt >= expected - allowed_delta) and (dt <= expected + allowed_delta)
# ---------------------------------------------------------------------------------------
def _norm(dt):
    """
    Entfernt Mikro- und Sekunden aus `dt` und gibt das Ergebnis zurück.
    """
    return dt.replace(second = 0, microsecond = 0)
# ---------------------------------------------------------------------------------------
def test_consistency(day):
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
            if dawn != exp_dawn:
                check(False, "Dawn result at %s differs: expected %s, got %s.", dt, exp_dawn, dawn)
            if dusk != exp_dusk:
                check(False, "Dusk result at %s differs: expected %s, got %s.", dt, exp_dusk, dusk)
    check(True, "Consistency check for %s", day)
# ---------------------------------------------------------------------------------------
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
# ---------------------------------------------------------------------------------------
def test_times():
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

        check(in_range(open_time, expected_open_time), "At %s open time %s is in range (%s +- %s)", today, open_time, expected_open_time, allowed_delta)
        check(in_range(close_time, expected_close_time), "At %s close time %s is in range (%s +- %s)", today, close_time, expected_close_time, allowed_delta)
# ---------------------------------------------------------------------------------------
def test_dooraction():
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
                if expected_action != action:
                    check(False, "At %s expected door to be %s, but is %s", dt, expected_action, action)
                if action == prev_action:
                    continue
                if lastchange + timedelta(hours = 5) > dt:
                    check(False, "Unexpected door state switch within 5 hours at %s", dt)
        check(True, "Door action check at %s.", today)
# ---------------------------------------------------------------------------------------
@testfunction
def test():
    test_consistency(datetime(2018, 3, 25, 14, 23))
    test_consistency(datetime(2018, 10, 28, 1, 1))
    test_consistency(datetime(2018, 8, 25, 11, 16))
    test_times()
    test_dooraction()
    return True
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()
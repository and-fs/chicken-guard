#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Script berechnet die Sonnenaufgangs / -untergangsdaten für die
kommenden 7 Tage und legt das Ergebnis unter resources/sunset.data
als Tab-getrennte Werte ab.

Beispiel::
17.09.2018	06:48	19:11
18.09.2018	06:50	19:09
19.09.2018	06:53	19:06
20.09.2018	06:55	19:04
21.09.2018	06:57	19:02
22.09.2018	07:00	18:59
23.09.2018	07:02	18:57
24.09.2018	07:04	18:55
25.09.2018	07:07	18:52
26.09.2018	07:09	18:50
"""
# ------------------------------------------------------------------------
import math
import datetime
import time
import os
# ------------------------------------------------------------------------
import shared
from shared import LoggableClass
from config import * # pylint: disable=W0614
# ------------------------------------------------------------------------
LATITUDE_IN_RAD = math.radians(LATITUDE)
SUNSET_HEIGHT = math.radians(-(50.0/60.0))
# ------------------------------------------------------------------------
def sunDeclination(day_of_year):
    return 0.409526325277017 * math.sin(0.0169060504029192 * (day_of_year - 80.0856919827619))
# ------------------------------------------------------------------------
def sunTimeDiff(day_of_year):
    return (-0.170869921174742 * math.sin(0.0336997028793971 * day_of_year + 0.465419984181394)
           - 0.129890681040717 * math.sin(0.0178674832556871 * day_of_year - 0.167936777524864))
# ------------------------------------------------------------------------
def localTimeDiff(declination, latitude_in_rad):
    return (12.0 * math.acos(
                (math.sin(SUNSET_HEIGHT) - math.sin(latitude_in_rad) * math.sin(declination))
                / (math.cos(latitude_in_rad)*math.cos(declination))
            ) / math.pi)         
# ------------------------------------------------------------------------
def getSunTimes(when = None):
    """
    Liefert ein Tupel aus Sonnenaufgangs- und -untergangszeit
    für den angegebenen Tag `when`.
    Sommer-/Winterzeit wird dabei berücksichtigt.
    """
    if when is None:
        when = datetime.datetime.now()
    timetuple = when.timetuple()
    stamp = time.mktime(timetuple)
    tt = time.localtime(stamp)
    is_dst = tt.tm_isdst > 0   
    day_of_year = timetuple.tm_yday
    decl = sunDeclination(day_of_year)
    diff = localTimeDiff(decl, LATITUDE_IN_RAD) - sunTimeDiff(day_of_year)
    diff = datetime.timedelta(hours = diff)
    midday = when.replace(hour = 12 + (1 if is_dst else 0), minute = 0, second = 0, microsecond = 0)
    sunset = (midday - diff) 
    sunrise = (midday + diff)
    return sunset, sunrise
# ------------------------------------------------------------------------
def GetSuntimes(current_datetime):
    """
    Liefert die Schaltzeiten für die Tür an dem Tag des Datums
    von current_datatime.
    """
    dawn, dusk = getSunTimes(current_datetime)
    hour, minute = EARLIEST_OPEN_TIMES.get(current_datetime.weekday(), (5, 30))
    dawn = dawn.replace(hour = hour, minute = minute)
    dawn += datetime.timedelta(seconds = DAWN_OFFSET)
    dusk += datetime.timedelta(seconds = DUSK_OFFSET)
    return dawn, dusk
# ------------------------------------------------------------------------
def GetDoorAction(current_datetime, dawn, dusk):
    if (current_datetime < dawn):
        # wir sind noch vor dem Sonnenaufgang
        return DOOR_CLOSED
    if (current_datetime < dusk):
        # wir sind nach Sonnenauf- aber vor Sonnenuntergang
        return DOOR_OPEN
    return DOOR_CLOSED
# ------------------------------------------------------------------------
def test():
    sunset, sunrise = getSunTimes()
    print ("Am {sunset:%d.%m.%Y} geht die Sonne {sunset:%H:%M} Uhr auf und {sunrise:%H:%M} unter.".format(sunset = sunset, sunrise = sunrise))
# ------------------------------------------------------------------------
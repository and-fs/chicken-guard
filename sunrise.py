#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Funktionen zur Berechnung der Sonnenzeiten und abhängiger Türzustände.
"""
# --------------------------------------------------------------------------------------------------
import math
import datetime
import time
# --------------------------------------------------------------------------------------------------
from config import * # pylint: disable=W0614
# --------------------------------------------------------------------------------------------------
#: Längengrad des Standorts in RAD.
LATITUDE_IN_RAD = math.radians(LATITUDE)
# --------------------------------------------------------------------------------------------------
def _SunDeclination(day_of_year:int):
    return 0.409526325277017 * math.sin(0.0169060504029192 * (day_of_year - 80.0856919827619))
# --------------------------------------------------------------------------------------------------
def _SunTimeDiff(day_of_year:int):
    return (
        -0.170869921174742 * math.sin(0.0336997028793971 * day_of_year + 0.465419984181394)
        - 0.129890681040717 * math.sin(0.0178674832556871 * day_of_year - 0.167936777524864)
    )
# --------------------------------------------------------------------------------------------------
def _LocalTimeDiff(declination:float, latitude_in_rad:float)->float:
    return (
        12.0 * math.acos(
            (
                math.sin(math.radians(-(50.0/60.0))) -
                math.sin(latitude_in_rad) * math.sin(declination)
            ) / (
                math.cos(latitude_in_rad) * math.cos(declination)
            )
        ) / math.pi
    )
# --------------------------------------------------------------------------------------------------
def CalculateSunTimes(when:datetime.datetime = None)->tuple:
    """
    Liefert ein Tupel aus Sonnenaufgangs- und -untergangszeit
    für den angegebenen Tag ``when``.

    Sommer-/Winterzeit wird dabei berücksichtigt, aber für den fragenden Tag
    gilt immer die Zeitzone, in der Sonnenaufgang- und -untergang stattfinden.

    :param datetime.datetime when: Tag für den die Sonnenzeiten berechnet werden sollen.
        Die enthaltene Zeit wird auf 12:00 Mittags gesetzt.
        Wenn nicht angegeben, wird der aktuelle Tag verwendet.

    :returns: Tuple aus Sonnenaufgang- und -untergangszeit, jeweils als ``datetime``.
    """
    if when is None:
        when = datetime.datetime.now()
    when = when.replace(hour = 12, minute = 0, second = 0, microsecond = 0)
    timetuple = when.timetuple()
    stamp = time.mktime(timetuple)
    tt = time.localtime(stamp)
    is_dst = tt.tm_isdst > 0
    day_of_year = timetuple.tm_yday
    decl = _SunDeclination(day_of_year)
    diff = _LocalTimeDiff(decl, LATITUDE_IN_RAD) - _SunTimeDiff(day_of_year)
    diff = datetime.timedelta(hours = diff)
    if is_dst:
        when += datetime.timedelta(hours = 1)
    sunset = (when - diff)
    sunrise = (when + diff)
    return (sunset, sunrise)
# --------------------------------------------------------------------------------------------------
def GetSuntimes(current_datetime):
    """
    Liefert die Schaltzeiten für die Tür an dem Tag des Datums
    von current_datatime.
    """
    dawn, dusk = CalculateSunTimes(current_datetime)
    dawn += datetime.timedelta(seconds = DAWN_OFFSET)
    hour, minute = EARLIEST_OPEN_TIMES.get(current_datetime.weekday(), (5, 30))
    eot = datetime.time(hour = hour, minute = minute)
    if eot > dawn.time():
        dawn = dawn.replace(hour = hour, minute = minute)
    dusk += datetime.timedelta(seconds = DUSK_OFFSET)
    return dawn, dusk
# --------------------------------------------------------------------------------------------------
def GetDoorAction(
        dtcurrent:datetime.datetime,
        open_time:datetime.datetime,
        close_time:datetime.datetime
    )->int:
    """
    Liefert den erwarteten Zustand der Zür zu einem Zeitpunkt ``dtcurrent``
    wenn die Tür zwischen ``open_time`` und ``close_time`` geöffnet sein soll.

    :param datetime.datetime dtcurrent: Der Zeitpunkt, zu der Zustand der Tür ermittelt werden soll.

    :param datetime.datetime open_time: Zeitpunkt, an dem die Tür geöffnet wird. Liegt idealer-
        weise vor ``close_time``.

    :param datetime.datetime close_time: Zeitpunkt, an dem die Tür geschlossen wird. Liegt nach
        ``open_time``.

    :returns: Der erwartete Zustand der Tür, also entweder :data:`config.DOOR_CLOSED` oder
        :data:`config.DOOR_OPEN`.
    """
    if dtcurrent < open_time:
        # wir sind noch vor der Öffnungszeit
        return DOOR_CLOSED
    if dtcurrent < close_time:
        # wir sind nach Öffnungs- aber vor Schließungszeit
        return DOOR_OPEN
    # es ist nach Schließungszeit
    return DOOR_CLOSED
# --------------------------------------------------------------------------------------------------
def GetNextActions(
        current_datetime:datetime.datetime,
        open_time:datetime.datetime,
        close_time:datetime.datetime
    )->tuple:
    """
    Liefert die nächsten beiden Türaktionen ausgehend von der
    Zeit ``current_datetime``.

    :param datetime.datetime current_datetime: Zeitpunkt, ab dem die Schritte ermittelt
            werden sollen.

    :param datetime.datetime open_time: Zeitpunkt des Öffnens der Tür an dem Tag,
            in dem ``current_datetime`` liegt.

    :param datetime.datetime close_time: Zeitpunkt des Schließens der Tür an dem Tag,
            in dem ``current_datetime`` liegt.

    :returns: Ein Tuple mit genau zwei Werten, jeder Wert wiederum ein Tuple.
        Das erste Element ist der Schaltzeitpunkt (``datetime.datetime``), das zweite
        die durchzuführende Aktion (:data:`config.OPEN_DOOR`, :data:`config.CLOSE_DOOR`).

        Beispiel::
            ((datetime(2018, 9, 28, 6, 36, 0), OPEN_DOOR),
             (datetime(2018, 9, 28, 18, 30, 0), CLOSE_DOOR))
    """
    if current_datetime < open_time:
        # aktuell sind wir noch vor der Öffnungszeit des aktuellen
        # Tages, damit haben wir alles
        return ((open_time, DOOR_OPEN),
                (close_time, DOOR_CLOSED))

    # jetzt müssen wir uns noch den nächsten Tag holen
    n_open_time, n_close_time = GetSuntimes(current_datetime + datetime.timedelta(days = 1))
    if current_datetime < close_time:
        # wir sind vor der Schließzeit am aktuellen Tag
        return ((close_time, DOOR_CLOSED),
                (n_open_time, DOOR_OPEN))

    # wir befinden uns nach der Schließzeit des aktuellen oder Vortag
    return ((n_open_time, DOOR_OPEN),
            (n_close_time, DOOR_CLOSED))
# --------------------------------------------------------------------------------------------------

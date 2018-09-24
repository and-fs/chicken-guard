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
    sunset = (midday - diff) + datetime.timedelta(seconds = DAWN_OFFSET)
    sunrise = (midday + diff) + datetime.timedelta(seconds = DUSK_OFFSET)
    return sunset, sunrise
# ------------------------------------------------------------------------
class SunTimesFile(LoggableClass):

    def __init__(self, fpath = None):
        LoggableClass.__init__(self, name = "sunrise")
        #: Datetime-Format für die Tagesangabe
        self.day_format = '%d.%m.%Y'
        #: Datetime-Format für die Zeiangabe
        self.time_format = '%H:%M'
        #: Separator für die Datetimefelder pro Zeile
        self.field_sep = '\t'
        #: Template für eine Zeile in der Datendatei.
        self.line_tpl = "{0:%s}%s{1:%s}%s{2:%s}%s" % (
            self.day_format, self.field_sep,
            self.time_format, self.field_sep,
            self.time_format, os.linesep
        )
        #: Datendatei
        self.datafile = shared.resource_path.joinpath(SUNSETFILE) if (fpath is None) else fpath

    def write(self, days = 10):
        """
        Schreibt die Sonnenaufgangs- / -untergangszeiten der nächsten 'days' Tage
        in die konfigurierte Datei (config.SUNSETFILE) im Ressourcenverzeichnis
        (shared.resource_path).

        Falls die bestehende Datei jünger als die aktuelle Zeit ist (RPi hat nach
        einem Hochfahren noch keine aktuelle Zeit erhalten), wird die Aktion
        abgebrochen.
        """
        now = datetime.datetime.now()

        self.info("Calculating times into data file %s.", self.datafile)

        # als erstes schauen wir nach, wann das letzte Mal eine
        # Aktualisierung der Datei stattgefunden hat.
        if self.datafile.exists():
            self.debug("Datafile already exists, checking time.")
            # falls die letzte Aktualisierung der Datei neuer(!)
            # ist als die aktuelle Zeit, wurde der PI neu gestartet
            # und hat (noch) keine aktuelle Zeit.
            # in diesem Fall brechen wir ab
            filetime = datetime.datetime.fromtimestamp(self.datafile.stat().st_mtime)
            if now < filetime:
                self.warn("Sunrise data file time (%s) is newer then current time (%s), aborting this run.", filetime.ctime(), now.ctime())
                return -1
        else:
            self.debug("Datafile doesn't exist, creating a new one.")

        self.info("Calculating sunrise data.")

        current = now.replace(hour = 12)
        daydiff = datetime.timedelta(days = 1)

        with self.datafile.open("w") as f:
            for _ in range(days):
                (sunrise, sunset) = getSunTimes(current)
                f.write(self.line_tpl.format(current, sunrise, sunset))
                current += daydiff

        self.info("Finished.")

    def read(self):
        """
        Liest die aktuell geschriebenen Zeiten.
        """
        # als erstes schauen wir nach, wann das letzte Mal eine
        # Aktualisierung der Datei stattgefunden hat.
        if not self.datafile.exists():
            self.info("Cannot read times from data file '%s', currently not existing.", self.datafile)
            return []

        self.info("Reading times from data file %s.", self.datafile)
        result = []
        with self.datafile.open('r') as f:
            for linenum, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    current, sunrise, sunset = line.split(self.field_sep)
                    current = datetime.datetime.strptime(current, self.day_format)
                    sunrise = datetime.datetime.strptime(sunrise, self.time_format)
                    sunset = datetime.datetime.strptime(sunset, self.time_format)
                except ValueError:
                    self.exception('Error in datafile at line %d: %r!', linenum, line)
                    continue
                result.append((current, sunrise, sunset))
        self.info("Finished reading, read %d times.", len(result))
        return result
# ------------------------------------------------------------------------
def test():
    sunset, sunrise = getSunTimes()
    print ("Am {sunset:%d.%m.%Y} geht die Sonne {sunset:%H:%M} Uhr auf und {sunrise:%H:%M} unter.".format(sunset = sunset, sunrise = sunrise))
# ------------------------------------------------------------------------
if __name__ == "__main__":
    print(SunTimesFile().read())
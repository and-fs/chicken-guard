#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Enthält die in der Steuerung verwendeten Konfigurationsdaten.

Diese sind über die :class:`shared.Config` - Klasse nachladbar.
"""
# ------------------------------------------------------------------------
#: Intervall, in dem die Sonnenaufgangs / Untergangszeiten berechnet werden
#: (in Sekunden)
SUNRISE_INTERVAL = 7000

#: Prüfintervall des Türstatus (Öffnen / Schließen) in Sekunden
DOORCHECK_INTERVAL = 60

#: Intervall in dem die Messergebnisse der Sensoren erfasst werden in Sekunden.
SENSOR_INTERVALL = 5 * 60

#: Dauer in Sekunden die die Türautomatik bei manueller Bedienung deaktiviert
#: wird.
DOOR_AUTOMATIC_OFFTIME = 30 * 60

#: Anzahl Sekunden nach Sonnenaufgang, in der die Tür geöffnet wird
DAWN_OFFSET = -30 * 60

#: Anzahl Sekunden nach Sonnenuntergang, in der die Tür geschlossen wird.
DUSK_OFFSET = 40 * 60

#: Zeitpunkt des frühesten Öffnens der Tür
EARLIEST_OPEN_TIMES = {
    0: (7, 00), # Montag
    1: (7, 00),
    2: (7, 00),
    3: (7, 00),
    4: (7, 00),
    5: (8, 00), # Samstag
    6: (8, 00), # Sonntag
}

# --------------------------------------------------------------------------------------------------
DOOR_MOVE_UP_TIME = 8.5    #: Maximale Zeit die die Tür zum Öffnen benötigt
DOOR_MOVE_DOWN_TIME = 6.6  #: Maximale Zeit zum Schließen der Tür (Sekunden)
LOWER_REED_OFFSET = 0.6    #: Dauer in Sekunden die die Tür nach Signalisierung
                           #: durch den unteren Magnetschalter weiter läuft,
                           #: damit die Tür vollständig geschlossen ist
UPPER_REED_OFFSET = 0.6    #: Wie :data:`LOWER_REED_OFFSET` für den oberen
                           #: Magnetkontakt

# --------------------------------------------------------------------------------------------------
#: Gibt an, wieviel Sekunden vor den Schließen der Tür die Innen-
#: beleuchtung aktiviert werden soll.
#: 0 = aus
SWITCH_LIGHT_ON_BEFORE_CLOSING = 0

#: Wie SWITCH_LIGHT_ON_BEFORE_CLOSING, allerdings die Ausschaltzeit nach
#: dem Schließen. Ist nur relevant, wenn SWITCH_LIGHT_ON_BEFORE_CLOSING != 0
SWITCH_LIGHT_OFF_AFTER_CLOSING = (1 * 60) if SWITCH_LIGHT_ON_BEFORE_CLOSING else 0
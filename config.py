#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Alle hier verwendeten PINs beziehen sich auf den BOARD-Mode,
also die RPi-Nummerierung am Header.
"""
# ------------------------------------------------------------------------
LOGDIR = 'log'               #: Log-Verzeichnis relativ zu www (root)
RESOURCEDIR = 'resources'    #: Resourcen-Verzeichnis relativ zu www (root)
SCRIPTDIR = 'scripts'        #: Script-Verzeichnis relativ zu www (root)
MAPFILE = -1                 #: Auf -1 setzen wenn Release!
SUNSETFILE = 'sunset.data'   #: Name der Datei mit den Sonnenzeiten relativ zur 'RESOURCEDIR'
# ------------------------------------------------------------------------
#: Template für die Logausgabe (siehe logging - Modul)
LOGFORMAT = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'

#: Template für das Zeitformat der Logausgabe (siehe logging - Modul)
LOGDATEFMT = '%m-%d %H:%M:%S'

#: Logging Level, 10 = logging.DEBUG
LOGLEVEL = 10
# ------------------------------------------------------------------------
# Die folgenden Pins sind OUTPUT-Pins
PIN_RELAIS_1 = 40            #: PIN für Relais 1
PIN_RELAIS_2 = 38            #: PIN für Relais 2
PIN_RELAIS_3 = 36            #: PIN für Relais 3
PIN_RELAIS_4 = 31            #: PIN für Relais 4

# Die nachstehenden Pins sind INPUT-Pins
PIN_REED_1 = 13              #: PIN für den Magnetschalter 1 (Pullup, HIGH = offen / kein Kontakt)
PIN_REED_2 = 11              #: PIN für den Magnetschalter 2 (Pullup, HIGH = offen / kein Kontakt)

PIN_BUTTON_1 = 29            #: PIN für den Button 1 (Pullup, HIGH = offen / nicht gedrückt)
# ------------------------------------------------------------------------
RELAIS_ON = 1                #: Output für Relais geschlossen (grün)
RELAIS_OFF = 0               #: Output für Relais offen (rot)
# ------------------------------------------------------------------------
REED_CLOSED = 0              #: Input für Magnetkontakt geschlossen (Kontakt)
REED_OPENED = 1              #: Input für Magnetkontakt offen (kein Kontakt)
# ------------------------------------------------------------------------
#: PIN für das Aussenlicht-Relais (230V)
LIGHT_OUTDOOR = PIN_RELAIS_3

#: PIN für das Innenlicht-Relais (230V)
LIGHT_INDOOR = PIN_RELAIS_4

#: PIN für das Relais mit der Motor-An/Aus-Schaltung (19V)
MOTOR_ON = PIN_RELAIS_1

#: PIN für das Relais mit der Drehrichtung (siehe MOVE_UP, MOVE_DOWN)
MOVE_DIR = PIN_RELAIS_2

#: Schaltwert für das Relais MOVE_DIR nach Links
MOVE_UP = 0

#: Schaltwert für das Relais MOVE_DIR nach Rechts
MOVE_DOWN = 1

#: Oberer Magnetkontakt
REED_UPPER = PIN_REED_1

#: Unter Magnetkontakt
REED_LOWER = PIN_REED_2

#: Shutdown-Button
SHUTDOWN_BUTTON = PIN_BUTTON_1
# ------------------------------------------------------------------------
#: Menge aller Eingabe-Pins
INPUT_PINS = (PIN_REED_1, PIN_REED_2, PIN_BUTTON_1)
#: Menge aller Relais-Pins.
RELAIS_PINS = (PIN_RELAIS_1, PIN_RELAIS_2, PIN_RELAIS_3, PIN_RELAIS_4)
#: Menge aller Ausgabe-Pins
OUTPUT_PINS = RELAIS_PINS
# ------------------------------------------------------------------------
#: Gibt an, ob zusätzlich zur Fehlerausgabe im Logger eine Exception
#: ausgelöst werden soll.
RAISE_ERRORS = True
# ------------------------------------------------------------------------
#: Längen- und Breitengrad des aktuellen Standort.
LATITUDE = 51.138904 #: Breite
LONGITUDE = 12.094316 #: Länge
# ------------------------------------------------------------------------
CONTROLLER_HOST = 'localhost' #: Host des XMLRPC-Controller-Server
CONTROLLER_PORT = 8010        #: Port des XMLRPC-Controller-Server
#: Adresse des XMLRPC-Server, der die Board-Schnittstelle bereitstellt
CONTROLLER_URI = 'http://%s:%s' % (CONTROLLER_HOST, CONTROLLER_PORT)
# ------------------------------------------------------------------------
MAX_DOOR_MOVE_DURATION = 2 #: Maximale Zeit (in Sekunden) die die Tür für
                           #: eine volle Bewegung benötigt.
# ------------------------------------------------------------------------
#: Anzahl Sekunden nach der der TFT ohne Aktivität (Touch) ausgeschalten
#: wird
TFT_SLEEP_TIMEOUT = 30
# ------------------------------------------------------------------------
#: Intervall, in dem die Sonnenaufgangs / Untergangszeiten berechnet werden
#: (in Sekunden)
SUNRISE_INTERVAL = 4 * 60 * 60

#: Prüfintervall für den Türstatus (Öffnen / Schließen)
DOORCHECK_INTERVAL = 60

#: Anzahl Minuten nach Sonnenaufgang, in der die Tür geöffnet wird
DAWN_OFFSET = 0

#: Anzahl Minuten nach Sonnenuntergang, in der die Tür geschlossen wird.
DUSK_OFFSET = 30 * 60
# ------------------------------------------------------------------------
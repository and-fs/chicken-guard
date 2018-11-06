#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Enthält die in der Steuerung verwendeten Konstanten.

Alle hier verwendeten PINs beziehen sich auf den BOARD-Mode,
also die RPi-Nummerierung am Header.
"""
# ------------------------------------------------------------------------
DEBUG = False
# ------------------------------------------------------------------------
LOGDIR = 'log'               #: Log-Verzeichnis relativ zu root
RESOURCEDIR = 'resources'    #: Resourcen-Verzeichnis relativ zu root
SCRIPTDIR = 'scripts'        #: Script-Verzeichnis relativ zu root
MAPFILE = -1                 #: Auf -1 setzen wenn Release!
BOARDFILE = 'board.json'     #: Name der Datei in der der Boardstatus
                             #: gespeichert wird (relativ zur 'RESOURCEDIR')
SENSORFILE = 'sensor.csv'    #: Sensorwerte, relativ zu RESOURCEDIR
# ------------------------------------------------------------------------
if DEBUG:
    #: Template für die Logausgabe (siehe logging - Modul)
    LOGFORMAT = '%(asctime)s %(name)-20s %(thread)-10d %(levelname)-8s %(message)s'

    #: Template für das Zeitformat der Logausgabe (siehe logging - Modul)
    LOGDATEFMT = ''

    #: Logging Level, 10 = logging.DEBUG
    LOGLEVEL = 10
else:
    LOGFORMAT = '%(asctime)s %(name)-20s %(levelname)-8s %(message)s'
    LOGDATEFMT = '%m-%d %H:%M:%S'
    LOGLEVEL = 20 # logging.INFO
# ------------------------------------------------------------------------
#: Template für die Ausgabe einer Zeile im SENSORFILE.
#: Die Substituierungswerte sind (light, temperature).
SENSOR_LINE_TPL = '%d;%.2f\n'
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
RELAIS_ON = 0                #: Output für Relais geschlossen (grün)
RELAIS_OFF = 1               #: Output für Relais offen (rot)
# ------------------------------------------------------------------------
REED_CLOSED = 0              #: Input für Magnetkontakt geschlossen (Kontakt)
REED_OPENED = 1              #: Input für Magnetkontakt offen (kein Kontakt)
# ------------------------------------------------------------------------
#: PIN für das Aussenlicht-Relais (230V)
LIGHT_OUTDOOR = PIN_RELAIS_4

#: PIN für das Innenlicht-Relais (230V)
LIGHT_INDOOR = PIN_RELAIS_3

#: PIN für das Relais mit der Motor-An/Aus-Schaltung (19V)
MOTOR_ON = PIN_RELAIS_1

#: PIN für das Relais mit der Drehrichtung (siehe MOVE_UP, MOVE_DOWN)
MOVE_DIR = PIN_RELAIS_2

#: Schaltwert für das Relais MOVE_DIR nach oben
MOVE_UP = 1

#: Schaltwert für das Relais MOVE_DIR nach unten
MOVE_DOWN = 0

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
#: Längen- und Breitengrad des aktuellen Standort.
LATITUDE = 51.138904 #: Breite
LONGITUDE = 12.094316 #: Länge
# ------------------------------------------------------------------------
CONTROLLER_HOST = 'localhost' #: Host des XMLRPC-Controller-Server
CONTROLLER_PORT = 8010        #: Port des XMLRPC-Controller-Server
#: Adresse des XMLRPC-Server, der die Board-Schnittstelle bereitstellt
CONTROLLER_URI = 'http://%s:%s' % (CONTROLLER_HOST, CONTROLLER_PORT)
# ------------------------------------------------------------------------
DOOR_AUTO_OFF = 0               #: Türautomatik vorübergehend deaktiviert
DOOR_AUTO_ON = 1                #: Türautomatik aktiv
DOOR_AUTO_DEACTIVATED = -1      #: Türautomatik dauerhaft deaktiviert
# ------------------------------------------------------------------------
#: Tür Stati.
DOOR_NOT_MOVING = 0    #: Initialstatus, eigentlich "unknown"
DOOR_MOVING_UP = 1     #: Bewegung nach oben (Tür öffnet sich)
DOOR_MOVING_DOWN = 2   #: Bewegung nach unten (Tür schließt sich)
DOOR_MOVING = DOOR_MOVING_UP | DOOR_MOVING_DOWN #: Tür in Bewegung
DOOR_OPEN = 4          #: Tür ist offen
DOOR_CLOSED = 8        #: Tür ist geschlossen

# ------------------------------------------------------------------------
CAM_WIDTH = 640    #: Breite des gestreamten Kamerabildes
CAM_HEIGHT = 480   #: Höhe des gestreamten Kamerabildes
CAM_FRAMERATE = 10 #: Bildrate
CAM_PORT = 8000    #: Port des Kameraservers

#: Maximale Zeit, die ein Stream offengehalten wird (in Sekunden)
MAX_STREAM_TIME = 5 * 60

#: Maximale Anzahl paralleler Streams
MAX_STREAM_COUNT = 3
# ------------------------------------------------------------------------
#: Dauer in Sekunden, die der Shutdown-Button gedrückt sein muss,
#: um einen Shutdown auszulösen.
#: Achtung: dieser Wert muss GRÖSSER als BTN_DURATION_REBOOT sein
BTN_DURATION_SHUTDOWN = 6.0

#: Dauer in Sekunden, die der Shutdown-Button gedrückt sein muss,
#: um einen Reboot auszulösen.
#: Achtung: dieser Wert muss KLEINER als BTN_DURATION_SHUTDOWN sein
BTN_DURATION_REBOOT = 2.0
# --------------------------------------------------------------------------------------------------
#: Anzahl Sekunden nach der der TFT ohne Aktivität (Touch) ausgeschalten
#: wird
TFT_SLEEP_TIMEOUT = 30
# --------------------------------------------------------------------------------------------------
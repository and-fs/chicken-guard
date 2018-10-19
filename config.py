#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Alle hier verwendeten PINs beziehen sich auf den BOARD-Mode,
also die RPi-Nummerierung am Header.
"""
# ------------------------------------------------------------------------
DEBUG = True
# ------------------------------------------------------------------------
LOGDIR = 'log'               #: Log-Verzeichnis relativ zu www (root)
RESOURCEDIR = 'resources'    #: Resourcen-Verzeichnis relativ zu www (root)
SCRIPTDIR = 'scripts'        #: Script-Verzeichnis relativ zu www (root)
MAPFILE = -1                 #: Auf -1 setzen wenn Release!
BOARDFILE = 'board.json'     #: Name der Datei in der der Boardstatus
                             #: gespeichert wird (relativ zur 'RESOURCEDIR')
SENSORFILE = 'sensor.csv'    #: Sensorwerte, relativ zu RESOURCEDIR
# ------------------------------------------------------------------------
#: Template für die Logausgabe (siehe logging - Modul)
LOGFORMAT = '%(asctime)s %(name)-20s %(thread)-10d %(levelname)-8s %(message)s'

if DEBUG:
    #: Template für das Zeitformat der Logausgabe (siehe logging - Modul)
    LOGDATEFMT = ''

    #: Logging Level, 10 = logging.DEBUG
    LOGLEVEL = 10
else:
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
#: Gibt an, ob zusätzlich zur Fehlerausgabe im Logger eine Exception
#: ausgelöst werden soll.
RAISE_ERRORS = False
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
MAX_DOOR_MOVE_DURATION = 8.0 #: Maximale Zeit (in Sekunden) die die Tür für
                             #: eine volle Bewegung benötigt.
# ------------------------------------------------------------------------
#: Anzahl Sekunden nach der der TFT ohne Aktivität (Touch) ausgeschalten
#: wird
TFT_SLEEP_TIMEOUT = 30
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

DOOR_AUTO_OFF = 0               #: Türautomatik vorübergehend deaktiviert
DOOR_AUTO_ON = 1                #: Türautomatik aktiv
DOOR_AUTO_DEACTIVATED = -1      #: Türautomatik dauerhaft deaktiviert

#: Anzahl Sekunden nach Sonnenaufgang, in der die Tür geöffnet wird
DAWN_OFFSET = -30 * 60

#: Anzahl Sekunden nach Sonnenuntergang, in der die Tür geschlossen wird.
DUSK_OFFSET = 15 * 60

#: Zeitpunkt des frühesten Öffnens der Tür
EARLIEST_OPEN_TIMES = {
    0: (5, 30), # Montag
    1: (5, 30),
    2: (5, 30),
    3: (5, 30),
    4: (5, 30),
    5: (7, 30), # Samstag
    6: (7, 30), # Sonntag
}
# ------------------------------------------------------------------------
#: Tür Stati.
DOOR_NOT_MOVING = 0    #: Initialstatus, eigentlich "unknown"
DOOR_MOVING_UP = 1     #: Bewegung nach oben (Tür öffnet sich)
DOOR_MOVING_DOWN = 2   #: Bewegung nach unten (Tür schließt sich)
DOOR_MOVING = DOOR_MOVING_UP | DOOR_MOVING_DOWN #: Tür in Bewegung
DOOR_OPEN = 4          #: Tür ist offen
DOOR_CLOSED = 8        #: Tür ist geschlossen
# ------------------------------------------------------------------------
DOOR_MOVE_UP_TIME = 7.3    #: Maximale Zeit die die Tür zum Öffnen benötigt
DOOR_MOVE_DOWN_TIME = 6.0  #: Maximale Zeit zum Schließen der Tür (Sekunden)
# ------------------------------------------------------------------------
#: Gibt an, wieviel Sekunden vor den Schließen der Tür die Innen-
#: beleuchtung aktiviert werden soll.
#: 0 = aus
SWITCH_LIGHT_ON_BEFORE_CLOSING = 0

#: Wie SWITCH_LIGHT_ON_BEFORE_CLOSING, allerdings die Ausschaltzeit nach
#: dem Schließen. Ist nur relevant, wenn SWITCH_LIGHT_ON_BEFORE_CLOSING != 0
SWITCH_LIGHT_OFF_AFTER_CLOSING = (1 * 60) if SWITCH_LIGHT_ON_BEFORE_CLOSING else 0
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
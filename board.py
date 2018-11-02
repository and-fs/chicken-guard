#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Modul enthält die Klassen und Funktionen, die als Abstraktionslayer zur Steuerung
der Schaltung dienen:

 - Tür bewegen
 - Türposition ermitteln
 - Licht schalten
 - Außenhelligkeit und Temperatur ermitteln
 - Reboot- / Shutdownbutton überwachen

Ursprünglich war geplant, die Bewegung der Tür durch Interrupts an den Magnetschaltern
zu steuern. Leider hat mir dort die Interferenz durch den Weidezaun einen Strich durch
die Rechnung gemacht, so dass ich mich auf die Werte der Magnetschalter nicht verlassen konnte.

Aus diesem Grund ist die Methode zum Bewegen der Tür (:meth:`Board.SyncMoveDoor`) nicht mehr
asynchron erstellt, sondern wird vollständig synchron ausgeführt.

Türsteuerung
------------

Das Bewegen der Tür erfolgt über die beiden Relais an den Pins
:data:`MOTOR_ON <config.MOTOR_ON>` (Pin #40) und
:data:`MOTOR_DIR <config.MOTOR_DIR>` (Pin #38).
Die Relais schalten bei :data:`config.RELAIS_ON` durch (HIGH).

Ich verwende hier Relais mit einer Wechselschaltung, auch wenn ich diese nur für die Richtungs-
steuerung benötige. Dahinter liegt eine Platine eines alten RC-Fahrzeugs, über die ich dann
die Leitungen entsprechend durchschalte.

Als erstes wird immer die Richtung über das Relais an
:data:`config.MOTOR_DIR` (PIN #38) geschalten:

  - :data:`config.MOVE_UP` (HIGH) dreht den Motor so, dass die Tür nach oben gezogen wird
  - :data:`config.MOVE_DOWN` (LOW) genau anders herum ;)

Danach erst wird der Motor aktiviert, indem das Relais :data:`config.MOTOR_ON` (Pin #40) auf
:data:`config.RELAIS_ON` (HIGH) geschalten wird.

Jetzt bleibt der Motor solange angeschalten, bis entweder die maximale Zeit der entsprechenden
Bewegungsrichtung erreicht oder der jeweilige Magnetkontakt geschlossen wurde.

Bei kalten Aussentemperaturen führt ein Abschalten nach Zeit zwar leider dazu, dass die Tür
nicht vollständig öffnet und die Hühner sich bücken müssen, aber wichtiger ist, dass die Tür
abends vollständig schließt.

Der als Antrieb verwendete Akkuschrauber hat eine Lastkupplung, so dass ein Überdrehen
bei Erreichen der Endposition ausgeschlossen ist.

Magnetkontakte
--------------

Hier handelt es sich um zwei einfache Magnetkontakte:

  - :data:`config.REED_UPPER` (Pin #13) als oberer Anschlag
  - :data:`config.REED_LOWER` (Pin #11) als unterer Anschlag

Beide liegen als Pullup mit einem 10k - Widerstand an den Pins an, ein Schließen der
Magnetkontakte zieht die Pins also von :data:`config.REED_OPENED` (HIGH) nach
:data:`config.REED_CLOSED` (LOW).

Wie bereits erwähnt, kann es bei aktivem Weidezaung zu Interferenzen kommen, die dazu führen,
dass der Magnetschalter nicht triggert.
Aus diesem Grund musst die ursprüngliche Implementierung (Interrupt an fallender Flanke)
verwerfen und ein Intervall-Polling verwenden (siehe :meth:`Board.IsReedClosed`)
sowie die Dauer der Bewegung prüfen.

Um nach einem Neustart den letzten Zustand auch ohne Magnetkontakte zu erhalten, wird
der jeweils aktuelle Zustand der Tür in einer Datei gespeichert, die bei Neustart
eingelesen und mit den Signalen der Magnetkontakte abgeglichen wird.

Licht
-----

Hier handelt es sich um zwei handelsübliche LED-Lampen, die über die Relais mit
230V versorgt werden:

  - :data:`config.LIGHT_INDOOR` (Pin #36) schaltet die Innenbeleuchtung
  - :data:`config.LIGHT_OUTDOOR` (Pin #31) schaltet die Außenbeleuchtung

Das jeweilige Licht geht an, wenn das entsprechende Relais auf :data:`config.RELAIS_ON`
geschalten wird.

Als zusätzliche Abschalteinrichtung ist nach den Relais nochmals ein Schalter
verbaut, mit dem das jeweilige Liche abgeschalten werden kann (UND-Schaltung
Relais - Schalter 1).
Ein manuelles Einschalten des Lichts wird durch einen weiteren Schalter realisiert,
der eine Leitung parallel zur Relais-Leitung realisiert (ODER-Schaltung Relais - Schalter 2)

Sensoren
--------

Hier ist ein über I2C an Kanal 0x48 angeschlossener PCF8591 verbaut, der zum Ermitteln
der Helligkeit (am Fenster des Hühnerhaus) sowie der Temperatur im Innenraum dient.
Letzterer liefert leider keine korrekten Werte (eventuell sind hier die 3.3V Eingangsspannung
zu niedrig), weshalb aktuell die Temperaturwerte nicht zu gebrauchen sind.

Der Helligkeitssensor (ein Fotowiderstand) gibt hohe Werte zurück, je dunkler die Umgebung ist
(200 = dunkel, < 100 sehr hell).

Reboot-Button
-------------

Als Pullup mit 10K an :data:`config.SHUTDOWN_BUTTON` (Pin #29) verbundener Taster.
Ursprünglich nur als Shutdown-Variante mit Interrupt an steigender Flanke (Loslassen)
verbunden, gab es auch hier ab und an Fehlmeldung (entweder auch durch Interferenzen oder
Fehler in der GPIO-Bibliothek), so dass ich hier :meth:`Board.OnShutdownButtonPressed`
als Interrupt für beide Flanken verwenden und die Zeit dazwischen messe, um einen
Reboot (> :data:`config.BTN_DURATION_REBOOT` Sekunden drücken) oder
Shutdown (> :data:`config.BTN_DURATION_SHUTDOWN` Sekunden drücken) auszulösen.

Klassen und Funktionen
----------------------

"""
# --------------------------------------------------------------------------------------------------
import os
import time
import json
# --------------------------------------------------------------------------------------------------
from shared import LoggableClass, resource_path
from gpio import GPIO, SMBus
from config import * # pylint: disable=W0614
# --------------------------------------------------------------------------------------------------
def AnalogToCelsius(analog_value):
    """
    Rechnet den vom Thermistor des PCF8591 gelieferten Analogwert in Grad Celsius um.
    Achtung: aktuell wird der Eingangswert unverändert (aber als float) zurückgegeben,
    da der Sensor nicht funktioniert.
    """
    return float(analog_value)
    # nominal_temp = 298.15      # Nenntemperatur des Thermistor (Datenblatt, in Kelvin)
    # material_constant = 1100.0 # Materialkonstante des Thermistor aus dem Datenblatt
    # calibration_value = 127.0  # ausgelesener Wert bei Nennemperatur (nominal_temp)
    # temp = 1.0 / (1.0 / nominal_temp + 1.0
    #               / material_constant * math.log(analog_value / calibration_value))
    # return temp - 273.15
# --------------------------------------------------------------------------------------------------
class Sensors(LoggableClass):
    """
    Diese Klasse dient zum Auslesen des Multisensors PCF8591 an I2C #0
    auf PIN #3 (SDA) und PIN #4 (SCL).
    """

    SMBUS_ADDR = 0x48       #: Adresse des I2C-Device
                            #: (PCF8591 an I2C 0, PIN 3 / 5 bei ALT0 = SDA / SCL)
    SMBUS_CH_LIGHT = 0x40   #: Kanal des Fotowiderstand (je kleiner der Wert desto heller)
    SMBUS_CH_AIN  = 0x41    #: AIN
    SMBUS_CH_TEMP = 0x42    #: Temperatur
    SMBUS_CH_POTI = 0x43    #: Potentiometer-Kanal
    SMBUS_CH_AOUT = 0x44    #: AOUT

    def __init__(self):
        LoggableClass.__init__(self, name = "Sensors")
        self._bus = SMBus(1)

    def ReadChannel(self, channel:int, count:int = 10)->int:
        """
        Liest vom Kanal 'channel' Werte in der Anzahl 'count',
        bildet aus diesen den Median und liefert ihn zurück.
        Wenn kein Wert ermittelt werden konnte, wird stattdessen
        None zurückgegeben.
        """
        values = []
        for _ in range(count):
            try:
                # als erstes den Kanal addressieren
                self._bus.write_byte(self.SMBUS_ADDR, channel)
                # dann dessen Wert auslesen
                values.append(self._bus.read_byte(self.SMBUS_ADDR))
            except Exception:
                continue
        if not values:
            self.error("Failed to read from channel %d.", channel)
            return None

        read_values = len(values)
        if read_values < count:
            self.warn(
                "Missed some values at channel %d, expected %d, got only %d.",
                channel, count, read_values)

        # Median bilden:

        values.sort()
        median = values[read_values // 2]
        self.debug(
            "Measured %d values in %d attempts at channel %d, median is %d.",
            read_values, count, channel, median)
        return median

    def ReadTemperature(self)->float:
        """
        Liest den Widerstandswert des Thermistor aus dem entsprechenden Kanal
        und liefert à conto dessen die Temperatur in °C zurück.

        :see:
            :meth:`ReadChannel`
        """
        self.debug("Reading temperature.")
        analog_value = self.ReadChannel(self.SMBUS_CH_TEMP)
        try:
            t = AnalogToCelsius(analog_value)
        except ValueError: # Wert ausserhalb des Bereichs
            t = -100.0
        self.debug("Read a temperatur of %.2f°C.", t)
        return t

    def ReadLight(self)->int:
        """
        Gibt den Wert des Helligkeitssensors zurück.
        Je höher der Wert, desto dunkler.

        :see:
            :meth:`ReadChannel`
        """
        self.debug("Reading light sensor.")
        return self.ReadChannel(self.SMBUS_CH_LIGHT)

    def CleanUp(self):
        """
        Räumt die verwendeten Ressourcen auf.
        """
        self._bus.close()
# --------------------------------------------------------------------------------------------------
class Board(LoggableClass):
    """
    Bildet die wesentliche Steuerung am Board ab.
    """

    def __init__(self):
        LoggableClass.__init__(self, name = "Board")

        #: Aktueller Zustand der Tür.
        #: Kann einen der folgenden Werte annehmen:
        #:
        #:   - :data:`config.DOOR_NOT_MOVING`: Quasi ein unbekannter Zustand, da die
        #:     Tür im Stillstand entweder geschlossen oder offen sein sollte.
        #:   - :data:`config.DOOR_MOVING_UP`: Tür bewegt sich nach oben
        #:   - :data:`config.DOOR_MOVING_DOWN`: Tür bewegt sich nach unten
        #:   - :data:`config.DOOR_OPEN`: Tür ist offen
        #:   - :data:`config.DOOR_CLOSED`: Tür ist geschlossen
        #:
        #: Zur Abfrage, ob sich die Tür bewegt, existiert ausserdem noch die Konstante
        #: :data:`config.DOOR_MOVING`, die als ODER-Ergebnis aus :data:`config.DOOR_MOVING_DOWN`
        #: und :data:`config.DOOR_MOVING_UP` zur Maskierung des Bewegungszustands
        #: verwendet werden kann:
        #:
        #: .. code-block:: python
        #:
        #:   door_is_moving = bool(door_state & DOOR_MOVING)
        self.door_state = DOOR_NOT_MOVING

        #: Zustand der Innenbeleuchtung (``True`` = an)
        #:
        #: .. seealso::
        #:   :meth:`SwitchIndoorLight`
        #:   :attr:`light_state_indoor`
        self.light_state_indoor = False

        #: Zustand der Außenbeleuchtung (``True`` = an)
        #:
        #: .. seealso::
        #:   :meth:`SwitchOutdoorLight`
        #:   :attr:`light_state_indoor`
        self.light_state_outdoor = False

        #: Zeitpunkt, an dem der Shutdown-Button gedrückt wurde.
        #: Wird in :meth:`OnShutdownButtonPressed` benutzt um zu ermitteln, wie lange der Knopf
        #: gedrückt wurde (und Fehlsignalisierung auszuschließen)
        self.shutdown_btn_time = 0

        #: Referenz auf ein Callable, welches bei Änderung des Board-Status
        #: gerufen wird.
        #:
        #: .. seealso::
        #:    :meth:`CallStateChangeHandler`
        #:    :meth:`SetStateChangeHandler`
        self.state_change_handler = None

        #: Pfad der Datei, in der der Status gespeichert wird.
        #:
        #: .. seealso::
        #:   :meth:`Load`
        #:   :meth:`Save`
        self.state_file = resource_path.joinpath(BOARDFILE)

        GPIO.setmode(GPIO.BOARD)

        self.logger.debug("Settings pins %s to OUT.", OUTPUT_PINS)
        GPIO.setup(OUTPUT_PINS, GPIO.OUT, initial = RELAIS_OFF)

        self.logger.debug("Settings pins %s to IN.", INPUT_PINS)
        GPIO.setup(INPUT_PINS, GPIO.IN)

        GPIO.add_event_detect(
            SHUTDOWN_BUTTON, GPIO.BOTH,
            self.OnShutdownButtonPressed, bouncetime = 200)

        #: Instanz von :class:`Sensors` zum Auslesen der Temperatur
        #: und Helligkeitswerte.
        self.sensor = Sensors()

        self.CheckInitialState()
    # -----------------------------------------------------------------------------------
    def __del__(self):
        GPIO.cleanup()
    # -----------------------------------------------------------------------------------
    def CheckInitialState(self):
        """
        Prüft den initialen Zustand nach Konstruktion dieser Instanz.

        Lädt zuerst die Statusdatei (:meth:`Load`) und prüft dann,
        ob der obere Magnetkontakt geschlossen ist (:meth:`IsReedClosed`).

        Falls ja, wird der Türstatus auf offen (:data:`config.DOOR_OPEN`) gesetzt,
        ansonsten auf den Zustand, der zuletzt gespeichert wurde. Falls
        (noch) keine Zustandsdatei existiert, wird die die Tür als
        geschlossen (:data:`config.DOOR_CLOSED`) angenommen.

        .. seealso::
            :meth:`Save`
            :meth:`Load`
            :meth:`IsReedClosed`
            :attr:`door_state`
        """
        # als ersten holen wir uns den gespeicherten Zustand
        loaded = self.Load()
        # dann den oberen Magnetkontakt prüfen
        door_is_open = self.IsReedClosed(REED_UPPER)
        # wenn der letzte Zustand geladen wurde UND der obere Magnetkontakt
        # nicht geschlossen ist, dann nehmen wir den gespeicherten Zustand
        if loaded and (not door_is_open):
            door_is_open = bool(self.door_state & DOOR_OPEN)
        self.door_state = DOOR_OPEN if door_is_open else DOOR_CLOSED

    def Save(self)->bool:
        """
        Speichert den aktuellen Zustand des Boards in der
        Datei :attr:`state_file`.

        Der Zustand besteht aus den Attributen:
            - :attr:`door_state`
            - :attr:`light_state_indoor`
            - :attr:`light_state_outdoor`

        die im JSON-Format gespeichert werden.

        .. seealso::
            :meth:`Load`
            :meth:`CallStateChangeHandler`
        """
        try:
            with self.state_file.open('w') as f:
                json.dump({
                    'door_state': self.door_state,
                    'light_state_indoor': self.light_state_indoor,
                    'light_state_outdoor': self.light_state_outdoor,
                }, f)
        except Exception:
            self.exception("Error while saving state file.")
            return False
        self.debug("Saved state.")
        return True

    def Load(self)->bool:
        """
        Lädt den in der Datei :attr:`state_file` abgelegten Zustand
        des Boards. Obwohl in :meth:`Save` mehr gespeichert wird,
        wird hier nur :attr:`door_state` geladen.

        :returns: Ein Boolean das angibt, ob die Datei geladen wurde.
        """
        if not self.state_file.exists():
            return False

        try:
            with self.state_file.open('r') as f:
                data = json.load(f)
        except Exception:
            self.exception("Error while loading state file.")
            return False

        # wir laden nur den Türstatus, da die Lichtrelais immer aus sind,
        # wenn neu gestartet wurde.
        self.door_state = data.get('door_state', DOOR_NOT_MOVING)

        self.info("Loaded state: %s", data)
        return True
    # -----------------------------------------------------------------------------------
    def OnShutdownButtonPressed(self, *_args):
        """
        Interrupt-Methode für den Taster am Pin :data:`config.SHUTDOWN_BUTTON`.

        Wird mit einer Bouncetime von 200ms an beiden Flanken gerufen, also sowohl
        wenn der Taster gedrückt also auch losgelassen wurde.

        Da der Taster über einen 10K - Pullup den Pin auf LOW zieht, wird
        bei einem LOW Signal davon ausgegangen, dass der Taster gedrückt und
        bei einem HIGH Signal losgelassen wurde.

        Zur Vermeidung der Interpretation von Fehlsignalen, wird auch genau diese
        Reihenfolge (erst drücken, dann loslassen) erwartet und in allen andere
        Fällen keine Verarbeitung durchgeführt.
        Hierzu wird der Zeitpunkt des Drückens in :attr:`shutdown_btn_time`
        verwendet. Bei einem LOW-Signal (gedrückt) muss dieser 0 sein und wird
        dann auf die aktuelle Zeit gesetzt, bei HIGH (losgelassen) darf er
        nicht 0 sein und wird nach Auswertung wieder auf 0 gesetzt.

        Die so ermittelt Zeit führt dann zu jeweiligen Aktion:
         - länger als :data:`config.BTN_DURATION_SHUTDOWN` Sekunden: Shutdown
         - länger als :data:`config.BTN_DURATION_REBOOT` Sekunden: Reboot
         - weniger als :data:`config.BTN_DURATION_REBOOT` Sekunden: keine Aktion

        Die Aktionen werden über ``os.system`` ausgeführt, der Prozess muss also
        entsprechende Rechte verfügen.
        """
        # der Button zieht das permanente HIGH-Signal auf LOW, wenn
        # er gedrückt wird (PULL_UP)
        if GPIO.input(SHUTDOWN_BUTTON) == GPIO.LOW:
            # der Knopf ist gedrückt.
            if self.shutdown_btn_time != 0:
                # da stimmt was nicht, wir ignorieren lieber alles,
                # setzen den Wert aber zurück
                self.shutdown_btn_time = 0
                return
            self.shutdown_btn_time = time.time()
        else:
            # der Knopf wurde losgelassen
            if self.shutdown_btn_time == 0:
                # auch hier wäre jetzt was verkehrt, also
                # ignorieren
                return
            # jetzt prüfen, wie lange er gedrückt war.
            pressed_duration = time.time() - self.shutdown_btn_time
            # und setzen den Wert wieder zurück
            self.shutdown_btn_time = 0
            self.info("Shutdown button has been pressed for %.2f seconds.", pressed_duration)
            if pressed_duration > BTN_DURATION_SHUTDOWN:
                # shutdown
                self.info("Shutting system down.")
                os.system("sudo shutdown -h now")
            elif pressed_duration > BTN_DURATION_REBOOT:
                # reboot
                self.info("Rebooting system.")
                os.system("sudo reboot -h now")
    # -----------------------------------------------------------------------------------
    # --- LICHT -------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------
    def SwitchOutdoorLight(self, swon:bool):
        """
        Schaltet das Aussenlicht ein, wenn ``swon`` True ist. (sonst aus)

        .. seealso::
            :meth:`SwitchIndoorLight`
            :meth:`IsOutdoorLightOn`
        """
        self.light_state_outdoor = swon
        GPIO.output(LIGHT_OUTDOOR, RELAIS_ON if swon else RELAIS_OFF)
        self.info("Switched outdoor light %s", "on" if swon else "off")
        self._CallStateChangeHandler()

    def SwitchIndoorLight(self, swon:bool):
        """
        Schaltet die Innenbeleuchtung ein, wenn ``swon`` True ist. (sonst aus).

        .. seealso::
            :meth:`SwitchOutdoorLight`
            :meth:`IsIndoorLightOn`
        """
        self.light_state_indoor = swon
        GPIO.output(LIGHT_INDOOR, RELAIS_ON if swon else RELAIS_OFF)
        self.info("Switched indoor light %s", "on" if swon else "off")
        self._CallStateChangeHandler()

    def IsIndoorLightOn(self)->bool:
        """
        Gibt zurück, ob die Innenbeleuchtung angeschalten ist.

        .. seealso::
            :meth:`SwitchIndoorLight`
            :meth:`IsOutdoorLightOn`
        """
        return self.light_state_indoor

    def IsOutdoorLightOn(self)->bool:
        """
        Gibt zurück, ob die Außenbeleuchtung angeschalten ist.

        .. seealso::
            :meth:`SwitchOutdoorLight`
            :meth:`IsIndoorLightOn`
        """
        return self.light_state_outdoor
    # -----------------------------------------------------------------------------------
    # ---- TÜR --------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------
    def _SetDoorState(self, new_state: int):
        """
        Setzt den Zustand der Tür auf ``new_state``.
        Ruft nach dem Setzen :meth:`_CallStateChangeHandler` zur Propagierung der
        Änderung. Sollten neuer und alter Wert identisch sein, erfolgt
        keine Aktion.
        """
        if self.door_state != new_state:
            self.door_state = new_state
            self._CallStateChangeHandler()

    def StartMotor(self, direction:int):
        """
        Schaltet die Motorsteuerungsrelais so, dass sich der Motor in die
        entsprechende Richtung dreht.

        :param direction: Drehrichung. Der Einfachheit halber wird hier :data:`config.MOVE_UP`
            bzw. :data:`config.MOVE_DOWN` für die Richtung erwartet und entspricht damit
            der Bewegungsrichtung der Tür.

        .. seealso::
            :meth:`SyncMoveDoor`
            :meth:`StopMotor`
            :meth:`_SetDoorState`
        """
        self.info("Starting motor (%s).", "up" if direction == MOVE_UP else "down")
        GPIO.output(MOVE_DIR, direction)
        GPIO.output(MOTOR_ON, RELAIS_ON)
        self._SetDoorState(DOOR_MOVING_UP if direction == MOVE_UP else DOOR_MOVING_DOWN)

    def StopMotor(self, end_state:int = DOOR_NOT_MOVING):
        """
        Schaltet die Releais zur Motorsteuerung so, dass der Motor ausgeht und die
        Drehrichtung zurückgesetzt wird.

        :param int end_state: der damit erreichte Status der Tür, in der Regel also
            :data:`config.DOOR_OPEN` oder :data:`config.DOOR_CLOSED`.
        """
        self.info("Stopping motor.")
        GPIO.output(MOTOR_ON, RELAIS_OFF)
        GPIO.output(MOVE_DIR, MOVE_UP)
        self._SetDoorState(end_state)

    def SyncMoveDoor(self, direction:int)->bool:
        """
        Bewegt die Tür in die angegebene Richtung und kehrt erst nach Erreichen des damit
        verbundenen Endzustands zurück.

        Sollte die Endposition der vorgegebenen Bewegungsrichtung bereits erreicht sein
        (z.Bsp. :data:`config.DOOR_CLOSED` bei :data:`config.MOVE_DOWN`) oder die Tür
        bereits in Bewegung, wird eine Fehlermeldung ins Log geschrieben und keine Aktion
        ausgeführt.

        Der erwartete Endzustand wird sowohl anhand der maximalen Bewegungszeit der
        entsprechenden Richtung (:data:`config.DOOR_MOVE_DOWN_TIME` oder
        :data:`config.DOOR_MOVE_UP_TIME`) als auch den Signalen der Magnetkontakte geprüft.

        Wenn die Signalisierung über die Magnetkontakte stattgefunden hat, wird die Bewegung
        entsprechend der konfigurierten Zeiten noch etwas weiter ausgeführt (siehe
        :data:`config.LOWER_REED_OFFSET` bzw. :data:`config.UPPER_REED_OFFSET`). Der Grund
        dafür ist, dass die Magnetkontakte sehr zeitig auslösen und die jeweilige Endposition
        der Tür noch nicht erreicht wurde.

        Sollte der jeweilige Magnetkontakt nicht auslösen, wird die oben genannte Bewegungszeit
        als Maximum verwendet und bei Erreichen der Motor angehalten.

        In beiden Fällen wird dann der Zustand der Tür entsprechend der Bewegungsrichtung
        gesetzt.

        :param int direction: Bewegungsrichtung der Tür.
            Kann entweder :data:`config.MOVE_UP` oder :data:`config.MOVE_DOWN` sein.

        :returns: Ob die Tür bewegt wurde.

        .. seealso::
            :meth:`StartMotor`
            :meth:`StopMotor`
            :meth:`IsReedClosed`
            :meth:`IsDoorMoving`
        """
        if direction == MOVE_UP:
            str_dir = "up"
            reed_pin = REED_UPPER
            end_state = DOOR_OPEN
            max_duration = DOOR_MOVE_UP_TIME
            reed_offset = UPPER_REED_OFFSET
        else:
            str_dir = "down"
            reed_pin = REED_LOWER
            end_state = DOOR_CLOSED
            max_duration = DOOR_MOVE_DOWN_TIME
            reed_offset = LOWER_REED_OFFSET

        can_move = not self.IsReedClosed(reed_pin)
        if can_move:
            # wenn der Magnetkontakt HIGH liefert, kann es sich um
            # eine Störung halten, deshalb prüfen wir
            # hier sicherheitshalber den gespeicherten Status
            can_move = (self.door_state & end_state) == 0
        if not can_move:
            self.error("Cannot move %s, door is already there!", str_dir)
            return False

        if self.IsDoorMoving():
            self.error("Cannot move door, already moving!")
            return False

        self.debug("Moving door %s synchronized (max. %.2f seconds).", str_dir, max_duration)

        self.StartMotor(direction)

        # maximale Dauer der Anschaltzeit des Motor
        move_end_time = time.time() + max_duration

        reed_signaled = False
        while not reed_signaled and (move_end_time > time.time()):
            reed_signaled = self.IsReedClosed(reed_pin)

        if reed_signaled:
            self.info("Reed %s has been closed.", str_dir)
            time.sleep(reed_offset)
        else:
            self.warning("Reed %s not closed, reached timeout.", str_dir)

        self.StopMotor(end_state)
        return True

    def IsReedClosed(self, reed_pin:int)->bool:
        """
        Gibt an, ob der Magnetkontakt am entsprechenden Pin geschlossen ist.
        Da es immer wieder Probleme durch Interferenzen mit dem Weidezaun gab, werden
        hier 15 Messungen in 0,7 Sekunden durchgeführt.
        Wenn mindestens 5x der Kontakt als geschlossen ermittelt wurde, wird der
        gehen wir hier von einem echten Schließen aus.

        :param int reed_pin: Pin des Magnetkontakts, also entweder :data:`config.REED_UPPER`
            oder :data:`config.REED_LOWER`

        :returns: Ob der angegebene Magentkontakt geschlossen ist.

        .. seealso::
            :meth:`IsDoorOpen`
            :meth:`IsDoorClosed`
            :meth:`SyncMoveDoor`
        """
        triggered = i = 0
        for i in range(15):
            if GPIO.input(reed_pin) == REED_CLOSED:
                if triggered > 4:
                    # der Magnetkontakt war jetzt 4x
                    # geschlossen, damit ist die Bedingung erfüllt
                    self.info("Reed trigger: %d of %d", triggered, i)
                    return True
                triggered += 1
            if i < 14: # nach dem letzten Messen warten wir nicht
                time.sleep(0.05)
        self.info("Reed trigger: %d of %d", triggered, i)
        return False

    def IsDoorOpen(self)->bool:
        """
        Gibt zurück, ob die Tür geöffnet ist.
        Primär wird dazu :meth:`IsReedClosed` für den Kontakt :data:`config.REED_UPPER`
        verwendet.
        Da es trotz der Messreihe aus :meth:`IsReedClosed` immer noch manchmal
        zu Messfehlern am Magnetkontakt kommt, wird - falls :meth:`IsReedClosed` ``False``
        liefert - der gespeicherte Zustand der Tür aus :attr:`door_state` geprüft.

        :returns: Ob die Tür offen ist.

        .. seealso::
            :meth:`IsDoorClosed`
            :meth:`IsReedClosed`
            :meth:`SyncMoveDoor`
        """
        if not self.IsReedClosed(REED_UPPER):
            # wenn der Magnetschalter behauptet, dass er
            # nicht geschlossen ist, nehmen wir sicher-
            # heitshalber den gespeicherten Zustand
            return bool(self.door_state & DOOR_OPEN)
        return True

    def IsDoorClosed(self)->bool:
        """
        Gibt zurück, ob die Tür geschlossen ist.
        Siehe :meth:`IsDoorOpen` für weitere Details.
        """
        if not self.IsReedClosed(REED_LOWER):
            return bool(self.door_state & DOOR_CLOSED)
        return True

    def IsDoorMoving(self)->bool:
        """
        Liefert zurück, ob die Tür sich gerade in Bewegung befindet.
        Die Richtung ist dabei nicht von Belang.

        .. seealso::
            :meth:`IsDoorOpen`
            :meth:`SyncMoveDoor`
        """
        return bool(self.door_state & DOOR_MOVING)

    def OpenDoor(self)->bool:
        """
        Entspricht :meth:`SyncMoveDoor` ( :data:`config.MOVE_UP` ).
        """
        self.debug("Executing OpenDoor command.")
        return self.SyncMoveDoor(MOVE_UP)

    def CloseDoor(self):
        """
        Entspricht :meth:`SyncMoveDoor` ( :data:`config.MOVE_DOWN` ).
        """
        self.debug("Executing CloseDoor command.")
        return self.SyncMoveDoor(MOVE_DOWN)

    def StopDoor(self):
        """
        Hält die Tür an (insofern sie sich gerade bewegt).
        Ruft lediglich :meth:`StopMotor`.

        .. seealso::
            :meth:`OpenDoor`
            :meth:`CloseDoor`
        """
        self.info("Executing StopDoor command.")
        self.StopMotor()
    # -----------------------------------------------------------------------------------
    # --- Sensoren ----------------------------------------------------------------------
    # -----------------------------------------------------------------------------------
    def GetTemperature(self)->float:
        """
        Liefert die aktuelle Temperatur am angeschlossenen Sensor.
        Siehe dazu :meth:`Sensors.ReadTemperature`.
        """
        return self.sensor.ReadTemperature()

    def GetLight(self)->int:
        """
        Liefert den Wert des Helligkeitssensors.
        Siehe dazu :meth:`Sensors.ReadLight`.
        """
        return self.sensor.ReadLight()

    def GetState(self):
        """
        Gibt den aktuellen Status des Board als Dictionary zurück.
        Dieser hat folgende Werte:

          - ``indoor_light``: bool = Zustand der Innenbeleuchtung (siehe
            :meth:`IsIndoorLightOn`)
          - ``outdoor_light``: bool = Zustand der Außenbeleuchtung (siehe
            :meth:`IsOutdoorLightOn`)
          - ``door``: int = aktueller Türzustand. Kann folgende Werte haben:
            - :data:`config.DOOR_MOVING`: Tür bewegt sich gerade
            - :data:`config.DOOR_CLOSED`: Tür ist geschlossen
            - :data:`config.DOOR_OPEN`: Tür ist offen
            - :data:`config.DOOR_NOT_MOVING`: Fehler
        """
        result = {
            "indoor_light": self.light_state_indoor,
            "outdoor_light": self.light_state_outdoor,
        }

        if self.IsDoorMoving():
            result["door"] = DOOR_MOVING
        elif self.IsDoorClosed():
            result["door"] = DOOR_CLOSED
        elif self.IsDoorOpen():
            result["door"] = DOOR_OPEN
        else:
            result["door"] = DOOR_NOT_MOVING

        return result

    def SetStateChangeHandler(self, handler:callable):
        """
        Setzt einen Handler der bei jeder Statusänderung des Boards gerufen wird.

        :param callable handler: Ein Callable das ein Dictionary wie in :meth:`GetState`
            als einzigen Parameter entgegennimmt.
            Kann auch ``None`` sein, das entspricht einem Entfernen des Handlers.

        .. seealso::
            :meth:`tools.InstallStateChangeHandler`
            :meth:`GetState`
            :meth:`_SetDoorState`
            :meth:`_CallStateChangeHandler`
        """
        self.state_change_handler = handler

    def _CallStateChangeHandler(self):
        """
        Wird intern bei jeder Änderung des aktuellen Status gerufen.
        Speichert den Status mittels :meth:`Save` und ruft dann den
        Change-Handler, insofern gesetzt.

        .. seealso::
            :meth:`SetStateChangeHandler`
            :meth:`GetState`
        """
        self.Save()
        if self.state_change_handler:
            self.debug("Calling state change handler")
            try:
                self.state_change_handler(self.GetState())
            except Exception:
                self.exception("Error while calling state change handler.")
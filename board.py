#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
import threading
import os
import math
import time
import json
from shared import LoggableClass, resource_path
from gpio import GPIO, SMBus
from config import * # pylint: disable=W0614
# ---------------------------------------------------------------------------------------
def analogToCelsius(analog_value):
    """
    Rechnet den vom Thermistor des PCF8591 gelieferten Analogwert in Grad Celsius um.
    Achtung: aktuell wird der Eingangswert unverändert (aber als float) zurückgegeben.
    """
    return float(analog_value)
    # nominal_temp = 298.15      # Nenntemperatur des Thermistor (Datenblatt, in Kelvin)
    # material_constant = 1100.0 # Materialkonstante des Thermistor aus dem Datenblatt
    # calibration_value = 127.0  # ausgelesener Wert bei Nennemperatur (nominal_temp)
    # temp = 1.0 / (1.0 / nominal_temp + 1.0 / material_constant * math.log(analog_value / calibration_value))
    # return temp - 273.15
# ---------------------------------------------------------------------------------------
class Sensors(LoggableClass):
    """
    Diese Klasse dient zum Auslesen des Multisensors PCF8591 an I2C #0
    auf PIN #3 (SDA) und PIN #4 (SCL).
    """

    SMBUS_ADDR = 0x48       # Adresse des I2C-Device (PCF8591 an I2C 0, PIN 3 / 5 bei ALT0 = SDA / SCL)
    SMBUS_CH_LIGHT = 0x40   # Kanal des Fotowiderstand (je kleiner der Wert desto heller)
    SMBUS_CH_AIN  = 0x41    # AIN
    SMBUS_CH_TEMP = 0x42    # Temperatur
    SMBUS_CH_POTI = 0x43    # Potentiometer-Kanal
    SMBUS_CH_AOUT = 0x44    # AOUT

    def __init__(self):
        LoggableClass.__init__(self, name = "Sensors")
        self._bus = SMBus(1)

    def ReadChannel(self, channel: int, count: int = 10):
        """
        Liest vom Kanal 'channel' Werte in der Anzahl 'count',
        bildet aus diesen den Median und liefert ihn zurück.
        Wenn kein Wert ermittelt werden konnte, wird stattdessen
        None zurückgegeben.
        """
        if not channel in (self.SMBUS_CH_LIGHT, self.SMBUS_CH_POTI, self.SMBUS_CH_AIN, self.SMBUS_CH_TEMP):
            self.error("Cannot read from channel %d!", channel)

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
            self.warn("Missed some values at channel %d, expected %d, got only %d.", channel, count, read_values)

        # Median bilden:

        values.sort()
        median = values[read_values // 2]
        self.debug("Measured %d values in %d attempts at channel %d, median is %d.", read_values, count, channel, median)
        return median

    def ReadTemperature(self):
        """
        Liest den Widerstandswert des Thermistor aus dem entsprechenden Kanal
        und liefert à conto dessen die Temperatur in °C zurück.
        """
        self.debug("Reading temperature.")
        analog_value = self.ReadChannel(self.SMBUS_CH_TEMP)
        try:
            t = analogToCelsius(analog_value)
        except ValueError: # Wert ausserhalb des Bereichs
            t = -100.0
        self.debug("Read a temperatur of %.2f°C.", t)
        return t

    def ReadLight(self):
        self.debug("Reading light sensor.")
        return self.ReadChannel(self.SMBUS_CH_LIGHT)

    def CleanUp(self):
        self._bus.close()
# ---------------------------------------------------------------------------------------
class Board(LoggableClass):
    """
    Bildet die wesentliche Steuerung am Board ab.
    """

    def __init__(self):
        LoggableClass.__init__(self, name = "Board")

        self.door_state = DOOR_NOT_MOVING
        self.light_state_indoor = False
        self.light_state_outdoor = False

        #: Zeitpunkt, an dem der Shutdown-Button gedrückt wurde.
        #: Wird benutzt um zu ermitteln, wie lange der Knopf
        #: gedrückt wurde (und Fehlsignalisierung auszuschließen)
        self.shutdown_btn_time = 0

        self._wait_condition = threading.Condition()

        self.state_change_handler = None

        self.state_file = resource_path.joinpath(BOARDFILE)

        GPIO.setmode(GPIO.BOARD)

        self.logger.debug("Settings pins %s to OUT.", OUTPUT_PINS)
        GPIO.setup(OUTPUT_PINS, GPIO.OUT, initial = RELAIS_OFF)

        self.logger.debug("Settings pins %s to IN.", INPUT_PINS)
        GPIO.setup(INPUT_PINS, GPIO.IN)

        GPIO.add_event_detect(SHUTDOWN_BUTTON, GPIO.BOTH, self.OnShutdownButtonPressed, bouncetime = 200)

        self.sensor = Sensors()

        self.CheckInitialState()
    # -----------------------------------------------------------------------------------
    def __del__(self):
        GPIO.cleanup()
    # -----------------------------------------------------------------------------------
    def CheckInitialState(self):
        # als ersten holen wir uns den gespeicherten Zustand
        loaded = self.Load()
        # dann den oberen Magnetkontakt prüfen
        door_is_open = self.IsReedClosed(REED_UPPER)
        # wenn der letzte Zustand geladen wurde UND der obere Magnetkontakt
        # nicht geschlossen ist, dann nehmen wir den gespeicherten Zustand
        if loaded and (not door_is_open):
            door_is_open = 0 != (self.door_state & DOOR_OPEN)
        self.door_state = DOOR_OPEN if door_is_open else DOOR_CLOSED

    def Save(self):
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

    def Load(self):
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
    def OnShutdownButtonPressed(self, *args):
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
        Schaltet das Aussenlicht ein, wenn 'swon' True ist. (sonst aus)
        """
        self.light_state_outdoor = swon
        GPIO.output(LIGHT_OUTDOOR, RELAIS_ON if swon else RELAIS_OFF)
        self.info("Switched outdoor light %s", "on" if swon else "off")
        self.CallStateChangeHandler()

    def SwitchIndoorLight(self, swon:bool):
        """
        Schaltet die Innenbeleuchtung ein, wenn 'swon' True ist. (sonst aus)
        """
        self.light_state_indoor = swon
        GPIO.output(LIGHT_INDOOR, RELAIS_ON if swon else RELAIS_OFF)
        self.info("Switched indoor light %s", "on" if swon else "off")
        self.CallStateChangeHandler()

    def IsIndoorLightOn(self):
        return self.light_state_indoor

    def IsOutdoorLightOn(self):
        return self.light_state_outdoor
    # -----------------------------------------------------------------------------------
    # ---- TÜR --------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------
    def SetDoorState(self, new_state):
        if self.door_state == new_state:
            return
        self.door_state = new_state
        self.CallStateChangeHandler()
    # -----------------------------------------------------------------------------------
    def StartMotor(self, direction):
        self.info("Starting motor (%s).", "up" if direction == MOVE_UP else "down")
        GPIO.output(MOVE_DIR, direction)
        GPIO.output(MOTOR_ON, RELAIS_ON)
        self.SetDoorState(DOOR_MOVING_UP if direction == MOVE_UP else DOOR_MOVING_DOWN)

    def StopMotor(self, end_state = DOOR_NOT_MOVING):
        self.info("Stopping motor.")
        GPIO.output(MOTOR_ON, RELAIS_OFF)
        GPIO.output(MOVE_DIR, MOVE_UP)
        self.SetDoorState(end_state)

    def SyncMoveDoor(self, direction, max_duration:float = MAX_DOOR_MOVE_DURATION):
        if direction == MOVE_UP:
            str_dir = "up"
            reed_pin = REED_UPPER
            end_state = DOOR_OPEN
        else:
            str_dir = "down"
            reed_pin = REED_LOWER
            end_state = DOOR_CLOSED

        can_move = not self.IsReedClosed(reed_pin)
        if can_move:
            # wenn der Magnetkontakt HIGH liefert, kann es sich um
            # eine Störung halten, deshalb prüfen wir
            # hier sicherheitshalber den gespeicherten Status
            can_move = 0 == (self.door_state & end_state)
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
            if direction == MOVE_DOWN:
                time.sleep(0.3) # die Tür schließt sonst nicht richtig
        else:
            self.warning("Reed %s not closed, reached timeout.", str_dir)

        self.StopMotor(end_state)
        return True

    def IsReedClosed(self, reed_pin: int):
        triggered = 0
        for i in range(15):
            if GPIO.input(reed_pin) == REED_CLOSED:
                if triggered > 4:
                    # der Magnetkontakt war jetzt 4x
                    # geschlossen, damit ist die Bedingung erfüllt
                    self.debug("Reed trigger: %d of %d", triggered, i)
                    return True
                triggered += 1
            if i < 14: # nach dem letzten Messen warten wir nicht
                time.sleep(0.05)
        self.debug("Reed trigger: %d of %d", triggered, i)
        return False

    def IsDoorOpen(self):
        if not self.IsReedClosed(REED_UPPER):
            # wenn der Magnetschalter behauptet, dass er
            # nicht geschlossen ist, nehmen wir sicher-
            # heitshalber den gespeicherten Zustand
            return 0 != (self.door_state & DOOR_OPEN)
        return True

    def IsDoorClosed(self):
        if not self.IsReedClosed(REED_LOWER):
            return 0 != (self.door_state & DOOR_CLOSED)
        return True

    def IsDoorMoving(self):
        return 0 != (self.door_state & DOOR_MOVING)

    def OpenDoor(self):
        self.debug("Executing OpenDoor command.")
        return self.SyncMoveDoor(MOVE_UP)

    def CloseDoor(self):
        """
        Wie 'OpenDoor', allerdings in die andere Richtung.
        """
        self.debug("Executing CloseDoor command.")
        return self.SyncMoveDoor(MOVE_DOWN, DOOR_MOVE_DOWN_TIME)

    def StopDoor(self):
        """
        Hält die Tür an (insofern sie sich gerade bewegt).
        """
        self.info("Executing StopDoor command.")
        self.StopMotor()
    # -----------------------------------------------------------------------------------
    # --- Sensoren ----------------------------------------------------------------------
    # -----------------------------------------------------------------------------------
    def GetTemperature(self):
        return self.sensor.ReadTemperature()

    def GetLight(self):
        return self.sensor.ReadLight()

    def GetState(self):
        """
        Liefert den aktuellen Status des Board zurück.
        Dieser wird als Dictionary geliefert.
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

    def SetStateChangeHandler(self, callable):
        self.state_change_handler = callable

    def CallStateChangeHandler(self):
        self.Save()
        if self.state_change_handler:
            self.debug("Calling state change handler")
            try:
                self.state_change_handler(self.GetState())
            except Exception:
                self.exception("Error while calling state change handler.")
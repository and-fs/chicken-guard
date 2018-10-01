#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
import threading
import os
import math
import time
from shared import LoggableClass
from gpio import GPIO, SMBus
from config import * # pylint: disable=W0614
# ---------------------------------------------------------------------------------------
def analogToCelsius(analog_value):
    """
    Rechnet den vom Thermistor des PCF8591 gelieferten Analogwert in Grad Celsius um.
    """
    nominal_temp = 298.15      # Nenntemperatur des Thermistor (Datenblatt, in Kelvin)
    material_constant = 1100.0 # Materialkonstante des Thermistor aus dem Datenblatt
    calibration_value = 127.0  # ausgelesener Wert bei Nennemperatur (nominal_temp)
    temp = 1.0 / (1.0 / nominal_temp + 1.0 / material_constant * math.log(analog_value / calibration_value))
    return temp - 273.15
# ---------------------------------------------------------------------------------------
class Sensors(LoggableClass):
    """
    Diese Klasse dient zum Auslesen des Multisensors PCF8591 an I2C #0
    auf PIN #3 (SDA) und PIN #4 (SCL).
    """
    
    SMBUS_ADDR = 0x48       # Adresse des I2C-Device (PCF8591 an I2C 0, PIN 3 / 5 bei ALT0 = SDA / SCL)
    SMBUS_CH_LIGHT = 0x40   # Kanal des Fotowiderstand (je kleiner der Wert desto heller)
    SMBUS_CH_AIN  = 0x41    # AIN
    SMBUS_CH_TEMP = 0x44    # Temperatur
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

    DOOR_NOT_MOVING = 0
    DOOR_MOVING_UP = 1
    DOOR_MOVING_DOWN = 2
    DOOR_MOVING = DOOR_MOVING_UP | DOOR_MOVING_DOWN
    DOOR_OPEN = 4
    DOOR_CLOSED = 8

    def __init__(self):
        LoggableClass.__init__(self, name = "Board")
        
        self.door_state = Board.DOOR_NOT_MOVING
        self.light_state_indoor = False
        self.light_state_outdoor = False

        self._wait_condition = threading.Condition()

        self.state_change_handler = None

        GPIO.setmode(GPIO.BOARD)
        
        self.logger.debug("Settings pins %s to OUT.", OUTPUT_PINS)
        GPIO.setup(OUTPUT_PINS, GPIO.OUT, initial = RELAIS_OFF)

        self.logger.debug("Settings pins %s to IN.", INPUT_PINS)
        GPIO.setup(INPUT_PINS, GPIO.IN)

        GPIO.add_event_detect(SHUTDOWN_BUTTON, GPIO.RISING, self.OnShutdownButtonPressed, bouncetime = 200)

        self.CheckForError(
            not (self.IsDoorOpen() and self.IsDoorClosed()),
            "Inconsistent door contact state, door is signaled both to be open and closed, check configuration!"
        )

        self.sensor = Sensors()
    # -----------------------------------------------------------------------------------
    def __del__(self):
        GPIO.cleanup()
    # -----------------------------------------------------------------------------------
    def CheckForError(self, condition, message, *args, errorclass = RuntimeError):
        """
        Wenn 'condition' nicht mit 'True' evaluiert, wird über den Logger
        ein Fehler mit dem Inhalt von 'message' substituiert durch 'args' ausgegeben.
        Wenn RAISE_ERRORS mit 'True' konfiguriert wurde (siehe config.py),
        wird zusätzlich eine Exception mit dem Typ 'errorclass' geworfen.
        Gibt zurück, ob die 'condition' erfüllt ist.
        """
        if condition:
            return True
        self.error(message, *args)
        if RAISE_ERRORS:
            raise errorclass(message % args)
        return False
    # -----------------------------------------------------------------------------------
    def OnShutdownButtonPressed(self, *args):
        #: TODO: es kann sein, dass das nicht funktioniert, weil der Controller nicht
        #: als root - Nutzer ausgeführt wird.
        #: In diesem Fall muss ein eigenes Script her, welches beim Startup
        #: als root ausgeführt wird und den Button überwacht
        self.info("Shutdown button has been released, shutting system down.")
        os.system("sudo shutdown -h now")
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
        #self.CallStateChangeHandler()
    # -----------------------------------------------------------------------------------
    def StartMotor(self, direction):
        self.info("Starting motor (%s).", "up" if direction == MOVE_UP else "down")
        GPIO.output(MOVE_DIR, direction)
        GPIO.output(MOTOR_ON, RELAIS_ON)
        self.SetDoorState(Board.DOOR_MOVING_UP if direction == MOVE_UP else Board.DOOR_MOVING_DOWN)

    def StopMotor(self, end_state = DOOR_NOT_MOVING):
        self.info("Stopping motor.")
        GPIO.output(MOTOR_ON, RELAIS_OFF)
        GPIO.output(MOVE_DIR, MOVE_UP)
        self.SetDoorState(end_state)

    def SyncMoveDoor(self, direction):
        if direction == MOVE_UP:
            str_dir = "up"
            reed_pin = REED_UPPER
            end_state = Board.DOOR_OPEN
        else:
            str_dir = "down"
            reed_pin = REED_LOWER
            end_state = Board.DOOR_CLOSED

        self.debug("Moving door %s synchronized.", str_dir)

        if self.door_state & Board.DOOR_MOVING:
            self.error("Cannot move door, already moving!")
            return False

        self.StartMotor(direction)

        # maximale Dauer der Anschaltzeit des Motor
        move_end_time = time.time() + MAX_DOOR_MOVE_DURATION

        reed_signaled = False
        while not reed_signaled and (move_end_time > time.time()):
            reed_signaled = self.IsReedClosed(reed_pin)

        if reed_signaled:
            self.info("Reed %s has been closed.", str_dir)
        else:
            self.warn("Reed %s not closed, reached timeout.", str_dir)

        self.StopMotor(end_state)

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
        return self.IsReedClosed(REED_UPPER)

    def IsDoorClosed(self):
        return self.IsReedClosed(REED_LOWER)

    def IsDoorMoving(self):
        return 0 != (self.door_state & Board.DOOR_MOVING)

    def OpenDoor(self):
        self.debug("Executing OpenDoor command.")
        return self.SyncMoveDoor(MOVE_UP)

    def CloseDoor(self):
        """
        Wie 'OpenDoor', allerdings in die andere Richtung.
        """
        self.debug("Executing CloseDoor command.")
        return self.SyncMoveDoor(MOVE_DOWN)

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
            "temperature": self.GetTemperature(),
            "indoor_light": self.IsIndoorLightOn(),
            "outdoor_light": self.IsOutdoorLightOn(),
            "light_sensor": self.GetLight(),
        }

        if self.IsDoorMoving():
            result["door"] = DOOR_MOVING
        elif self.IsDoorClosed():
            result["door"] = DOOR_CLOSED
        elif self.IsDoorOpen():
            result["door"] = DOOR_OPEN
        else:
            result["door"] = DOOR_UNKNOWN

        return result

    def SetStateChangeHandler(self, callable):
        self.state_change_handler = callable

    def CallStateChangeHandler(self):
        if self.state_change_handler:
            self.debug("Calling state change handler")
            try:
                self.state_change_handler(self.GetState())
            except Exception:
                self.exception("Error while calling state change handler.")
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
    SMBUS_CH_TEMP = 0x43    # Temperatur
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

    def __init__(self):
        LoggableClass.__init__(self, name = "Board")
        
        self.door_state = Board.DOOR_NOT_MOVING
        self.light_state_indoor = False
        self.light_state_outdoor = False

        self._wait_condition = threading.Condition()
        self._waiter = None

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

        # damit wir die Bewegung sofort anhalten, wenn der jeweilige
        # Magnetkontakt geschlossen wird, setzen wir einen Interrupt.
        # Da der Magnetkontakt mit LOW geschlossen wird, soll das Event auf
        # die fallende Flanke (Wechsel von HIGH nach LOW) reagieren
        GPIO.add_event_detect(REED_UPPER, GPIO.RISING, self.OnUpperReedClosed, bouncetime = 250)
        GPIO.add_event_detect(REED_LOWER, GPIO.RISING, self.OnLowerReedClosed, bouncetime = 250)

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
    def SwitchRelais(self, channel: int, state: int):
        """
        Schaltet das Relais am Pin 'channel' in den Status 'state'.
        """
        if self.CheckForError(
            channel in RELAIS_PINS,
            "Channel %d is not a relais pin!",
            channel,
            errorclass = ValueError
        ):
            return

        if self.CheckForError(
            state in (RELAIS_ON, RELAIS_OFF),
            "State %d is not valid for relais!",
            state,
            errorclass = ValueError
        ):
            return

        self.debug("Output %d to pin %d.", state, channel)
        GPIO.output(channel, state)
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

    def SwitchIndoorLight(self, swon:bool):
        """
        Schaltet die Innenbeleuchtung ein, wenn 'swon' True ist. (sonst aus)
        """
        self.light_state_indoor = swon
        GPIO.output(LIGHT_INDOOR, RELAIS_ON if swon else RELAIS_OFF)
        self.info("Switched indoor light %s", "on" if swon else "off")

    def IsIndoorLightOn(self):
        return self.light_state_indoor

    def IsOutdoorLightOn(self):
        return self.light_state_outdoor
    # -----------------------------------------------------------------------------------
    # ---- TÜR --------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------
    def IsDoorOpen(self):
        return GPIO.input(REED_UPPER) == REED_CLOSED

    def IsDoorClosed(self):
        return GPIO.input(REED_LOWER) == REED_CLOSED

    def IsDoorMoving(self):
        return 0 != (self.door_state & Board.DOOR_MOVING)

    def OnUpperReedClosed(self, channel):
        """
        Event-Handler für das Triggern des oberen Magnetschalters.
        Wenn die Bewegungsrichtung nach unten ist, wird
        das Ereignis ignoriert, sonst an OnReedClosed weitergegeben.
        """
        if self.door_state == Board.DOOR_MOVING_DOWN:
            self.warn("Received upper reed closed event although moving down, ignored.")
            return        
        self.info("Upper reed closed.")
        return self.OnReedClosed(channel)

    def OnLowerReedClosed(self, channel):
        """
        Event-Handler für das Triggern des unteren Magnetschalters.
        Wenn die Bewegungsrichtung nach oben ist, wird
        das Ereignis ignoriert, sonst an OnReedClosed weitergegeben.
        """
        if self.door_state == Board.DOOR_MOVING_UP:
            self.warn("Received lower reed closed event although moving up, ignored.")
            return
        self.info("Lower reed closed.")
        return self.OnReedClosed(channel)

    def OnReedClosed(self, channel):
        """
        Eventhandler für das Erreichen eines Magnetkontakt (Pin an
        'channel' geht auf LOW).

        Schaltet die beiden Relais für Motor-An und Richtung auf AUS
        und setzt den Status der Tür auf "not moving".

        Wenn '_waiter' gesetzt ist, wird dieses als Condition behandelt,
        benachrichtigt und auf None gesetzt.

        Args:
            channel: Der Kanal, der das Event ausgelöst hat.
                Dieser kann -1 sein, wenn der Handler wegen Not-Aus
                gerufen wurde (siehe StopDoor).
        """
        # in jedem Fall halten wir den Motor an
        GPIO.output(MOTOR_ON, RELAIS_OFF)
        
        # und die Richtung setzen wir auch zurück (damit das Relais aus ist)
        GPIO.output(MOVE_DIR, MOVE_UP)

        self.door_state = Board.DOOR_NOT_MOVING

        if self._waiter:
            with self._wait_condition:
                self._waiter.notify_all()
                self._waiter = None

        self.CallStateChangeHandler()

        if (channel >= 0) and (channel not in (REED_UPPER, REED_LOWER)):
            self.error("Reed event handler got unexpected channel %r.", channel)

    def _DoorWait(self, action, waittime = None):
        result = False
        if not waittime is None:
            self._waiter = self._wait_condition
            self.debug("Waiting in %r for %.4f seconds.", action, waittime)
            with self._wait_condition:
                result = self._waiter.wait(waittime)
                self._waiter = None
            if result:
                self.debug("%r has been signaled with waittime.", action)
            else:
                self.warn("Expected %r has not been signaled within %.4f seconds.", action, waittime)
        return result            

    def _DoorTimerControl(self, duration, state, direction):
        self.door_state = state
        GPIO.output(MOVE_DIR, direction)   # als erstes das Richtungs-Relais schalten
        GPIO.output(MOTOR_ON, RELAIS_ON) # dann den Motor anmachen
        # und jetzt warten
        time.sleep(duration)
        self.door_state = Board.DOOR_NOT_MOVING
        return True

    def OpenDoor(self, duration:float = DOOR_MOVE_UP_TIME, from_timer: bool = False):

        self.debug("OpenDoor(duration = %r, from_timer = %r)", duration, from_timer)
        
        # wenn der Timer steuert, benutzen wir die Wartezeit, da der Stromzaun
        # Interferenzen erzeugt und die Reeds keine Signale liefern
        if from_timer:
            return self._DoorTimerControl(duration, Board.DOOR_MOVING_UP, MOVE_UP)

        if self.IsDoorMoving():
            self.warn('Received OpenDoor command while door is currently moving, ignored.')
            return -1 # die tür ist bereits in Bewegung, wir machen hier erstmal nichts

        if self.IsDoorOpen():
            self.warn('Received OpenDoor command while door is already open, ignored.')
            return -2

        self.door_state = Board.DOOR_MOVING_UP

        GPIO.output(MOVE_DIR, MOVE_UP)   # als erstes das Richtungs-Relais schalten
        GPIO.output(MOTOR_ON, RELAIS_ON) # dann den Motor anmachen

        return self._DoorWait("OpenDoor", duration)

    def CloseDoor(self, duration:float = DOOR_MOVE_DOWN_TIME, from_timer: bool = False):
        """
        Wie 'OpenDoor', allerdings in die andere Richtung.
        """
        self.debug("CloseDoor(duration = %r, from_timer = %r)", duration, from_timer)

        # wenn der Timer steuert, benutzen wir die Wartezeit, da der Stromzaun
        # Interferenzen erzeugt und die Reeds keine Signale liefern
        if from_timer:
            return self._DoorTimerControl(duration, Board.DOOR_MOVING_DOWN, MOVE_DOWN)

        if self.IsDoorMoving():
            self.warn('Received CloseDoor command while door is currently moving, ignored.')
            return -1 # die tür ist bereits in Bewegung, wir machen hier erstmal nichts
        if self.IsDoorClosed():
            self.warn('Received CloseDoor command while door is already closed, ignored.')
            return -2

        self.door_state = Board.DOOR_MOVING_DOWN

        GPIO.output(MOVE_DIR, MOVE_DOWN) # als erstes das Richtungs-Relais schalten
        GPIO.output(MOTOR_ON, RELAIS_ON) # dann den Motor anmachen

        return self._DoorWait("CloseDoor", duration)

    def StopDoor(self):
        """
        Hält die Tür an (insofern sie sich gerade bewegt).
        Ruft dazu einfach 'OnReedClosed' mit Kanal -1.
        """
        self.info("Door stop received, stopping motor.")
        self.OnReedClosed(-1)
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
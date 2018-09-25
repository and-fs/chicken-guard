#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
import threading
import os
from shared import LoggableClass
from gpio import GPIO, SMBus
from config import * # pylint: disable=W0614
# ---------------------------------------------------------------------------------------
class Sensors(LoggableClass):
    """
    Diese Klasse dient zum Auslesen des Multisensors PCF8591 an I2C #0
    auf PIN #3 (SDA) und PIN #4 (SCL).
    """
    
    SMBUS_ADDR = 0x48       # Adresse des I2C-Device (PCF8591 an I2C 0, PIN 3 / 5 bei ALT0 = SDA / SCL)
    SMBUS_CH_LIGHT = 0x40   # Kanal des Fotowiderstand (je kleiner der Wert desto heller)
    SMBUS_CH_AIN  = 0x41    # AIN
    SMBUS_CH_POTI = 0x42    # Potentiometer-Kanal
    SMBUS_CH_TEMP = 0x43    # Temperatur
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
        self.debug("Reading temperature.")
        return self.ReadChannel(self.SMBUS_CH_TEMP)

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

        self._wait_lock = threading.Lock()
        self._wait_condition = threading.Condition(self._wait_lock)
        self._waiter = None

        self.movement_stop_callback = None
        self.state_change_handler = None

        GPIO.setmode(GPIO.BOARD)
        self.logger.debug("Settings pins %s to OUT.", OUTPUT_PINS)
        for pin in OUTPUT_PINS:
            GPIO.setup(pin, GPIO.OUT, initial = RELAIS_OFF)
        self.logger.debug("Settings pins %s to IN.", INPUT_PINS)
        for pin in INPUT_PINS:
            GPIO.setup(pin, GPIO.IN)

        GPIO.add_event_detect(SHUTDOWN_BUTTON, GPIO.RISING, self.OnShutdownButtonPressed, bouncetime = 200)

        self.CheckForError(
            not (self.IsDoorOpen() and self.IsDoorClosed()),
            "Inconsistent door contact state, door is signaled both to be open and closed, check configuration!"
        )

        # damit wir die Bewegung sofort anhalten, wenn der jeweilige
        # Magnetkontakt geschlossen wird, setzen wir einen Interrupt.
        # Da der Magnetkontakt mit LOW geschlossen wird, soll das Event auf
        # die fallende Flanke (Wechsel von HIGH nach LOW) reagieren
        GPIO.add_event_detect(REED_UPPER, GPIO.FALLING, self.OnReedClosed, bouncetime = 250)
        GPIO.add_event_detect(REED_LOWER, GPIO.FALLING, self.OnReedClosed, bouncetime = 250)

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
        self.info("Switching outdoor light %s", "on" if swon else "off")
        GPIO.output(LIGHT_OUTDOOR, RELAIS_ON if swon else RELAIS_OFF)

    def SwitchIndoorLight(self, swon:bool):
        """
        Schaltet die Innenbeleuchtung ein, wenn 'swon' True ist. (sonst aus)
        """
        self.light_state_indoor = swon
        self.info("Switching indoor light %s", "on" if swon else "off")
        GPIO.output(LIGHT_INDOOR, RELAIS_ON if swon else RELAIS_OFF)

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

    def OnReedClosed(self, channel):
        """
        Eventhandler für das Erreichen eines Magnetkontakt (Pin an
        'channel' geht auf LOW).

        Schaltet die beiden Relais für Motor-An und Richtung auf AUS
        und setzt den Status der Tür auf "not moving".

        Wenn 'movement_stop_callback' gesetzt ist, wird es aufgerufen und
        auf None gesetzt. Exceptions werden aufgefangen und geloggt.

        Wenn '_waiter' gesetzt ist, wird dieses als Condition behandelt,
        benachrichtigt und auf None gesetzt.

        Args:
            channel: Der Kanal, der das Event ausgelöst hat.
                Dieser kann -1 sein, wenn der Handler wegen Not-Aus
                gerufen wurde (siehe StopDoor).
        """
        if channel > 0:
            self.info("%s reed contact closed, stopping motor.",
                "Upper" if channel == REED_UPPER else "Lower"
            )
        else:
            self.info("Door stop received, stopping motor.")
        
        # in jedem Fall halten wir den Motor an
        GPIO.output(MOTOR_ON, RELAIS_OFF)
        
        # und die Richtung setzen wir auch zurück (damit das Relais aus ist)
        GPIO.output(MOVE_DIR, MOVE_DOWN)

        self.door_state = Board.DOOR_NOT_MOVING

        if self.movement_stop_callback:
            callback = self.movement_stop_callback
            self.movement_stop_callback = None
            self.debug("Calling movement stop callback.")
            try:
                callback(channel in (REED_UPPER, REED_LOWER))
            except Exception:
                self.exception("Error while calling movement stop callback.")

        if self._waiter:
            with self._wait_lock:
                self._waiter.notify_all()
                self._waiter = None

        self.CallStateChangeHandler()

        if (channel >= 0) and (channel not in (REED_UPPER, REED_LOWER)):
            self.error("Reed event handler got unexpected channel %r.", channel)
            return

    def OpenDoor(self, callback = None, waittime = None):
        """
        Fährt die Tür nach oben und gibt zurück, ob das Schließen eingeleitet wurde.
        Falls die Tür bereits in Bewegung oder sogar offen ist, passiert nichts.
        
        Args:
            callable: Wenn angegeben, muss es sich hier um eine Funktion handeln,
                die ein bool als Argumente erwartet. Dieses gibt an, ob die
                Tür die Endposition erreicht hat.
                Wird gerufen, sobald die Tür anhält.
                Der Aufruf erfolgt aus einem anderen Thread.
            waittime: Wenn nicht None handelt es sich hier um eine Wartezeit in
                Sekunden als Float (mit Bruchteilen), die diese Funktion wartet
                bis die Tür offen ist.

        Returns:
            Eine Zahl < 0 im Fehlerfall, sonst 1.
            Wurde eine 'waittime' angegeben, ist der Rückgabewert 0 wenn das Timeout
            ohne Signalisierung überschritten wurde.
        """

        self.debug("OpenDoor(%r, %r)", callback, waittime)
        if self.IsDoorMoving():
            self.warn('Received OpenDoor command while door is currently moving, ignored.')
            return -1 # die tür ist bereits in Bewegung, wir machen hier erstmal nichts
        if self.IsDoorOpen():
            self.warn('Received OpenDoor command while door is already open, ignored.')
            return -2

        self.CheckForError(self._waiter is None,
            "Waiting condition is set when using OpenDoor!"
        )

        if waittime:
            self._waiter = self._wait_condition

        self.debug("Setting callback for OpenDoor to %r", callback)
        self.movement_stop_callback = callback
        self.door_state = Board.DOOR_MOVING_UP

        GPIO.output(MOVE_DIR, MOVE_UP)   # als erstes das Richtungs-Relais schalten
        GPIO.output(MOTOR_ON, RELAIS_ON) # dann den Motor anmachen

        result = 1
        if not waittime is None:
            self.debug("Waiting in OpenDoor for %.4f seconds.", waittime)
            with self._wait_lock:
                result = 1 if self._waiter.wait(waittime) else 0
            self._waiter = None
            if result:
                self.debug("Door open has been signaled with waittime.")
            else:
                self.warn("Expected 'door open' has not been signaled within %.4f seconds.", waittime)
        return result

    def CloseDoor(self, callback = None, waittime = None):
        """
        Wie 'OpenDoor', allerdings in die andere Richtung.
        """
        self.debug("CloseDoor(%r, %r)", callback, waittime)
        if self.IsDoorMoving():
            self.warn('Received CloseDoor command while door is currently moving, ignored.')
            return -1 # die tür ist bereits in Bewegung, wir machen hier erstmal nichts
        if self.IsDoorClosed():
            self.warn('Received CloseDoor command while door is already closed, ignored.')
            return -2

        self.CheckForError(self._waiter is None,
            "Waiting condition is set when using CloseDoor!"
        )

        if waittime:
            self._waiter = self._wait_condition

        self.debug("Setting callback for OpenDoor to %r", callback)
        self.movement_stop_callback = callback
        self.door_state = Board.DOOR_MOVING_UP

        GPIO.output(MOVE_DIR, MOVE_DOWN) # als erstes das Richtungs-Relais schalten
        GPIO.output(MOTOR_ON, RELAIS_ON) # dann den Motor anmachen

        result = 1
        if not waittime is None:
            self.debug("Waiting in CloseDoor for %.4f seconds.", waittime)
            with self._wait_lock:
                result = 1 if self._waiter.wait(waittime) else 0
            self._waiter = None
            if result:
                self.debug("Door closed has been signaled within waittime.")
            else:
                self.warn("Expected 'door closed' has not been signaled within %.4f seconds.", waittime)
        return result

    def StopDoor(self):
        """
        Hält die Tür an (insofern sie sich gerade bewegt).
        Ruft dazu einfach 'OnReedClosed' mit Kanal -1.
        """
        self.debug("StopDoor")
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
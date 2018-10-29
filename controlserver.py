#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Script startet einen XMLRPC-Server unter der
Adresse config.CONTROLLER_HOST auf dem Port config.CONTROLLER_PORT
und stellt darüber die Schnittstelle zum Board zur Verfügung.
Alle Zugriffe sollten über diesen Server erfolgen (abgesehen vom TFT),
da so parallele Zugriffe ausgeschlossen sind.

Als cronjob mit Start bei jedem Boot einrichten::
    sudo crontab -e
    reboot /usr/bin/python3 /usr/chickenguard/controlserver.py
"""
# ------------------------------------------------------------------------
import os
import xmlrpc.server
import socketserver
import threading
import time
import datetime
# ------------------------------------------------------------------------
import shared
import board
import sunrise
from shared import LoggableClass, resource_path
from config import * # pylint: disable=W0614
# ------------------------------------------------------------------------
class JobTimer(LoggableClass):
    def __init__(self, controller):
        LoggableClass.__init__(self, name = 'JobTimer')
        self.controller = controller
        self.terminate = False
        self.terminate_condition = threading.Condition()
        self.thread = threading.Thread(target = self, name = 'JobTimer', daemon = True)
        self.last_sunrise_check = 0
        self.last_door_check = 0
        self.next_sensor_check = 0
        self.light_switch_off_time = None
        self.light_switch_on_time = None

    def Terminate(self):
        self.info("Terminating JobTimer.")
        with self.terminate_condition:
            self.terminate = True
            self.terminate_condition.notify_all()

    def Start(self):
        self.info("Starting JobTimer.")
        self.thread.start()

    def Join(self, timeout = None):
        if not self.IsRunning():
            return True
        with self.terminate_condition:
            return self.terminate_condition.wait(timeout)

    def IsRunning(self):
        return self.thread.is_alive()

    def ShouldTerminate(self):
        with self.terminate_condition:
            return self.terminate

    def WakeUp(self):
        self.debug("WakeUp called.")
        with self.terminate_condition:
            self.terminate_condition.notify_all()

    def ResetCheckTimes(self):
        with self.terminate_condition:
            self.last_door_check = 0
            self.last_sunrise_check = 0
            self.terminate_condition.notify_all()

    def __call__(self):
        try:
            self._run()
        except Exception:
            self.exception("Error in JobTimer thread loop.")

    def DoSunriseCheck(self, dtnow, now, open_time, close_time):
        # aktuelle Sonnenaufgangs / Untergangszeiten holen
        if self.last_sunrise_check + SUNRISE_INTERVAL < now:
            # es wird wieder mal Zeit (dawn = Morgens, dusk = Abends)
            self.info("Doing sunrise time check.")
            open_time, close_time = sunrise.GetSuntimes(dtnow)
            # jetzt noch die nächsten beiden Aktionen ermitteln (für
            # die Anzeige im Display)
            next_steps = sunrise.GetNextActions(dtnow, open_time, close_time)
            self.controller.SetNextActions(next_steps)
            self.last_sunrise_check = now

            if SWITCH_LIGHT_ON_BEFORE_CLOSING > 0:
                # Wichtig: wenn das Licht zur Schließzeit der Tür automatisch
                # getriggert wird, darf in dieser Zeit die Lichtschaltzeit nicht
                # berechnet werden!
                can_calculate = True
                # die Start- und Endzeit des Intervall runden wir noch in die entsprechende
                # Richtung um die Zeit des Türprüfintervalls (weil in diesem auch die Lichtschaltzeiten
                # geprüft werden)
                if not self.light_switch_on_time is None:
                    light_ivl_start = self.light_switch_on_time - datetime.timedelta(seconds = DOORCHECK_INTERVAL)
                    light_ivl_end = self.light_switch_on_time + datetime.timedelta(seconds = DOORCHECK_INTERVAL)

                    if (dtnow >= light_ivl_start) and (dtnow <= light_ivl_end):
                        # hier sind wir genau in der Lichtschaltzeit, also lassen wir hier die Berechnung
                        # aus und führen wir diese erst beim nächsten Mal durch, das reicht aus.
                        self.info("Skipped light switch times calculation due to beeing currently in light interval.")
                        can_calculate = False

                if can_calculate:
                    # jetzt ermitteln wir die Einschaltzeit für die Innenbeleuchtung
                    for item in next_steps:
                        if item is None:
                            break
                        dt, action = item
                        if dt < dtnow:
                            continue
                        if action == DOOR_CLOSED:
                            self.light_switch_on_time = dt - datetime.timedelta(seconds = SWITCH_LIGHT_ON_BEFORE_CLOSING)
                            self.light_switch_off_time = dt + datetime.timedelta(seconds = SWITCH_LIGHT_OFF_AFTER_CLOSING )
                            self.info("Calculated new light switch times: on at %s, off at %s.", self.light_switch_on_time, self.light_switch_off_time)
        return (open_time, close_time)

    def DoDoorCheck(self, dtnow, now, open_time, close_time):
        if self.controller.automatic == DOOR_AUTO_OFF:
            # wenn am controller die Automatik deaktiviert ist,
            # müssen wir prüfen, ob diese wieder angeschaltet werden muss
            if self.controller.automatic_enable_time <= now:
                self.info("Enabling door automatic due to reaching manual control timeout.")
                self.controller.EnableAutomatic()

        if self.controller.automatic == DOOR_AUTO_ON:
            # müssen wir die Tür öffnen / schließen?
            if self.last_door_check + DOORCHECK_INTERVAL < now:
                self.logger.debug("Doing door automatic check.")
                self.last_door_check = now
                action = sunrise.GetDoorAction(dtnow, open_time, close_time)
                if action == DOOR_CLOSED:
                    if not self.controller.IsDoorClosed():
                        self.info("Closing door, currently is night.")
                        self.controller._CloseDoorFromTimer()
                else:
                    # wir sind nach Sonnenauf- aber vor Sonnenuntergang
                    if not self.controller.IsDoorOpen():
                        self.info("Opening door, currently is day.")
                        self.controller._OpenDoorFromTimer()
        else:
            self.logger.debug("Skipped door check, automatic is off.")

    def DoSensorCheck(self, now):
        if self.next_sensor_check < now:
            self.next_sensor_check = now + SENSOR_INTERVALL
            self.controller._ReadSensors()

    def DoLightCheck(self, dtnow):
        if (self.controller.automatic == DOOR_AUTO_ON) and (not self.light_switch_on_time is None):
            if dtnow >= self.light_switch_off_time:
                if self.controller.IsIndoorLightOn():
                    self.info("Switching light off %.0f seconds after closing door.", SWITCH_LIGHT_OFF_AFTER_CLOSING)
                    self.controller.SwitchIndoorLight(False)
                self.light_switch_on_time = None
                self.light_switch_off_time = None
            elif dtnow >= self.light_switch_on_time:
                if not self.controller.IsIndoorLightOn():
                    self.info("Switching light on %.0f seconds before closing door.", SWITCH_LIGHT_ON_BEFORE_CLOSING)
                    self.controller.SwitchIndoorLight(True)

    def _run(self):
        self.info("JobTimer started.")
        open_time, close_time = sunrise.GetSuntimes(datetime.datetime.now())
        while not self.ShouldTerminate():
            now = time.time()
            dtnow = datetime.datetime.now()

            # Öffnen / Schließen berechnen
            (open_time, close_time) = self.DoSunriseCheck(dtnow, now, open_time, close_time)

            # Türstatus prüfen
            self.DoDoorCheck(dtnow, now, open_time, close_time)

            # Licht prüfen
            self.DoLightCheck(dtnow)

            # Sensorwerte holen
            self.DoSensorCheck(now)

            if self.ShouldTerminate():
                break

            with self.terminate_condition:
                if self.terminate_condition.wait(DOORCHECK_INTERVAL):
                    self.debug("Terminate condition is notified.")

        # falls jetzt noch jemand im Join hängt, wird der auch benachrichtigt.
        with self.terminate_condition:
            self.terminate_condition.notify_all()

        self.info("JobTimer stopped.")
# ------------------------------------------------------------------------
class Controller(LoggableClass):
    """
    Gateway zum Board.
    """
    def __init__(self, start_jobs = True):
        """
        :param start_jobs: Gibt an, ob der :class:`JobTimer` gestartet
            werden soll.
        """
        LoggableClass.__init__(self, name = "Controller")
        self.board = board.Board()

        #: Liste der nächsten Schritte, jeder besteht aus einem Tupel
        #: mit Zeitstempel und der Aktion, die dann vorgenommen wird
        #: (DOOR_OPEN oder DOOR_CLOSED)
        self.next_actions = tuple()

        #: Gibt an, ob die Tür über die Automatic gesteuert wird
        #: oder manuell. Wird vom job_timer verwendet.
        self.automatic = DOOR_AUTO_ON

        #: Zeitpunkt an dem die Türautomatik wieder aktiviert wird, wenn
        #: der Türstatur DOOR_AUTO_OFF ist.
        self.automatic_enable_time = -1

        self._state_lock = threading.Lock()
        self._state = (False, self.board.GetState())
        self._state_cond = threading.Condition(self._state_lock)

        self.temperature = 0.0
        self.light_sensor = 0
        self.sensor_file = resource_path / SENSORFILE

        self.board.SetStateChangeHandler(self._BoardStateChanged)

        self.job_timer = JobTimer(self)
        if start_jobs:
            self.job_timer.Start()

    def SetNextActions(self, actions):
        self.logger.debug("Received next actions list: %s", actions)
        if actions == self.next_actions:
            # wenn sich nichts geändert hat, machen wir auch nichts
            return
        # ansonsten merken und den State-Setter rufen
        # (der setzt dann den Status entsprechend)
        self.next_actions = actions
        self._UpdateBoardState()

    def SwitchIndoorLight(self, swon: bool) -> bool:
        self.debug("Received indoor light switch to %r request.", swon)
        self.board.SwitchIndoorLight(swon)
        return swon

    def SwitchOutdoorLight(self, swon: bool) -> bool:
        self.debug("Received outdoor light switch to %r request.", swon)
        self.board.SwitchOutdoorLight(swon)
        return swon

    def IsIndoorLightOn(self) -> bool:
        return self.board.IsIndoorLightOn()

    def IsOutdoorLightOn(self) -> bool:
        return self.board.IsOutdoorLightOn()

    def _CloseDoorFromTimer(self):
        self.info("Timer requests door to close.")
        return self.board.CloseDoor()

    def _OpenDoorFromTimer(self):
        self.info("Timer requests door to open.")
        return self.board.OpenDoor()

    def CloseDoor(self) -> bool:
        """
        Schickt das Kommando zum Schließen der Tür an den ControlServer.
        Mit DisableAutomatic() wird die
        Automatik vorübergehend deaktiviert.
        """
        self.info("Received CloseDoor request.")
        self.DisableAutomatic()
        return self.board.CloseDoor()

    def OpenDoor(self) -> bool:
        """
        Schickt das Kommando zum Öffnen der Tür an den ControlServer.
        Mit DisableAutomatic() wird die
        Automatik vorübergehend deaktiviert.
        """
        self.info("Received OpenDoor request.")
        self.DisableAutomatic()
        return self.board.OpenDoor()

    def StopDoor(self):
        """
        Schickt das Kommando zum Stoppen der Tür an den ControlServer.
        Wird nicht vom Automat benutzt, von daher wird hier immer von
        einer manuellen Aktion ausgegangen und die Automatik mit
        DisableAutomatic() vorübergehend ausser Kraft gesetzt.
        """
        self.debug("Received StopDoor request.")
        self.board.StopDoor()
        self.DisableAutomatic()

    def IsDoorOpen(self) -> bool:
        return self.board.IsDoorOpen()

    def IsDoorClosed(self) -> bool:
        return self.board.IsDoorClosed()

    def SwitchDoorAutomatic(self, new_state:int) -> int:
        self.debug("Switching door automatic to %d.", new_state)
        if new_state == 1:
            self.EnableAutomatic()
        else:
            self.DisableAutomatic(new_state == -1)
        return self.automatic

    def _AddStateInfo(self, state: dict):
        state.update(
            next_actions = self.next_actions,
            automatic = self.automatic,
            automatic_enable_time = self.automatic_enable_time,
            temperature = self.temperature,
            light_sensor = self.light_sensor
        )

    def GetBoardState(self) -> dict:
        self.debug("Received state request.")
        state = self.board.GetState()
        self._AddStateInfo(state)
        return state

    def _UpdateBoardState(self):
        """
        Wird innerhalb dieser Instanz gerufen um zu signalisieren,
        dass sich an einem der Zustände etwas geändert hat.
        Hierbei kann es sich nur um einen der Werte handeln, die
        bei _AddStateInfo() hinzugefügt werden.
        """
        state = self.board.GetState()
        self._BoardStateChanged(state)

    def _BoardStateChanged(self, state: dict):
        """
        Handler für Änderungen am Status des Boards.
        Reichert den Board-Status mit Daten aus _AddStateInfo() an.
        Wird entweder über die self.board-Instanz direkt bei dort
        getriggerten Änderungen oder via _UpdateBoardState() aufgerufen.
        Benachrichtig die Status-Condition, so das in WaitForStateChange()
        wartende Threads weiterarbeiten können.
        """
        self._AddStateInfo(state)
        self.info("Board state changed: %s", state)
        with self._state_lock:
            self._state = (True, state)
            self._state_cond.notify_all()

    def WaitForStateChange(self, waittime = 30.0) -> tuple:
        with self._state_lock:
            self._state_cond.wait(timeout = waittime)
            notified, state = self._state
            if notified:
                self._state = (False, state)
        return (notified, state)

    def GetNextAction(self):
        dtnow = datetime.datetime.now()
        for dt, action in self.next_actions:
            if dtnow < dt:
                return (dt, action)
        return (None, None)

    def DisableAutomatic(self, forever = False):
        """
        Deaktiviert die Tür-Automatik für die in DOOR_AUTOMATIC_OFFTIME
        gesetzte Anzahl von Sekunden.
        """
        if self.automatic == DOOR_AUTO_DEACTIVATED:
            return

        if forever:
            self.automatic = DOOR_AUTO_DEACTIVATED
            self.warn("Door automatic disabled.")
        else:
            # nur wenn die Automatik nicht bereits dauerhaft deaktiviert war,
            # stellen wir hier eine zeitbegrenzte Automatik ein
            self.automatic_enable_time = time.time() + DOOR_AUTOMATIC_OFFTIME
            self.automatic = DOOR_AUTO_OFF
            self.info("Door automatic disabled for the next %.2f seconds", float(DOOR_AUTOMATIC_OFFTIME))

        self._UpdateBoardState()

    def EnableAutomatic(self):
        """
        Aktiviert die Türautomatik (wieder).
        """
        if self.automatic == DOOR_AUTO_ON:
            return
        self.automatic = DOOR_AUTO_ON
        self.automatic_enable_time = -1
        self.info("Door automatic has been enabled.")
        self._UpdateBoardState()
        self.job_timer.WakeUp()

    def CleanUp(self):
        self.job_timer.Terminate()
        self.job_timer.Join(6.0)
        self.job_timer = None

    def _ReadSensors(self):
        """
        Wird im Intervall `SENSOR_INTERVAL` vom JobTimer aufgerufen.
        Hinterlegt die Messergebnisse der angebundenen Sensoren und
        aktualisiert den Board-Status.
        """
        self.temperature = self.board.GetTemperature()
        self.light_sensor = self.board.GetLight()
        self.info("Measured sensors. Light = %d, temperature = %.1f", self.light_sensor, self.temperature)
        self._UpdateBoardState()
        try:
            with self.sensor_file.open('w') as f:
                f.write(SENSOR_LINE_TPL % (self.light_sensor, self.temperature))
        except Exception:
            self.exception("Error while writing to %s", self.sensor_file)
# ------------------------------------------------------------------------
class DataServer(socketserver.ThreadingMixIn, xmlrpc.server.SimpleXMLRPCServer):
    """
    SimpleXMLRPC-Server, jeder Request wird in einem eigenen Thread ausgeführt.
    """
    def __init__(self, *args, **kwargs):
        self.logger = shared.getLogger("xmlrpc-server")
        super().__init__(*args, **kwargs)

    def _dispatch(self, method, params):
        """
        Überlädt die Basisklassenmethode um etwaige Exceptions
        im logger auszugeben.
        """
        try:
            return super()._dispatch(method, params)
        except Exception:
            self.logger.exception("Error in %s%r.", method, params)
            raise
# ------------------------------------------------------------------------
def main():
    """
    Initialisiert das Logging und den Controller und startet diesen.
    Ausführung bis CTRL-C oder `kill -INT <PID>`.
    """
    logger = shared.getLogger("controller")
    address = ("", CONTROLLER_PORT)
    logger.info("Starting XML-RPC-Server as %r, pid = %s", address, os.getpid())
    try:
        try:
            controller = Controller()
        except Exception:
            logger.exception("Error during initialization, stopped.")
            return

        try:
            ds = DataServer(address, allow_none = True)
            ds.register_instance(controller)
            logger.debug("Start serving.")
            ds.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutdown due to keyboardinterrupt.")
        except Exception:
            logger.exception("Unhandled error, stopped.")
        finally:
            controller.CleanUp()
    finally:
        logger.info("Finished.")
        shared.logging.shutdown()
# ------------------------------------------------------------------------
if __name__ == "__main__":
    main()

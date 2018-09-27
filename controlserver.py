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
    reboot /usr/bin/python3 /usr/www/scripts/controlserver.py
"""
# ------------------------------------------------------------------------
import xmlrpc.server
import socketserver
import threading
import time
import datetime
# ------------------------------------------------------------------------
import shared
import board
import sunrise
from shared import LoggableClass
from config import * # pylint: disable=W0614
# ------------------------------------------------------------------------
class JobTimer(LoggableClass):
    def __init__(self, controller):
        LoggableClass.__init__(self, name = 'JobTimer')
        self.controller = controller
        self.terminate = False
        self.terminate_condition = threading.Condition()
        self.thread = threading.Thread(target = self, name = 'JobTimer')
        self.last_sunrise_check = 0
        self.last_door_check = 0

    def Terminate(self):
        self.info("Termination JobTimer.")
        with self.terminate_condition:
            self.terminate = True
            self.terminate_condition.notify_all()

    def Start(self):
        self.info("Starting JobTimer.")
        self.thread.start()

    def Join(self):
        with self.terminate_condition:
            self.terminate_condition.wait()

    def ShouldTerminate(self):
        with self.terminate_condition:
            return self.terminate

    def WakeUp(self):
        with self.terminate_condition:
            self.terminate_condition.notify_all()

    def __call__(self):
        self.info("JobTimer started.")
        dawn, dusk = sunrise.GetSuntimes(datetime.datetime.now())
        while not self.ShouldTerminate():
            now = time.time()
            dtnow = datetime.datetime.now()

            # aktuelle Sonnenaufgangs / Untergangszeiten holen
            if self.last_sunrise_check + SUNRISE_INTERVAL < now:
                # es wird wieder mal Zeit (dawn = Morgens, dusk = Abends)
                self.info("Doing sunrise time check.")
                dawn, dusk = sunrise.GetSuntimes(dtnow)
                # jetzt noch die nächsten beiden Aktionen ermitteln (für
                # die Anzeige im Display)
                if dtnow < dawn:
                    # damit haben wir zwei, das reicht
                    next_steps = [(dawn, DOOR_OPEN),
                                  (dusk, DOOR_CLOSED)]
                else:
                    # jetzt müssen wir uns noch den nächsten Tag holen
                    ndawn, ndusk = sunrise.GetSuntimes(dtnow + datetime.timedelta(days = 1))
                    if dtnow < dusk:
                        next_steps = [(dusk, DOOR_CLOSED),
                                      (dawn, DOOR_OPEN)]
                    else:
                        next_steps = [(ndawn, DOOR_OPEN),
                                      (ndusk, DOOR_CLOSED)]
                self.controller.SetNextActions(next_steps)
                self.last_sunrise_check = now

            if self.controller.automatic:
                # müssen wir die Tür öffnen / schließen?
                if self.last_door_check + DOORCHECK_INTERVAL < now:
                    self.logger.debug("Doing door automatic check.")                
                    self.last_door_check = now
                    action = sunrise.GetDoorAction(dtnow, dawn, dusk)
                    if action == DOOR_CLOSED:
                        if not self.controller.IsDoorClosed():
                            self.info("Closing door, currently is after night.")
                            self.controller.CloseDoor()
                    else:
                        # wir sind nach Sonnenauf- aber vor Sonnenuntergang
                        if not self.controller.IsDoorOpened():
                            self.info("Opening door, currently is day.")
                            self.controller.OpenDoor()
            else:
                self.logger.debug("Skipped door check, automatic is off.")

            with self.terminate_condition:
                self.terminate_condition.wait(DOORCHECK_INTERVAL)

        self.info("JobTimer stopped.")
# ------------------------------------------------------------------------
class Controller(LoggableClass):
    """
    Gateway zum Board.
    """
    def __init__(self):
        LoggableClass.__init__(self, name = "Controller")
        self.board = board.Board()

        #: Liste der nächsten Schritte, jeder besteht aus einem Tupel
        #: mit Zeitstempel und der Aktion, die dann vorgenommen wird
        #: (DOOR_OPEN oder DOOR_CLOSED)
        self.next_actions = []

        #: Gibt an, ob die Tür über die Automatic gesteuert wird
        #: oder manuell. Wird vom job_timer verwendet.
        self.automatic = True

        self._state_lock = threading.Lock()
        self._state = (False, self.board.GetState())
        self._state_cond = threading.Condition(self._state_lock)
        self.board.SetStateChangeHandler(self._BoardStateChanged)
        self.job_timer = JobTimer(self)

    def SetNextActions(self, actions):
        self.logger.debug("Received next actions list: %s", actions)
        if actions == self.next_actions:
            # wenn sich nichts geändert hat, machen wir auch nichts
            return
        # ansonsten merken und den State-Setter rufen
        # (der setzt dann den Status entsprechend)
        self.next_actions == actions
        with self._state_lock:
            state = self._state[1].copy()
        self._BoardStateChanged(state)

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

    def CloseDoor(self) -> bool:
        self.debug("Received CloseDoor request.")
        result = self.board.CloseDoor(waittime = MAX_DOOR_MOVE_DURATION)
        return result == 1

    def OpenDoor(self) -> bool:
        self.debug("Received OpenDoor request.")
        result = self.board.OpenDoor(waittime = MAX_DOOR_MOVE_DURATION)
        return result == 1

    def StopDoor(self):
        self.debug("Received StopDoor request.")
        self.board.StopDoor()

    def IsDoorOpen(self) -> bool:
        return self.board.IsDoorOpen()

    def IsDoorClosed(self) -> bool:
        return self.board.IsDoorClosed()

    def SwitchDoorAutomatic(self, auto_on:bool):
        self.debug("Switching door automatic %s.", "on" if auto_on else "off")
        self.automatic = auto_on
        if auto_on:
            # wenn die Automatic angeschalten wird, muss
            # der Job timer wieder ran.
            self.job_timer.WakeUp()
        return self.automatic

    def GetBoardState(self) -> dict:
        self.debug("Received state request.")
        state = self.board.GetState()
        state['next_actions'] = self.next_actions
        state['automatic'] = self.automatic
        return state

    def _BoardStateChanged(self, state):
        self.info("Board state changed: %s", state)
        state['next_actions'] = self.next_actions
        state['automatic'] = self.automatic
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

    def CleanUp(self):
        self.job_timer.Terminate()
        self.job_timer.Join()
        self.job_timer = None

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
    Ausführung bis CTRL-C.
    """
    logger = shared.getLogger("ctrl-server")
    address = (CONTROLLER_HOST, CONTROLLER_PORT)
    logger.info("Starting XML-RPC-Server as %r", address)
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

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
        self.thread = threading.Thread(target = self, name = 'JobTimer')
        self.last_sunrise_check = 0
        self.last_door_check = 0

    def Terminate(self):
        self.info("Termination JobTimer.")
        self.terminate = True

    def Start(self):
        self.info("Starting JobTimer.")
        self.thread.start()

    def __call__(self):
        self.info("JobTimer started.")
        dawn, dusk = sunrise.getSunTimes()
        while not self.terminate:
            now = time.time()

            # aktuelle Sonnenaufgangs / Untergangszeiten holen
            if self.last_sunrise_check + SUNRISE_INTERVAL < now:
                # es wird wieder mal Zeit (dawn = Morgens, dusk = Abends)
                self.info("Doing sunrise time check,")
                dawn, dusk = sunrise.getSunTimes()
                self.last_sunrise_check = now

            # müssen wir die Tür öffnen / schließen?
            if self.last_door_check + DOORCHECK_INTERVAL < now:
                self.last_door_check = now
                dtnow = datetime.datetime.now()
                if (dtnow > dawn) and (dtnow < dusk):
                    if self.controller.IsDoorClosed():
                        self.info("Opening open door, dawn has been reached.")
                        self.controller.OpenDoor()
                elif (dtnow > dusk) and (dtnow < dawn):
                    if self.controller.IsDoorOpened():
                        self.info("Closing open door, dusk has been reached.")
                        self.controller.CloseDoor()

            time.sleep(DOORCHECK_INTERVAL)
        self.info("JobTimer stopped.")
# ------------------------------------------------------------------------
class Controller(LoggableClass):
    """
    Gateway zum Board.
    """
    def __init__(self):
        LoggableClass.__init__(self, name = "Controller")
        self.board = board.Board()
        self._state_lock = threading.Lock()
        self._state = (False, self.board.GetState())
        self._state_cond = threading.Condition(self._state_lock)
        self.board.SetStateChangeHandler(self._BoardStateChanged)
        self.job_timer = JobTimer(self)

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

    def GetBoardState(self) -> dict:
        self.debug("Received state request.")
        return self.board.GetState()

    def _BoardStateChanged(self, state):
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

    def CleanUp(self):
        self.job_timer.Terminate()
        self.job_timer.join()
        self.job_timer = None
# ------------------------------------------------------------------------
class DataServer(socketserver.ThreadingMixIn, xmlrpc.server.SimpleXMLRPCServer):
    """
    SimpleXMLRPC-Server, jeder Request wird in einem eigenen Thread ausgeführt.
    """
    pass
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
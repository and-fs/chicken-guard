#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import * # pylint: disable=W0614
from config import *  # pylint: disable=W0614
import time
import controlserver
import datetime
# ---------------------------------------------------------------------------------------
class ControllerDummy(object):
    def __init__(self):
        self.door_closed = False
        self.actions = []
        self.automatic = DOOR_AUTO_ON
        self.automatic_enable_time = -1
        self.sensors_read = False
    def IsDoorClosed(self):
        return self.door_closed
    def CloseDoor(self):
        self.door_closed = True
    def IsDoorOpen(self):
        return not self.door_closed
    def OpenDoor(self):
        self.door_closed = False
    def SetNextActions(self, actions):
        self.actions = actions
    def EnableAutomatic(self):
        self.automatic = DOOR_AUTO_ON
        self.automatic_enable_time = -1
    def _ReadSensors(self):
        self.sensors_read = True
    def IsIndoorLightOn(self):
        return self.light_on
    def SwitchIndoorLight(self, swon):
        self.light_on = swon
# ---------------------------------------------------------------------------------------
@testfunction
def test():
    controlserver.SWITCH_LIGHT_OFF_AFTER_CLOSING = 5  # 5 Sekunden nach Schließen aus
    controlserver.SWITCH_LIGHT_ON_BEFORE_CLOSING = 10 # 10 Sekunden vor Schließen an

    controller = ControllerDummy()
    timer = controlserver.JobTimer(controller)

    check(not timer.IsRunning(), "Timer doesn't start itself.")
    check(not timer.ShouldTerminate(), "Termination flag is initially cleared.")

    timer.Terminate()
    check(timer.ShouldTerminate(), "Termination flag is set.")
    timer.terminate = False # und wieder zurücksetzen

    timer.Start()
    # kurz warten damit der Thread anlaufen kann
    time.sleep(0.2)
    check(timer.IsRunning(), "Timer runs after starting.")
    check(not timer.ShouldTerminate(), "Termination flag is still cleared.")
    
    t = time.time()
    timer.Join(1)
    t = time.time() - t
    check(t >= 1.0 and t < 1.1, "Timer join works in time.")
    check(not timer.ShouldTerminate(), "Termination flag is still cleared.")
    check(timer.IsRunning(), "Timer is still running after join.")

    check(len(controller.actions) == 2, "Actions have been calculated (1).")
    controller.actions = []
    timer.ResetCheckTimes()
    timer.Join(0.1)
    check(timer.last_door_check != 0, "Door check done when automatic is on.")
    check(timer.last_sunrise_check != 0, "Sunrise check has been done.")
    check(len(controller.actions) == 2, "Actions have been calculated (2).")

    controller.automatic = DOOR_AUTO_OFF
    controller.automatic_enable_time = time.time() + 1.0
    logger.info("Disabling automatic, enable time set to %s", controller.automatic_enable_time)
    timer.ResetCheckTimes()
    timer.Join(0.1)
    check(timer.last_door_check == 0, "Door check skipped when automatic is off.")

    logger.info("Resetted check times, joining timer for 1.5 seconds.")
    # jetzt müssen wir warten, bis die gesetzte Aktivierungszeit erreicht wurde
    timer.Join(1.5) 
    # danach sorgen wir dafür, dass wieder ein Durchlauf stattfindet
    timer.ResetCheckTimes()
    # und dem Thread nochmal kurz Zeit geben, etwas zu tun
    timer.Join(0.2) 
    
    logger.info("Checking automatic state at %s", time.time())
    check(controller.automatic == DOOR_AUTO_ON, "Door automatic is reenabled.")
    check(timer.last_door_check > 0, "Door check done after reenabling automatic.")

    # jetzt die Lichtschaltzeiten prüfen
    dtnow = datetime.datetime.now()
    for dt, action in controller.actions:
        if action == DOOR_CLOSED:
            if dt >= dtnow:
                # die Aktion liegt in der Zukunft, demnach
                # sollte die Lichtzeit berechnet worden sein
                expected_off_time = dt + datetime.timedelta(seconds = controlserver.SWITCH_LIGHT_OFF_AFTER_CLOSING)
                check(expected_off_time == timer.light_switch_off_time, "Light switch off time calculated correctly.")
                expected_on_time = dt - datetime.timedelta(seconds = controlserver.SWITCH_LIGHT_ON_BEFORE_CLOSING)
                check(expected_on_time == timer.light_switch_on_time, "Light switch on time calculated correctly.")
            else:
                check(timer.light_switch_on_time == None, "Light switch time deactivated.")

    controller.light_on = False
    timer.light_switch_on_time = dtnow + datetime.timedelta(seconds = 10)
    timer.light_switch_off_time = timer.light_switch_on_time + datetime.timedelta(seconds = 10)
    timer.DoLightCheck(dtnow)
    check(controller.light_on == False, "Auto light is off before activation time.")
    timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 11))
    check(controller.light_on == True, "Auto light is on after activation time.")
    timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 21))
    check(controller.light_on == False, "Auto light is off after deactivation time.")

    timer.light_switch_on_time = None
    timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 11))
    check(controller.light_on == False, "Auto light is still off when on time not calculated.")

    controller.automatic = DOOR_AUTO_DEACTIVATED
    timer.light_switch_on_time = dtnow + datetime.timedelta(seconds = 10)
    timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 11))
    check(controller.light_on == False, "Auto light is still off after activation time when not in auto mode.")

    timer.ResetCheckTimes()
    timer.Join(0.1)
    controller.automatic_enable_time = time.time() + 1.0
    logger.info("Disabling automatic (permanently), enable time set to %s", controller.automatic_enable_time)
    timer.ResetCheckTimes()
    timer.Join(0.1)
    check(timer.last_door_check == 0, "Door check skipped when automatic is off (permanently).")

    logger.info("Resetted check times, joining timer for 1.5 seconds.")
    # jetzt müssen wir warten, bis die gesetzte Aktivierungszeit erreicht wurde
    timer.Join(1.5) 
    # danach sorgen wir dafür, dass wieder ein Durchlauf stattfindet
    timer.ResetCheckTimes()
    # und dem Thread nochmal kurz Zeit geben, etwas zu tun
    timer.Join(0.2) 
    
    logger.info("Checking automatic state at %s", time.time())
    check(controller.automatic == DOOR_AUTO_DEACTIVATED, "Door automatic is still disabled.")

    timer.Terminate()
    check(timer.ShouldTerminate(), "Termination flag is set.")
    t = time.time()
    timer.Join(5)
    check(t + 0.1 >= time.time(), "Join recognizes termination.")
    check(not timer.IsRunning(), "Timer is not running after termination.")

    check(len(controller.actions) == 2, "Actions have been calculated.")

    return True
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()
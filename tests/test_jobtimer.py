#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import * # pylint: disable=W0614
import time
import controlserver
# ---------------------------------------------------------------------------------------
class ControllerDummy(object):
    def __init__(self):
        self.door_closed = False
        self.actions = []
        self.automatic = True
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
# ---------------------------------------------------------------------------------------
@testfunction
def test():
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

    controller.automatic = False
    timer.ResetCheckTimes()
    timer.Join(0.1)
    check(timer.last_door_check == 0, "Door check skipped when automatic is off.")

    timer.Terminate()
    check(timer.ShouldTerminate(), "Termination flag is set.")
    timer.Join(0.1)
    check(not timer.IsRunning(), "Timer is not running after termination.")

    check(len(controller.actions) == 2, "Actions have been calculated.")

    return True
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()
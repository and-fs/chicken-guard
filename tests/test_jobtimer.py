#! /usr/bin/python3
# -*- coding: utf8 -*-
# --------------------------------------------------------------------------------------------------
# pylint: disable=E0602
import unittest
import time
import datetime
# --------------------------------------------------------------------------------------------------
from config import *  # pylint: disable=W0614
import base
import controlserver
# --------------------------------------------------------------------------------------------------
logger = base.logger
# --------------------------------------------------------------------------------------------------
class ControllerDummy(object):
    def __init__(self):
        self.door_closed = False
        self.actions = []
        self.automatic = DOOR_AUTO_ON
        self.automatic_enable_time = -1
        self.sensors_read = False
        self.light_on = False
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
    def _CloseDoorFromTimer(self):
        self.CloseDoor()
    def _OpenDoorFromTimer(self):
        self.OpenDoor()
# --------------------------------------------------------------------------------------------------
class Test_JobTimer(base.TestCase):
    def setUp(self):
        super().setUp()
        controlserver.SWITCH_LIGHT_OFF_AFTER_CLOSING = 5  # 5 Sekunden nach Schließen aus
        controlserver.SWITCH_LIGHT_ON_BEFORE_CLOSING = 10 # 10 Sekunden vor Schließen an
        self.controller = ControllerDummy()
        self.timer = controlserver.JobTimer(self.controller)

    def test_Timer(self):
        timer = self.timer
        controller = self.controller

        self.assertFalse(timer.IsRunning(), "Timer doesn't start itself.")
        self.assertFalse(timer.ShouldTerminate(), "Termination flag is initially cleared.")
        timer.Terminate()
        self.assertTrue(timer.ShouldTerminate(), "Termination flag is set.")
        timer.terminate = False # und wieder zurücksetzen

        timer.Start()
        # kurz warten damit der Thread anlaufen kann
        time.sleep(0.2)
        self.assertTrue(timer.IsRunning(), "Timer runs after starting.")
        self.assertFalse(timer.ShouldTerminate(), "Termination flag is still cleared.")

        t = time.time()
        timer.Join(1)
        t = time.time() - t
        self.assertTrue(1.0 <= t < 1.1, "Timer join works in time.")
        self.assertFalse(timer.ShouldTerminate(), "Termination flag is still cleared.")
        self.assertTrue(timer.IsRunning(), "Timer is still running after join.")

        self.assertEqual(len(controller.actions), 2, "Actions have been calculated (1).")
        controller.actions = []
        timer.ResetCheckTimes()
        timer.Join(0.1)
        self.assertTrue(timer.last_door_check != 0, "Door check done when automatic is on.")
        self.assertTrue(timer.last_sunrise_check != 0, "Sunrise check has been done.")
        self.assertEqual(len(controller.actions), 2, "Actions have been calculated (2).")

        controller.automatic = DOOR_AUTO_OFF
        controller.automatic_enable_time = time.time() + 1.0
        logger.info("Disabling automatic, enable time set to %s", controller.automatic_enable_time)
        timer.ResetCheckTimes()
        timer.Join(0.1)
        self.assertEqual(timer.last_door_check, 0, "Door check skipped when automatic is off.")

        logger.info("Resetted check times, joining timer for 1.5 seconds.")
        # jetzt müssen wir warten, bis die gesetzte Aktivierungszeit erreicht wurde
        timer.Join(1.5)
        # danach sorgen wir dafür, dass wieder ein Durchlauf stattfindet
        timer.ResetCheckTimes()
        # und dem Thread nochmal kurz Zeit geben, etwas zu tun
        timer.Join(0.2)


        logger.info("Checking automatic state at %s", time.time())
        self.assertEqual(controller.automatic, DOOR_AUTO_ON, "Door automatic is reenabled.")
        self.assertGreater(timer.last_door_check, 0, "Door check done after reenabling automatic.")

        # jetzt die Lichtschaltzeiten prüfen
        dtnow = datetime.datetime.now()
        for dt, action in controller.actions:
            if action == DOOR_CLOSED:
                if dt >= dtnow:
                    # die Aktion liegt in der Zukunft, demnach
                    # sollte die Lichtzeit berechnet worden sein

                    expected_off_time = dt + datetime.timedelta(
                        seconds = controlserver.SWITCH_LIGHT_OFF_AFTER_CLOSING
                    )

                    self.assertEqual(
                        expected_off_time, timer.light_switch_off_time,
                        "Light switch off time calculated correctly."
                    )

                    expected_on_time = dt - datetime.timedelta(
                        seconds = controlserver.SWITCH_LIGHT_ON_BEFORE_CLOSING
                    )

                    self.assertEqual(
                        expected_on_time, timer.light_switch_on_time,
                        "Light switch on time calculated correctly."
                    )
                else:
                    self.assertEqual(
                        timer.light_switch_on_time, None,
                        "Light switch time deactivated."
                    )

        controller.light_on = False
        timer.light_switch_on_time = dtnow + datetime.timedelta(seconds = 10)
        timer.light_switch_off_time = timer.light_switch_on_time + datetime.timedelta(seconds = 10)
        timer.DoLightCheck(dtnow)
        self.assertFalse(controller.light_on, "Auto light is off before activation time.")
        timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 11))
        self.assertTrue(controller.light_on, "Auto light is on after activation time.")
        timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 21))
        self.assertFalse(controller.light_on, "Auto light is off after deactivation time.")

        timer.light_switch_on_time = None
        timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 11))
        self.assertFalse(
            controller.light_on,
            "Auto light is still off when on time not calculated."
        )

        controller.automatic = DOOR_AUTO_DEACTIVATED
        timer.light_switch_on_time = dtnow + datetime.timedelta(seconds = 10)
        timer.DoLightCheck(dtnow + datetime.timedelta(seconds = 11))
        self.assertFalse(
            controller.light_on,
            "Auto light is still off after activation time when not in auto mode."
        )

        timer.ResetCheckTimes()
        timer.Join(0.1)
        controller.automatic_enable_time = time.time() + 1.0
        logger.info(
            "Disabling automatic (permanently), enable time set to %s",
            controller.automatic_enable_time
        )

        timer.ResetCheckTimes()
        timer.Join(0.1)
        self.assertEqual(
            timer.last_door_check, 0, "Door check skipped when automatic is off (permanently)."
        )

        logger.info("Resetted check times, joining timer for 1.5 seconds.")
        # jetzt müssen wir warten, bis die gesetzte Aktivierungszeit erreicht wurde
        timer.Join(1.5)
        # danach sorgen wir dafür, dass wieder ein Durchlauf stattfindet
        timer.ResetCheckTimes()
        # und dem Thread nochmal kurz Zeit geben, etwas zu tun
        timer.Join(0.2)

        logger.info("Checking automatic state at %s", time.time())

        self.assertEqual(
            controller.automatic, DOOR_AUTO_DEACTIVATED, "Door automatic is still disabled."
        )

        timer.Terminate()
        self.assertTrue(timer.ShouldTerminate(), "Termination flag is set.")
        time.sleep(0.1) # Thread-Wechsel zulassen
        t = time.time()
        timer.Join(5)
        self.assertTrue(t + 0.1 >= time.time(), "Join recognizes termination.")
        self.assertFalse(timer.IsRunning(), "Timer is not running after termination.")

        self.assertEqual(len(controller.actions), 2, "Actions have been calculated.")
# --------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()
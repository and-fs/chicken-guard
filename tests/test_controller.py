#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
# pylint: disable=C0413, C0111, C0103
# ---------------------------------------------------------------------------------------
def _SetupPath():
    import sys
    import pathlib
    root = str(pathlib.Path(__file__).parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
_SetupPath()
# ---------------------------------------------------------------------------------------
import unittest
import base
import controlserver
import board
from shared import Config
from constants import * # pylint: disable=W0614; unused import
from gpio import GPIO
# ---------------------------------------------------------------------------------------
def _DummyFunc(*_args, **_kwargs):
    return True
# ---------------------------------------------------------------------------------------
class Test_TestController(base.TestCase):

    @classmethod
    def setUpClass(cls):
        GPIO.setwarnings(False)
        board.Board.Load = _DummyFunc
        board.Board.Save = _DummyFunc

    def setUp(self):
        super().setUp()
        base.SetInitialGPIOState()
        with GPIO.write_context():
            GPIO.output(REED_LOWER, REED_CLOSED) # Kontakt oben offen
            GPIO.output(REED_UPPER, REED_OPENED) # Kontakt unten geschlossen
        self.controller = controlserver.Controller(start_jobs = False)

    def test_InitialState(self):
        c = self.controller
        self.assertTrue(c.IsDoorClosed(), "Initially door should be closed.")
        self.assertFalse(c.IsDoorOpen(), "Initially door should not be open.")
        self.assertFalse(c.board.IsDoorMoving(), "Initially door state is 'not moving'.")
        self.assertEqual(c.automatic, DOOR_AUTO_ON, "Door automatic is ON.")


    def test_Light(self):
        c = self.controller
        self.assertFalse(c.IsIndoorLightOn(), "Indoor light should be initially off.")
        c.SwitchIndoorLight(False)
        self.assertFalse(c.IsIndoorLightOn(), "Indoor light should be off.")
        c.SwitchIndoorLight(True)
        self.assertTrue(c.IsIndoorLightOn(), "Indoor light should be on.")
        c.SwitchIndoorLight(False)
        self.assertFalse(c.IsIndoorLightOn(), "Indoor light should be off.")

        self.assertFalse(c.IsOutdoorLightOn(), "Outdoor light should be initially off.")
        c.SwitchOutdoorLight(False)
        self.assertFalse(c.IsOutdoorLightOn(), "Outdoor light should be off.")
        c.SwitchOutdoorLight(True)
        self.assertTrue(c.IsOutdoorLightOn(), "Outdoor light should be on.")
        c.SwitchOutdoorLight(False)
        self.assertFalse(c.IsOutdoorLightOn(), "Outdoor light should be off.")

    def OpenDoorTest(self):
        ctrl = self.controller
        ftr = base.Future(ctrl.OpenDoor)
        self.assertTrue(ftr.WaitForExectionStart(0.5), "Door open command is running.")

        with self.assertRaises(TimeoutError):
            ftr.WaitForResult(0.5)

        with GPIO.write_context():
            motor_on = GPIO.input(MOTOR_ON)
            move_dir = GPIO.input(MOVE_DIR)

        self.assertEqual(ctrl.automatic, DOOR_AUTO_OFF, "Door automatic is temporary disabled.")
        self.assertEqual(motor_on, RELAIS_ON, "Motor is running.")
        self.assertEqual(move_dir, MOVE_UP, "Door is moving up.")
        self.assertTrue(ctrl.board.IsDoorMoving(), "Door state is 'moving'.")
        return ftr

    def test_OpenDoorByTime(self):
        ftr = self.OpenDoorTest()

        self.assertTrue(ftr.WaitForResult(), "Door is open.")

        self.assertGreater(
            ftr.GetRuntime(),  Config.Get("DOOR_MOVE_UP_TIME"),
            "Door open duration has been reached.")

        self.assertLess(
            ftr.GetRuntime(),  Config.Get("DOOR_MOVE_UP_TIME") * 1.4,
            "Door open duration is below upper limit.")

    def test_OpenDoorByContact(self):
        #ctrl.board.door_state = DOOR_CLOSED
        #with GPIO.write_context():
        #    GPIO.output(REED_LOWER, REED_CLOSED)
        ftr = self.OpenDoorTest()

        with GPIO.write_context():
            GPIO.output(REED_LOWER, REED_OPENED) # Kontakt unten offen
            GPIO.output(REED_UPPER, REED_CLOSED) # Kontakt oben geschlossen

        self.assertTrue(ftr.WaitForResult(), "Door is open.")

        self.assertLess(
            ftr.GetRuntime(),  Config.Get("DOOR_MOVE_UP_TIME"),
            "Door open duration has not been reached due to contact.")

    def CloseDoorTest(self):
        ctrl = self.controller
        ctrl.board.door_state = DOOR_OPEN
        with GPIO.write_context():
            GPIO.output(REED_UPPER, REED_CLOSED) # Kontakt oben geschlossen
            GPIO.output(REED_LOWER, REED_OPENED) # Kontakt unten offen

        ftr = base.Future(ctrl.CloseDoor)
        self.assertTrue(ftr.WaitForExectionStart(0.5), "Door close command is running.")

        with self.assertRaises(TimeoutError):
            ftr.WaitForResult(2)

        with GPIO.write_context():
            motor_on = GPIO.input(MOTOR_ON)
            move_dir = GPIO.input(MOVE_DIR)

        self.assertEqual(ctrl.automatic, DOOR_AUTO_OFF, "Door automatic is temporary disabled.")
        self.assertEqual(motor_on, RELAIS_ON, "Motor is running.")
        self.assertEqual(move_dir, MOVE_DOWN, "Door is moving down.")
        self.assertTrue(ctrl.board.IsDoorMoving(), "Door state is 'moving'.")
        return ftr

    def test_CloseDoorByTime(self):
        ftr = self.CloseDoorTest()
        self.assertTrue(ftr.WaitForResult(), "Door is closed.")

        self.assertGreater(
            ftr.GetRuntime(),  Config.Get("DOOR_MOVE_DOWN_TIME"),
            "Door close duration has been reached.")

        self.assertLess(
            ftr.GetRuntime(),  Config.Get("DOOR_MOVE_DOWN_TIME") * 1.5,
            "Door close duration is below upper limit.")

    def test_CloseDoorByContact(self):
        ftr = self.CloseDoorTest()
        with GPIO.write_context():
            GPIO.output(REED_LOWER, REED_CLOSED) # Kontakt oben offen
            GPIO.output(REED_UPPER, REED_OPENED) # Kontakt unten geschlossen

        self.assertTrue(ftr.WaitForResult(), "Door is closed.")

        self.assertLess(
            ftr.GetRuntime(),  Config.Get("DOOR_MOVE_UP_TIME"),
            "Door close duration has not been reached due to contact.")
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()
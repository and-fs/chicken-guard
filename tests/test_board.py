#! /usr/bin/python3
# -*- coding: utf8 -*-
# --------------------------------------------------------------------------------------------------
# pylint: disable=C0413, C0111, C0103
# --------------------------------------------------------------------------------------------------
def _SetupPath():
    import sys
    import pathlib
    root = str(pathlib.Path(__file__).parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
_SetupPath()
# --------------------------------------------------------------------------------------------------
import unittest
import base
import board
from config import * # pylint: disable=W0614; unused import
from gpio import GPIO
# --------------------------------------------------------------------------------------------------
filestate = dict(saved = False, loaded = False)
logger = base.logger
# --------------------------------------------------------------------------------------------------
def _DummyLoad(*_args, **_kwargs):
    filestate['loaded'] = True
    return True
# --------------------------------------------------------------------------------------------------
def _DummySave(*_args, **_kwargs):
    filestate['saved'] = True
    return True
# --------------------------------------------------------------------------------------------------
def _GetSaveState():
    res = filestate['saved']
    filestate['saved'] = False
    return res
# --------------------------------------------------------------------------------------------------
class Test_TestBoard(base.TestCase):

    @classmethod
    def setUpClass(cls):
        GPIO.setwarnings(False)
        board.Board.Load = _DummyLoad
        board.Board.Save = _DummySave

    def setUp(self):
        base.SetInitialGPIOState()
        filestate.update(saved = False, loaded = False)
        self.board = board.Board()

    def test_InitialState(self):
        self.assertTrue(filestate['loaded'], "Initial board state has been loaded.")
        self.assertTrue(self.board.IsDoorClosed(), "Initially door should be closed.")
        self.assertFalse(self.board.IsDoorOpen(), "Initially door should not be open.")

    def test_DoorOpen(self):
        ftr = base.Future(self.board.OpenDoor)
        self.assertTrue(ftr.WaitForExectionStart(1.0), "Future starts within time.")
        self.assertFalse(
            self.board.OpenDoor(),
            "Calling OpenDoor() while door is moving should not be possible!"
        )
        self.assertFalse(ftr.HasResult(), "OpenDoor() is running.")

        with GPIO.write_context():
            GPIO.output(REED_LOWER, REED_OPENED) # unten kein Signal mehr

        self.assertFalse(
            self.board.IsDoorClosed(),
            "Door should not be closed when lower reed is HIGH"
        )

        with GPIO.write_context():
            GPIO.output(REED_UPPER, REED_CLOSED) # oben auf LOW

        ftr.WaitForResult(0.5 + UPPER_REED_OFFSET)

        self.assertTrue(ftr.HasResult(), "OpenDoor() is finished.")
        self.assertTrue(_GetSaveState(), "Board state has been saved.")
        self.assertTrue(self.board.IsDoorOpen(), "Door should be opened when upper reed is LOW")
        self.assertFalse(
            self.board.IsDoorClosed(),
            "Door should not be closed when lower reed is HIGH"
        )

        self.assertTrue(ftr.WaitForResult(), "OpenDoor() succeeded.")
        self.assertFalse(
            self.board.OpenDoor(),
            "Calling OpenDoor() while door is opened shouldn't be possible"
        )
        self.assertFalse(_GetSaveState(), "Board state not saved when operation fails.")

    def test_DoorClose(self):
        # Tür auf "Offen" setzen:
        self.board.door_state = DOOR_OPEN
        with GPIO.write_context():
            GPIO.output(REED_UPPER, REED_CLOSED)
            GPIO.output(REED_LOWER, REED_OPENED)

        ftr = base.Future(self.board.CloseDoor)
        self.assertTrue(ftr.WaitForExectionStart(1.0), "Future starts within time.")

        self.assertFalse(
            ftr.HasResult(),
            "Calling CloseDoor() when door is open should be possible"
        )

        self.assertFalse(
            self.board.CloseDoor(),
            "Calling CloseDoor() while door is moving should not be possible"
        )

        with GPIO.write_context():
            GPIO.output(REED_UPPER, REED_OPENED) # oben kein Signal mehr

        self.assertFalse(
            self.board.IsDoorOpen(),
            "Door should not be opened when upper reed is HIGH"
        )

        with GPIO.write_context():
            GPIO.output(REED_LOWER, REED_CLOSED) # unten auf LOW

        ftr.WaitForResult(0.5 + LOWER_REED_OFFSET) # anderen Thread ranlassen

        self.assertTrue(ftr.HasResult(), "CloseDoor() is finished.")

        self.assertTrue(_GetSaveState(), "Board state has been saved.")
        self.assertTrue(self.board.IsDoorClosed(), "Door should be closed when lower reed is LOW")
        self.assertFalse(self.board.IsDoorOpen(), "Door should not be open when upper reed is HIGH")
        self.assertTrue(ftr.WaitForResult(), "CloseDoor() succeeded.")

        self.assertFalse(
            self.board.CloseDoor(),
            "Calling CloseDoor() while door is open shouldn't be possible."
        )
        self.assertFalse(_GetSaveState(), "Board state not saved when operation fails.")

    def test_IndoorLight(self):
        # --- Innenbeleuchtung ---
        self.assertFalse(self.board.IsIndoorLightOn(), "Indoor light should be initially off.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_INDOOR), RELAIS_OFF, "Indoor light pin is not off.")
        self.board.SwitchIndoorLight(False)
        self.assertFalse(self.board.IsIndoorLightOn(), "Indoor light should be off.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_INDOOR), RELAIS_OFF, "Indoor light pin is not off.")
        self.board.SwitchIndoorLight(True)
        self.assertTrue(self.board.IsIndoorLightOn(), "Indoor light should be on.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_INDOOR), RELAIS_ON, "Indoor light pin is not on.")
        self.board.SwitchIndoorLight(False)
        self.assertFalse(self.board.IsIndoorLightOn(), "Indoor light should be off.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_INDOOR), RELAIS_OFF, "Indoor light pin is not off.")

    def test_OutdoorLight(self):
        # --- Aussenbeleuchtung ---
        self.assertFalse(self.board.IsOutdoorLightOn(), "Outdoor light should be initially off.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_OUTDOOR), RELAIS_OFF, "Outdoor light pin is not off.")
        self.board.SwitchOutdoorLight(False)
        self.assertFalse(self.board.IsOutdoorLightOn(), "Outdoor light should be off.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_OUTDOOR), RELAIS_OFF, "Outdoor light pin is not off.")
        self.board.SwitchOutdoorLight(True)
        self.assertTrue(self.board.IsOutdoorLightOn(), "Outdoor light should be on.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_OUTDOOR), RELAIS_ON, "Outdoor light pin is not on.")
        self.board.SwitchOutdoorLight(False)
        self.assertFalse(self.board.IsOutdoorLightOn(), "Outdoor light should be off.")
        with GPIO.write_context():
            self.assertEqual(GPIO.input(LIGHT_OUTDOOR), RELAIS_OFF, "Outdoor light pin is not off.")
# --------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main()

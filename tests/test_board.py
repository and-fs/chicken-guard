#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import *
import time
import board, shared
from gpio import GPIO
from config import * # pylint: disable=W0614
# ---------------------------------------------------------------------------------------
filestate = dict(saved = False, loaded = False)
# ---------------------------------------------------------------------------------------
def _DummyLoad(*args, **kwargs):
    filestate['loaded'] = True
    return True
# ---------------------------------------------------------------------------------------
def _DummySave(*args, **kwargs):
    filestate['saved'] = True
    return True
# ---------------------------------------------------------------------------------------
def _GetSaveState():
    res = filestate['saved']
    filestate['saved'] = False
    return res
# ---------------------------------------------------------------------------------------
@testfunction
def test():
    if not __debug__:
        raise RuntimeError("Tests have to be executed in DEBUG mode.")

    GPIO.setwarnings(False)
    SetInitialGPIOState()
    board.Board.Load = _DummyLoad
    board.Board.Save = _DummySave
    filestate.update(saved = False, loaded = False)
    b = board.Board()
    check(filestate['loaded'] == True, "Initial board state has been loaded.")
    check(b.IsDoorClosed(), "Initially door should be closed.")
    check(not b.IsDoorOpen(), "Initially door should not be open.")

    # --- Tür öffnen ---

    f = Future(b.OpenDoor)
    f.WaitForExectionStart(1.0)

    res = b.OpenDoor()
    check(not res, "Calling OpenDoor() while door is moving should not be possible!")

    check(not f.HasResult(), "OpenDoor() is running.")

    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_OPENED) # unten kein Signal mehr

    check(not b.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")

    with GPIO.write_context():
        GPIO.output(REED_UPPER, REED_CLOSED) # oben auf LOW

    time.sleep(0.5 + UPPER_REED_OFFSET)
    check(f.HasResult(), "OpenDoor() is finished.")

    check(_GetSaveState(), "Board state has been saved.")
    check(b.IsDoorOpen(), "Door should be opened when upper reed is LOW")
    check(not b.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")
    res = f.WaitForResult()
    check(res, "OpenDoor() succeeded (%r).", res)

    res = b.OpenDoor()
    check(not res, "Calling OpenDoor() while door is opened shouldn't be possible")
    check(not _GetSaveState(), "Board state not saved when operation fails.")


    # --- Tür schließen ---

    f = Future(b.CloseDoor)
    f.WaitForExectionStart(1.0)
    check(not f.HasResult(), "Calling CloseDoor() when door is open should be possible")
    
    res = b.CloseDoor()
    check(not res, "Calling CloseDoor() while door is moving should not be possible")

    with GPIO.write_context():
        GPIO.output(REED_UPPER, REED_OPENED) # oben kein Signal mehr
    check(not b.IsDoorOpen(), "Door should not be opened when upper reed is HIGH")

    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_CLOSED) # unten auf LOW

    time.sleep(1.0) # anderen Thread ranlassen
    check(f.HasResult(), "CloseDoor() is finished.")

    check(_GetSaveState(), "Board state has been saved.")
    check(b.IsDoorClosed(), "Door should be closed when lower reed is LOW")
    check(not b.IsDoorOpen(), "Door should not be open when upper reed is HIGH")
    check(f.WaitForResult(), "CloseDoor() succeeded.")

    res = b.CloseDoor()
    check(not res, "Calling CloseDoor() while door is open shouldn't be possible.")
    check(not _GetSaveState(), "Board state not saved when operation fails.")    

    # --- Innenbeleuchtung ---
    check(not b.IsIndoorLightOn(), "Indoor light should be initially off.")
    b.SwitchIndoorLight(False)
    check(not b.IsIndoorLightOn(), "Indoor light should be off.")
    b.SwitchIndoorLight(True)
    check(b.IsIndoorLightOn(), "Indoor light should be on.")
    b.SwitchIndoorLight(False)
    check(not b.IsIndoorLightOn(), "Indoor light should be off.")

    # --- Aussenbeleuchtung ---
    check(not b.IsOutdoorLightOn(), "Outdoor light should be initially off.")
    b.SwitchOutdoorLight(False)
    check(not b.IsOutdoorLightOn(), "Outdoor light should be off.")
    b.SwitchOutdoorLight(True)
    check(b.IsOutdoorLightOn(), "Outdoor light should be on.")
    b.SwitchOutdoorLight(False)
    check(not b.IsOutdoorLightOn(), "Outdoor light should be off.")
    return True
# ---------------------------------------------------------------------------------------------
if __name__ == "__main__":
    test()

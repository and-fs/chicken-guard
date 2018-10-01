#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import *
import time
import board, shared
from gpio import GPIO
from config import * # pylint: disable=W0614
# ---------------------------------------------------------------------------------------
@testfunction
def test():
    if not __debug__:
        raise RuntimeError("Tests have to be executed in DEBUG mode.")

    GPIO.setwarnings(False)
    SetInitialGPIOState()
    b = board.Board()

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

    time.sleep(0.5)
    check(f.HasResult(), "OpenDoor() is finished.")

    check(b.IsDoorOpen(), "Door should be opened when upper reed is LOW")
    check(not b.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")
    check(f.WaitForResult(), "OpenDoor() succeeded.")

    res = b.OpenDoor()
    check(not res, "Calling OpenDoor() while door is opened shouldn't be possible")

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

    time.sleep(0.5) # anderen Thread ranlassen
    check(f.HasResult(), "CloseDoor() is finished.")


    check(b.IsDoorClosed(), "Door should be closed when lower reed is LOW")
    check(not b.IsDoorOpen(), "Door should not be open when upper reed is HIGH")
    check(f.WaitForResult(), "CloseDoor() succeeded.")

    res = b.CloseDoor()
    check(not res, "Calling CloseDoor() while door is open shouldn't be possible.")

    # Tür timeouts

    f = Future(b.OpenDoor)
    start_t = time.time()
    f.WaitForExectionStart(1.0)
    check(not f.HasResult(), "OpenDoor() is running.")

    timeout_check = True
    try:
        res = f.WaitForResult(MAX_DOOR_MOVE_DURATION)
    except TimeoutError:
        timeout_check = False
    check(timeout_check, "Door command returns when reaching timeout.")
    check(not res, "Door command result is False when reaching timeout.")

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

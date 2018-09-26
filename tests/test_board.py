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

    cbres = []
    def cb(reed_closed):
        cbres.append(reed_closed)

    # --- Tür öffnen ---

    res = b.OpenDoor(callback = cb)
    check(res == 1, "Calling OpenDoor() when door is closed should be possible!")
    
    res = b.OpenDoor()
    check(res < 0, "Calling OpenDoor() while door is moving should not be possible!")

    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_OPENED) # unten kein Signal mehr
    check(not b.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")

    with GPIO.write_context():
        GPIO.output(REED_UPPER, REED_CLOSED) # oben auf LOW
    time.sleep(0.5) # anderen Thread ranlassen

    check(b.IsDoorOpen(), "Door should be opened when upper reed is LOW")
    check(not b.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")
    check(cbres and (cbres[-1] == True), "Callback for open door has not be called.")

    res = b.OpenDoor()
    check(res < 0, "Calling OpenDoor() while door is opened shouldn't be possible")

    # --- Tür schließen ---

    cbres.clear()
    res = b.CloseDoor(callback = cb)
    check(res == 1, "Calling CloseDoor() when door is open should be possible")
    
    res = b.CloseDoor()
    check(res < 0, "Calling CloseDoor() while door is moving should not be possible")

    with GPIO.write_context():
        GPIO.output(REED_UPPER, REED_OPENED) # oben kein Signal mehr
    check(not b.IsDoorOpen(), "Door should not be opened when upper reed is HIGH")

    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_CLOSED) # unten auf LOW
    time.sleep(0.2) # anderen Thread ranlassen

    check(b.IsDoorClosed(), "Door should be closed when lower reed is LOW")
    check(not b.IsDoorOpen(), "Door should not be open when upper reed is HIGH")
    check(cbres and (cbres[-1] == True), "Callback for close door has not be called.")

    res = b.CloseDoor()
    check(res < 0, "Calling CloseDoor() while door is open shouldn't be possible.")

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

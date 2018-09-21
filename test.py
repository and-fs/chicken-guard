#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
import time
import board
import shared
from config import * # pylint: disable=W0614
from gpio import GPIO
# ---------------------------------------------------------------------------------------
def test_SetInitialGPIOState():
    """
    Nur für Tests: setzt den initialen GPIO-Status
    """
    if not hasattr(GPIO, 'allow_write'):
        raise RuntimeError("Need GPIO dummy for setting initial board state!")

    with GPIO.write_context():
        GPIO.setmode(GPIO.BOARD)
        GPIO.output(REED_UPPER, 1)
        GPIO.output(REED_LOWER, 0) # Tür geschlossen
        GPIO.output(SHUTDOWN_BUTTON, 1)
# ---------------------------------------------------------------------------------------
def check(condition, message, *args):
    if condition:
        print ('[OK] ' + (message % args))
    else:
        print ('[FAIL] ' + (message % args))
        raise RuntimeError(message % args)
# ---------------------------------------------------------------------------------------
def test_board():
    if not __debug__:
        raise RuntimeError("Tests have to be executed in DEBUG mode.")

    shared.configureLogging("test")
    print ("Running Test...")
    GPIO.setwarnings(False)
    test_SetInitialGPIOState()
    b = board.Board()

    check(b.IsDoorClosed(), "Initially door should be closed.")
    check(not b.IsDoorOpen(), "Initially door should not be open.")

    cbres = []
    def cb():
        cbres.append(True)

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
    time.sleep(0.2) # anderen Thread ranlassen

    check(b.IsDoorOpen(), "Door should be opened when upper reed is LOW")
    check(not b.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")
    check(cbres[-1] == True, "Callback for open door has not be called.")

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
    check(cbres[-1] == True, "Callback for close door has not be called.")

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

    print ("Finished.")
    return b

def test_async_call():
    pass

def test_all():
    test_board()
    test_async_call()

if __name__ == "__main__":
    test_all()

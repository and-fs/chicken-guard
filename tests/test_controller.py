#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import * # pylint: disable=W0614
import controlserver
# ---------------------------------------------------------------------------------------
@testfunction
def test():
    GPIO.setwarnings(False)
    SetInitialGPIOState()
    c = controlserver.Controller()

    check(c.IsDoorClosed(), "Initially door should be closed.")
    check(not c.IsDoorOpen(), "Initially door should not be open.")

    # --- Tür öffnen ---
    res = c.OpenDoor()
    check(res == False, "Expected door opener to run into timeout!")

    f = Future(c.OpenDoor)
    # da die Rückmeldung nur dann positiv erfolgt, wenn der Türkontakt auch geschlossen
    # wurde, müssen wir das jetzt hier tun.
    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_OPENED) # unteres Reed offen
        GPIO.output(REED_UPPER, REED_CLOSED) # oberes Reed geschlossen

    res = f.WaitForResult(waittime = 5.0)    
    check(res == True, "Calling OpenDoor() did not return expected result!")
    
    res = c.OpenDoor()
    check(res < 0, "Calling OpenDoor() while door is moving should not be possible!")

    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_OPENED) # unten kein Signal mehr
    check(not c.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")

    with GPIO.write_context():
        GPIO.output(REED_UPPER, REED_CLOSED) # oben auf LOW

    check(c.IsDoorOpen(), "Door should be opened when upper reed is LOW")
    check(not c.IsDoorClosed(), "Door should not be closed when lower reed is HIGH")

    res = c.OpenDoor()
    check(res < 0, "Calling OpenDoor() while door is opened shouldn't be possible")

    # --- Tür schließen ---

    cbres.clear()
    res = c.CloseDoor()
    check(res == 1, "Calling CloseDoor() when door is open should be possible")
    
    res = c.CloseDoor()
    check(res < 0, "Calling CloseDoor() while door is moving should not be possible")

    with GPIO.write_context():
        GPIO.output(REED_UPPER, REED_OPENED) # oben kein Signal mehr
    check(not c.IsDoorOpen(), "Door should not be opened when upper reed is HIGH")

    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_CLOSED) # unten auf LOW

    check(c.IsDoorClosed(), "Door should be closed when lower reed is LOW")
    check(not c.IsDoorOpen(), "Door should not be open when upper reed is HIGH")

    res = c.CloseDoor()
    check(res < 0, "Calling CloseDoor() while door is open shouldn't be possible.")

    # --- Innenbeleuchtung ---
    check(not c.IsIndoorLightOn(), "Indoor light should be initially off.")
    b.SwitchIndoorLight(False)
    check(not c.IsIndoorLightOn(), "Indoor light should be off.")
    b.SwitchIndoorLight(True)
    check(c.IsIndoorLightOn(), "Indoor light should be on.")
    b.SwitchIndoorLight(False)
    check(not c.IsIndoorLightOn(), "Indoor light should be off.")

    # --- Aussenbeleuchtung ---
    check(not c.IsOutdoorLightOn(), "Outdoor light should be initially off.")
    b.SwitchOutdoorLight(False)
    check(not c.IsOutdoorLightOn(), "Outdoor light should be off.")
    b.SwitchOutdoorLight(True)
    check(c.IsOutdoorLightOn(), "Outdoor light should be on.")
    b.SwitchOutdoorLight(False)
    check(not c.IsOutdoorLightOn(), "Outdoor light should be off.")
    print ("Finished.")
    return True
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()
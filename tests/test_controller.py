#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
from base import * # pylint: disable=W0614
import controlserver
import time
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
    check(res == False, "Expected door opener to run into timeout.")
    # Jetzt müssen wir die Bewegung "stoppen", da sonst der nächste
    # Schritt fehlschlägt
    c.StopDoor()
    with GPIO.write_context():
        motor_on = GPIO.input(MOTOR_ON)
        move_dir = GPIO.input(MOVE_DIR)
    check(motor_on == RELAIS_OFF, "Motor relais is off after stop.")
    check(move_dir == MOVE_UP, "Moving direction is resetted after stop.")
    check(c.board.IsDoorMoving() == False, "Door state is 'not moving' after stop.")

    f = Future(c.OpenDoor)
    # wir müssen kurz warten, bis der Thread läuft, damit
    # c.OpenDoor mitbekommt, wenn die Reeds sich ändern
    check(f.WaitForExectionStart(1), "Future starts within time.")

    # da die Rückmeldung nur dann positiv erfolgt, wenn der Türkontakt auch geschlossen
    # wurde, müssen wir das jetzt hier tun.
    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_OPENED) # unteres Reed offen
        GPIO.output(REED_UPPER, REED_CLOSED) # oberes Reed geschlossen

    res = f.WaitForResult(waittime = 5.0)
    check(res == True, "Calling OpenDoor() returns %r.", res)
    
    check(c.IsDoorOpen(), "Door is open.")
    check(not c.IsDoorClosed(), "Door is not closed.")

    res = c.OpenDoor()
    check(res == False, "Calling OpenDoor() while door is opened shouldn't be possible")

    # --- Tür schließen ---
    res = c.CloseDoor()
    check(res, "Door closed.")

    # Auch hier müssen wir die Bewegung "stoppen", da sonst der nächste
    # Schritt fehlschlägt
    c.StopDoor()
    with GPIO.write_context():
        motor_on = GPIO.input(MOTOR_ON)
        move_dir = GPIO.input(MOVE_DIR)
    check(motor_on == RELAIS_OFF, "Motor relais is off after stop.")
    check(move_dir == MOVE_UP, "Moving direction is resetted after stop.")
    check(c.board.IsDoorMoving() == False, "Door state is 'not moving' after stop.")

    f = Future(c.CloseDoor)
    check(f.WaitForExectionStart(1), "Future starts within time.")
    # da die Rückmeldung nur dann positiv erfolgt, wenn der Türkontakt auch geschlossen
    # wurde, müssen wir das jetzt hier tun.
    with GPIO.write_context():
        GPIO.output(REED_LOWER, REED_CLOSED) # unteres Reed geschlossen
        GPIO.output(REED_UPPER, REED_OPENED) # oberes Reed offen

    res = f.WaitForResult(waittime = 5.0)
    check(res == True, "Calling CloseDoor() returns %r.", res)
    
    check(not c.IsDoorOpen(), "Door is not open.")
    check(c.IsDoorClosed(), "Door is closed.")

    res = c.CloseDoor()
    check(res == False, "Calling CloseDoor() while door is closed shouldn't be possible.")

    # --- Innenbeleuchtung ---
    check(not c.IsIndoorLightOn(), "Indoor light should be initially off.")
    c.SwitchIndoorLight(False)
    check(not c.IsIndoorLightOn(), "Indoor light should be off.")
    c.SwitchIndoorLight(True)
    check(c.IsIndoorLightOn(), "Indoor light should be on.")
    c.SwitchIndoorLight(False)
    check(not c.IsIndoorLightOn(), "Indoor light should be off.")

    # --- Aussenbeleuchtung ---
    check(not c.IsOutdoorLightOn(), "Outdoor light should be initially off.")
    c.SwitchOutdoorLight(False)
    check(not c.IsOutdoorLightOn(), "Outdoor light should be off.")
    c.SwitchOutdoorLight(True)
    check(c.IsOutdoorLightOn(), "Outdoor light should be on.")
    c.SwitchOutdoorLight(False)
    check(not c.IsOutdoorLightOn(), "Outdoor light should be off.")
    return True
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()
#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Test-Basis-Modul, immer als erstes importieren!
"""
# ---------------------------------------------------------------------------------------
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
# ---------------------------------------------------------------------------------------
from config import *
CATCH_TEST_ERRORS = True
# ---------------------------------------------------------------------------------------
import shared
shared.configureLogging("test")
from gpio import GPIO
# ---------------------------------------------------------------------------------------
class TestError(Exception):
    def __init__(self, message, *args):
        Exception.__init__(self, message % args)
# ---------------------------------------------------------------------------------------
def testfunction(fu):
    """
    Dekorator für Testfunktionen.

    Wenn CATCH_TEST_ERRORS mit Wahr evaluiert, werden Exceptions
    von diesem Typ abgefangen und nur als Fail ausgegeben, der Test
    ist dann aber trotzdem beendet.

    Alle anderen Exceptions werden nicht behandelt.
    Im Falle einer abgefangen TestError-Exception ist der Rückgabewert
    der dekorierten Funktion immer `False`.
    """
    def call(*args, **kwargs):
        print ("-" * 80)
        print ("Starting test.")
        try:
            result = fu(*args, **kwargs)
        except TestError as e:
            result = False
            print ("Test failed:", e)
            if not CATCH_TEST_ERRORS:
                raise
        else:
            print ("Test succeeded.")
        return result
    return call
# ---------------------------------------------------------------------------------------
def check(condition, message, *args):
    """
    Prüft die Bedingung `condition` auf `True`.
    Wenn erfüllt, wird die Nachricht mit dem Prefix `OK` ausgegeben,
    sonst `Fail`. In letzterem Fall wird ein TestError ausgelöst.

    Args:
        condition: Bedingung zur Erfüllung des Tests, wird als Bool evaluiert.
        message: Nachricht zum Testschritt (was wurde erwartet).
            Wird mit `args` substituiert, falls angegeben.
    """
    if condition:
        print ('[OK] ' + (message % args))
    else:
        print ('[FAIL] ' + (message % args))
        raise TestError(message, *args)
# ---------------------------------------------------------------------------------------
def SetInitialGPIOState():
    """
    Setzt den initialen GPIO-Status
    """
    if not hasattr(GPIO, 'allow_write'):
        raise RuntimeError("Need GPIO dummy for setting initial board state!")

    with GPIO.write_context():
        GPIO.setmode(GPIO.BOARD)
        GPIO.output(REED_UPPER, 1)
        GPIO.output(REED_LOWER, 0) # Tür geschlossen
        GPIO.output(SHUTDOWN_BUTTON, 1)
# ---------------------------------------------------------------------------------------
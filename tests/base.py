#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Test-Basis-Modul, immer als erstes importieren!
"""
# ---------------------------------------------------------------------------------------
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import threading
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
    Setzt den initialen GPIO-Status für die Tests.
    """
    if not hasattr(GPIO, 'allow_write'):
        raise RuntimeError("Need GPIO dummy for setting initial board state!")

    with GPIO.write_context():
        GPIO.setmode(GPIO.BOARD)
        GPIO.output(REED_UPPER, REED_OPENED)
        GPIO.output(REED_LOWER, REED_CLOSED) # Tür geschlossen
        GPIO.output(SHUTDOWN_BUTTON, 1)
# ---------------------------------------------------------------------------------------
class Future(object):
    """
    Future-Implementierung für die Tests.
    Führt eine Funktion nebenläufig aus, das Ergebnis kann
    dann zu einem späteren Zeitpunkt abgefragt werden.

    Beispiel: ```python
        import time
        def time_consuming_pow2(a):
            time.sleep(2.0)
            return "%d * %d is %d" % (a, a, a * a)

        f = Future(time_consuming_pow2, 10)
        print (f.HasResult()) # False
        time.sleep(1.0)
        print (f.HasResult()) # False
        print (f.WaitForResult(2.0)) # "10 * 10 is 100"
    ```
    """
    def __init__(self, function, *args, **kwargs):
        """
        Initializes the future with a reference to
        the callable `function` which will be executed
        in parallel.
        Both `args` and `kwargs` will be passed to
        the `function` on execution.
        """
        assert callable(function), "function has to be a callable!"
        self.function = function
        self.condition = threading.Condition()
        self.start_cond = threading.Condition()
        self.started = False
        self.thread = threading.Thread(target = self._Execute, args = args, kwargs = kwargs)
        self.thread.start()

    def _Execute(self, *args, **kwargs):
        with self.start_cond:
            self.started = True
            self.start_cond.notify_all()
        try:
            result = self.function(*args, **kwargs)
        except Exception as e:
            result = e
        with self.condition:
            self.result = result
            self.condition.notify_all()

    def WaitForExectionStart(self, waittime: float = None) -> bool:
        """
        Waits for the execution thread to start.

        Returns as soon as the execution of the contained
        function has been started or the waittime (in seconds or
        fractions thereof) has been reached.

        Returns:
            If the execution thread has been started within
            given time.
        """
        with self.start_cond:
            self.start_cond.wait(waittime)
            return self.started

    def HasResult(self) -> bool:
        """
        Returns if the result of the contained function is
        available.
        """
        with self.condition:
            return hasattr(self, 'result')

    def WaitForResult(self, waittime = None):
        """
        Waits `waittime` seconds (or fractions thereof)
        for the contained function to be executed and
        returns it's result.

        If waittime has been reached without getting
        a result, a TimeoutError is raised.
        """
        with self.condition:
            if hasattr(self, 'result'):
                return self.result
            self.condition.wait(waittime)
            if hasattr(self, 'result'):
                return self.result
            raise TimeoutError
# ---------------------------------------------------------------------------------------
#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Test-Basis-Modul, immer als erstes importieren!
"""
# --------------------------------------------------------------------------------------------------
import sys
import time
import pathlib
import threading
import unittest
import warnings
# --------------------------------------------------------------------------------------------------
warnings.filterwarnings('ignore', r'.*using a (GPIO|SMBUS) mockup.*')
# --------------------------------------------------------------------------------------------------
if str(pathlib.Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
# --------------------------------------------------------------------------------------------------
from config import * # pylint: disable=W0614,W0401
import shared
from gpio import GPIO
# --------------------------------------------------------------------------------------------------
logger = shared.getLogger("test")
# --------------------------------------------------------------------------------------------------
class TestCase(unittest.TestCase):
    def setUp(self):
        logger.info("*** %r is starting.", self._testMethodName)

    def tearDown(self):
        logger.info("*** %r has finished.", self._testMethodName)

    def assertTrue(self, expr, msg = None):
        if msg:
            logger.info(msg)
        return super().assertTrue(expr, msg = msg)

    def assertFalse(self, expr, msg = None):
        if msg:
            logger.info(msg)
        return super().assertFalse(expr, msg = msg)

    def assertEqual(self, first, second, msg = None):
        if msg:
            logger.info(msg)
        return super().assertEqual(first, second, msg = msg)

    def assertLess(self, a, b, msg = None):
        if msg:
            logger.info(msg)
        return super().assertLess(a, b, msg = msg)

    def assertGreater(self, a, b, msg = None):
        if msg:
            logger.info(msg)
        return super().assertGreater(a, b, msg = msg)

    def assertNotIn(self, member, container, msg = None):
        if msg:
            logger.info(msg)
        return super().assertNotIn(member, container, msg = msg)

    def assertIn(self, member, container, msg = None):
        if msg:
            logger.info(msg)
        return super().assertIn(member, container, msg = msg)
# --------------------------------------------------------------------------------------------------
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
# --------------------------------------------------------------------------------------------------
class Future:
    """
    Future-Implementierung für die Tests.
    Führt eine Funktion nebenläufig aus, das Ergebnis kann
    dann zu einem späteren Zeitpunkt abgefragt werden.

    Beispiel:

    .. code-block:: python

        import time
        def time_consuming_pow2(a):
            time.sleep(2.0)
            return "%d * %d is %d" % (a, a, a * a)

        f = Future(time_consuming_pow2, 10)
        print (f.HasResult()) # False
        time.sleep(1.0)
        print (f.HasResult()) # False
        print (f.WaitForResult(2.0)) # "10 * 10 is 100"

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
        self.start_time = None
        self.end_time = None
        self.thread = threading.Thread(target = self._Execute, args = args, kwargs = kwargs)
        self.thread.start()

    def _Execute(self, *args, **kwargs):
        with self.start_cond:
            self.started = True
            self.start_cond.notify_all()
        self.start_time = time.time()
        try:
            result = self.function(*args, **kwargs)
        except Exception as e: # pylint: disable=W0703
            result = e
        self.end_time = time.time()
        with self.condition:
            self.result = result # pylint: disable=W0201
            self.condition.notify_all()

    def GetRuntime(self):
        """
        Gibt die Laufzeit der gekapselten Funkton zurück.
        Sollte diese nicht gestartet oder noch nicht beendet sein,
        ist der Rückgabewert ``None``.
        """
        if not ((self.start_time is None) or (self.end_time is None)):
            return self.end_time - self.start_time
        return None

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

    def Join(self, waittime = None):
        """
        Wartet die angegebene Zeit (Sekunden) am Thread.
        """
        with self.condition:
            self.condition.wait(waittime)
# ---------------------------------------------------------------------------------------

#! /usr/bin/python3
# -*- coding: utf8 -*-
# --------------------------------------------------------------------------------------------------
# pylint: disable=C0413, C0111, C0103, W0212
import os
import subprocess
import unittest
from tests import base
from config import * # pylint: disable=W0614; unused import
import watchdog
# --------------------------------------------------------------------------------------------------
class popenDummy():

    SIGNAL_RAISE = 0
    SIGNAL_TERM = 1
    SIGNAL_IGNORE = 2

    EXITCODE_SIGNAL = 1
    EXITCODE_KILL = 2
    EXITCODE_FINISHED = 3

    PID = 1

    def __init__(self, mod, name):
        self._mod = mod
        self._name = name.rsplit(os.path.sep, 1)[-1]
        self._exitcode = None
        self._send_signal = self.SIGNAL_TERM
        popenDummy.PID += 1
        self.pid = popenDummy.PID
        self._mod._add_process(self)

    def _set_exitcode(self, code):
        self._exitcode = code
        self._mod._remove_process(self)

    def kill(self):
        self._exitcode = self.EXITCODE_KILL

    def poll(self):
        return self._exitcode

    def send_signal(self, signal_code):
        if self._send_signal == self.SIGNAL_RAISE:
            raise ValueError("Not supported signal %d!" % (signal_code,))
        elif self._send_signal == self.SIGNAL_TERM:
            self._exitcode = self.EXITCODE_SIGNAL
        else:
            pass # ansonsten gar nichts tun

    def __str__(self):
        return self._name

    __repr__ = __str__
# --------------------------------------------------------------------------------------------------
class subprocessDummy():

    def __init__(self):
        self._processes = {}
        self._names = {}

    def _add_process(self, p):
        self._processes[p.pid] = p
        self._names[p._name] = p

    def _remove_process(self, p):
        pold = self._processes.pop(p.pid, None)
        assert pold == p
        del self._names[p._name]

    def GetByPID(self, pid):
        return self._processes[pid]

    def GetByName(self, name):
        return self._names[name]

    def list2cmdline(self, cmdline):
        return subprocess.list2cmdline(cmdline)

    def Popen(self, cmdargs, *_args, **_kwargs):
        p = popenDummy(self, cmdargs[-1])
        return p
# --------------------------------------------------------------------------------------------------
class Test_TestWatchdog(base.TestCase):
    def setUp(self):
        super().setUp()
        self.sd = subprocessDummy()
        watchdog.subprocess = self.sd
        self.watchdog = watchdog.Watchdog(scripts = ['a', 'b', 'c'])
        self.watchdog.loop_time = 0.5
        self.ftr = base.Future(self.watchdog) # hier startet jetzt der Watchdog-Thread

    def tearDown(self):
        super().tearDown()
        self.watchdog.Terminate()
        self.ftr.WaitForResult()

    def test_Watchdog(self):
        self.assertTrue(self.ftr.WaitForExectionStart(1), "Future starts within time.")
        self.ftr.Join(3.0) # die Prozesse starten im Abstand von einer Sekunde!
        self.assertEqual(
            len(self.watchdog.processes), 3,
            "All processes have been started: {}".format(self.watchdog.processes)
        )
        self.ftr.Join(1.0)
        self.assertEqual(
            len(self.watchdog.processes), 3,
            "All processes are still running: {}".format(self.watchdog.processes)
        )
        p = self.sd.GetByName('b')
        p_pid = p.pid
        p._set_exitcode(popenDummy.EXITCODE_FINISHED)
        self.ftr.Join(1.0)

        self.assertNotIn(
            p, self.watchdog.processes,
            "Termination of process {} not detected.".format(p)
        )

        self.ftr.Join(1.0)
        p = self.sd.GetByName('b')
        self.assertFalse(p.pid == p_pid, "Process {} has been restarted (PID check)".format(p))
        self.assertIn(
            p, self.watchdog.processes,
            "Process {} has been restarted (set check)".format(p)
        )

        procs = list(self.sd._processes.values())
        for p in procs:
            p._set_exitcode(popenDummy.EXITCODE_FINISHED)
        self.ftr.Join(1.0)
        r = True
        for p in procs:
            r &= (p not in self.watchdog.processes)
        self.assertTrue(r, "Termination of all processes has been detected.")

        self.ftr.Join(1.0)
        self.assertEqual(len(self.watchdog.processes), 3, "All processes have been restarted.")

        p = self.sd.GetByName('a')
        p._send_signal = popenDummy.SIGNAL_RAISE
        procs = list(self.sd._processes.values())

        self.watchdog.Terminate()
        self.ftr.WaitForResult()

        self.assertEqual(
            len(self.watchdog.processes), 0,
            "All processes have been removed: {}".format(self.watchdog.processes)
        )

        for p in procs:
            if p._name == 'a':
                self.assertEqual(
                    p.poll(), popenDummy.EXITCODE_KILL,
                    "Process {} has been killed.".format(p)
                )
            else:
                self.assertEqual(
                    p.poll(), popenDummy.EXITCODE_SIGNAL,
                    "Process {} was signaled with SIGINT.".format(p)
                )
        return True
# --------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()
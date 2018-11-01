#! /usr/bin/python3
# -*- coding: utf8 -*-
# ---------------------------------------------------------------------------------------
import os
import time
import datetime
import subprocess
from base import * # pylint: disable=W0614
from config import *  # pylint: disable=W0614
import watchdog
# ---------------------------------------------------------------------------------------
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
# ---------------------------------------------------------------------------------------
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

    def Popen(self, cmdargs, *args, **kwargs):
        p = popenDummy(self, cmdargs[-1])
        return p
# ---------------------------------------------------------------------------------------
@testfunction
def test():
    sd = subprocessDummy()
    watchdog.subprocess = sd
    w = watchdog.Watchdog(scripts = ['a', 'b', 'c'])
    w.loop_time = 0.5
    f = Future(w)
    check(f.WaitForExectionStart(1), "Future starts within time.")

    try:
        time.sleep(3.0)
        check(len(w.processes) == 3, "All processes have been started: %s", w.processes)
        time.sleep(1.0)
        check(len(w.processes) == 3, "All processes are still running: %s", w.processes)
        p = sd.GetByName('b')
        p_pid = p.pid
        p._set_exitcode(popenDummy.EXITCODE_FINISHED)
        time.sleep(1)
        check(p not in w.processes, "Termination of process %r has been detected.", p)
        time.sleep(1)
        p = sd.GetByName('b')
        check(p.pid != p_pid, "Process %r has been restarted (PID check)", p)
        check(p in w.processes, "Process %r has been restarted (set check)", p)
        procs = list(sd._processes.values())
        for p in procs:
            p._set_exitcode(popenDummy.EXITCODE_FINISHED)
        time.sleep(1)
        r = True
        for p in procs:
            r &= (p not in w.processes)
        check(r, "Termination of all processes has been detected.")
        time.sleep(1)
        check(len(w.processes) == 3, "All processes have been restarted.")
        p = sd.GetByName('a')
        p._send_signal = popenDummy.SIGNAL_RAISE
        procs = list(sd._processes.values())
    finally:
        w.Terminate()
        f.WaitForResult()

    check(len(w.processes) == 0, "All processes have been removed: %s", w.processes)
    for p in procs:
        if p._name == 'a':
            check(p.poll() == popenDummy.EXITCODE_KILL, "Process %r has been killed.", p)
        else:
            check(p.poll() == popenDummy.EXITCODE_SIGNAL, "Process %r was signaled with SIGINT.", p)
    return True
# ---------------------------------------------------------------------------------------
if __name__ == '__main__':
    test()
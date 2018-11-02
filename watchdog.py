#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Script startet und überwacht alle Skripte für die Steuerung und
Überwachung des Chicken-Guard.
Diese werden in :py:data:`_scripts` abgelegt.

Das sind:
* Der Server für die WebCam (*cameraserver.py*)
* Der Boardcontroller (*controlserver.py*)
* Der Displaycontroller (*tftcontrol.py*)

Beispiel:

.. code-block:: python

    # Initialisieren mit foo und bar Skripten aus dem
    # selben Verzeichnis
    w = Watchdog(scripts = ['foo.py', 'bar.py])
    w()

Logging erfolg nach *watchdog.log* (siehe dazu :py:class:`LoggableClass`).
"""
# ------------------------------------------------------------------------
import sys
import subprocess
import signal
import time
from shared import LoggableClass, root_path
# ------------------------------------------------------------------------
#: Liste mit den zu startenden und überwachenden Python-Scripts.
_scripts = ('controlserver.py', 'cameraserver.py', 'tftcontrol.py')

#: SIGINT funktioniert unter Windows nicht, aber auch dort
#: gibt es nur CLTR_C_EVENT, also nehmen wir das wenn verfügbar.
SIGINT = getattr(signal, 'CTRL_C_EVENT', signal.SIGINT)
# ------------------------------------------------------------------------
class Watchdog(LoggableClass):

    def __init__(self, scripts = _scripts):
        """
        Initialisiert die Instanz.
        :param sequence _scripts: Eine Liste von Python-Script-Dateinamen
            (inklusive Endung) relativ zu :py:data:`root_path`.
            Diese werden beim Aufruf von :py:meth:`__call__` gestartet
            und überwacht.
        """
        super().__init__(name = "watchdog")
        #: Menge der zu überwachenden Prozess
        self.processes = set()
        #: Die Wartezeit nach Ende jeder Loop.
        self.loop_time = 5.0
        #: Liste mit den zu startenden und überwachenden Python-Scripts.
        self.scripts = list(scripts)
        #: Run-Flag, kann auf Fals gesetzt werden um die Loop zu beenden.
        self._run = True

    def StartSingle(self, scriptname):
        """
        Startet ein einzelnes Python-Script.

        :param str scriptname: Name der Scriptdatei (inklusive Endung).
            Wird relativ zu :py:data:`root_path` aufgelöst.

        :returns: Das Popen-Objekt im Erfolgsfall, sonst *None*.

        """
        scriptpath = root_path / scriptname
        cmdline =  [sys.executable, str(scriptpath)]
        self.info("Starting %s", subprocess.list2cmdline(cmdline))
        try:
            p = subprocess.Popen(cmdline)
        except Exception as e: # pylint: disable=W0703
            self.error("Could not start '%s': %s", subprocess.list2cmdline(cmdline), e)
            return None
        p.name = scriptname
        self.info("Started '%s' with pid %s.", scriptname, p.pid)
        return p

    def StartAll(self):
        """
        Startet alle Scripte aus :py:attr:`scripts`.
        Wenn alle erfolgreich gestartet wurden, ist die Rückgabe *True*.
        Schlägt mindestens ein Start fehl, wird das weitere Starten hier
        abgebrochen und *False* zurückgeliefert.
        Zwischen den Starts wird immer 1 Sekunde gewartet.
        Jeder gestartete Prozess wird zu :py:attr:`processes` hinzugefügt.
        """
        for scriptname in self.scripts:
            p = self.StartSingle(scriptname)
            if p is None:
                return False
            self.processes.add(p)
            time.sleep(1) # kurz warten, damit der Prozess hochfahren kann
        return True

    def Run(self):
        """
        Die Mainloop des Watchers.
        Startet alle Skripte aus :py:attr:`scripts` und überwacht diese.
        Wird eines der Skripte vorzeitig beendet, wird es neu gestartet.
        Beenden der Loop erfolgt mit *SIGINT*.
        Zwischen **jeder** Loop wird :py:attr:`looptime` Sekunden geschlafen.

        :returns: *False* wenn der Start der Skripte zu Beginn fehlgeschlagen
            ist, sonst immer *True*.
        """
        self.info("Started.")

        if not self.StartAll():
            return False

        # hier legen wir die Scriptnamen der Prozesse ab, die sich beendet haben
        # und neu gestartet werden müssen.
        needs_restart = set()

        while self._run:
            self.debug("Doing process check.")

            failed = set() # hier kommen die PIDs der fehlgeschlagenen Prozesse rein
            for p in self.processes:
                exitcode = p.poll()
                if exitcode is not None:
                    self.warning(
                        "Process '%s' with PID %d terminated with exitcode %s, starting again.",
                        p.name, p.pid, exitcode)
                    failed.add(p)
                    needs_restart.add(p.name)

            # die heruntergefahrenen entfernen
            self.processes.difference_update(failed)

            # und wieder neu starten. im vorigen Lauf fehlgeschlagene auch wieder starten
            for name in needs_restart.copy():             # wir nehmen eine Kopie, da wir das set
                                                          # in der Loop ändern
                p = self.StartSingle(name)                # jetzt starten
                if (p is not None) and p.poll() is None:  # hat es geklappt?
                    needs_restart.discard(name)           # ja, also aus der Menge der zu
                                                          # startenden entfernen
                    self.processes.add(p)                 # und den laufenden hinzufügen
                else:
                    # nein, also Warnung ausgeben und später erneut versuchen
                    self.warning("Failed to start '%s', tryiing again later.", name)

            # die Wartezeit halten wir immer ein, da es hier nichts macht, wenn mal längere
            # Zeit ein Skript nicht läuft.
            time.sleep(self.loop_time)

        self.info("Finished.")
        return True

    def _CheckExitCode(self, process):
        exitcode = process.poll()
        if not exitcode is None:
            self.info(
                "Process '%s' with PID %d has finished with exitcode %d.",
                process.name, process.pid, exitcode
            )
            self.processes.discard(process)

    def _Kill(self, process):
        try:
            process.kill()
        except Exception as e: # pylint: disable=W0703
            self.error(
                "Failed to send SIGKILL to '%s' with PID %d: %s",
                process.name, process.pid, e
            )
        else:
            self.info("Killed '%s' with PID %d.", process.name, process.pid)
            return True
        return False

    def Cleanup(self):
        """
        Räumt alle gestarten Prozesse weg.
        Zuerst wird versucht, ein :py:data:`SIGINT` an den Prozess zu schicken.
        Sollte das fehlschlagen oder der Prozess nach 5 Sekunden immer noch laufen,
        wird *SIGKILL* geschickt.
        Im Erfolgsfall ist :py:attr:`processes` nach Ende dieser Methode immer
        leer.
        """
        self.info("Cleaning up.")
        try:
            for p in self.processes.copy():
                exitcode = p.poll()
                if exitcode is None:
                    try:
                        p.send_signal(SIGINT)
                    except Exception as e: # pylint: disable=W0703
                        self.error("Failed to send SIGINT to '%s' with PID %d: %s", p.name, p.pid, e)
                        self._Kill(p)
                    else:
                        self.info("Sent SIGINT to '%s' with PID %d.", p.name, p.pid)
                    time.sleep(0.1)
                    self._CheckExitCode(p)

            # jetzt warten wir kurz, damit alle die Chance haben, zu gehen
            if self.processes:
                self.warn("Waiting for %d process(es) to exit.", len(self.processes))
                stop_time = time.time() + 5.0
                while self.processes and (time.time() < stop_time):
                    for p in self.processes.copy():
                        self._CheckExitCode(p)
                        time.sleep(0.1)

            # alle die jetzt noch da sind, werden gekillt (wenn möglich)
            if self.processes:
                self.warn(
                    "Following processes are still running, will try to kill again: %s",
                    ', '.join(p.name for p in self.processes)
                )
                for p in self.processes.copy():
                    if self._Kill(p):
                        self._CheckExitCode(p)
                if self.processes:
                    self.error("Finally failed to kill all processes, exiting now.")
                    self.processes.clear()
        except Exception: # pylint: disable=W0703
            self.exception("Error during cleanup.")

    def Terminate(self):
        self._run = False

    def __call__(self):
        """
        Startet den Watcher bis zu einem *KeyboardInterrupt* (SIGINT).
        Siehe :py:meth:`Run`.
        """
        try:
            self.Run()
        except KeyboardInterrupt:
            self.info("Catched Keyboardinterrupt, stopped.")
        except Exception: # pylint: disable=W0703
            self.exception("Unhandled error!")
        finally:
            self.Cleanup()
# ------------------------------------------------------------------------
def main():
    watchdog = Watchdog()
    watchdog()
# ------------------------------------------------------------------------
if __name__ == '__main__':
    main()
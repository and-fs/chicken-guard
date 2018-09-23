#! /usr/bin/python3
# -*- coding: utf8 -*-
# ------------------------------------------------------------------------
import pathlib
import logging
import os
# ------------------------------------------------------------------------
from config import * # pylint: disable=W0614
# ------------------------------------------------------------------------
root_path = pathlib.Path(__file__).parent
"""Dieser Pfad ist der Basispfad in dem auch die Skripte / Pythonmodule liegen"""

log_path = root_path.joinpath(LOGDIR)
"""Pfad zu den Logging-Dateien."""

resource_path = root_path.joinpath(RESOURCEDIR)
"""Enthält etwaige Ressourcen (Bilder etc.)"""
# ------------------------------------------------------------------------
logging_configured = False
"""Guard für die Ausführung von configureLogging"""
# ------------------------------------------------------------------------
def configureLogging(name, filemode = 'w'):
    """
    Führt eine Basiskonfiguration des logging durch.
    Verwendet LOGFORMAT, LOGDATEFMT und LOGLEVEL aus config.
    Wenn die Konfiguration in diesem Prozess bereits durchgeführt
    wurde, hat der Aufruf keinen Effekt.

    Args:
        name (str, optional): Name des Loggers. Unter diesem wird
            mit der Dateinamenserweiterung (Extension) `.log` die
            Logdatei in log_path erzeugt.
        filemode (str, optional): Dateimodus für die Logging-Datei.
            Muss ein Schreibmodus sein, Standard ist 'w'.
    """
    global logging_configured
    if logging_configured:
        return

    logging_configured = True

    log_path.mkdir(parents = True, exist_ok = True)

    logfilepath = log_path.joinpath(name + '.log')

    if not 'w' in filemode:
        with logfilepath.open(filemode) as f:
            f.write(os.linesep)
            f.write('-' * 80)
            f.write(os.linesep)

    logging.basicConfig(
        filename = logfilepath,
        filemode = filemode,
        format = LOGFORMAT,
        datefmt = LOGDATEFMT,
        level = LOGLEVEL
    )

    logging.info("Started.")
# ------------------------------------------------------------------------
def getLogger(name = None, filemode = 'w'):
    """
    Liefert eine Logger-Instanz.
    Ruft zuerst immer configureLogging mit `name` und `filemode` auf,
    gibt dann einen Logger aus logging zurück.
    Args:
        name (str, optional): Name des Loggers. Wenn `None` oder
            nicht angegeben, wird `'root'` verwendet.
        filemode (str, optional): Dateimodus für die Logging-Datei.
            Muss ein Schreibmodus sein, Standard ist 'w'.
    """
    configureLogging('root' if (name is None) else name, filemode)
    return logging.getLogger(name)
# ------------------------------------------------------------------------
class LoggableClass(object):
    """
    Basisklasse für alle Klassen mit Logausgabe.
    Fügt ein Attribut `logger` zur Instanz hinzu, auf dessen Eigenschaften
    dann via `self` zugegriffen werden kann.
    Also statt `self.logger.info(..)` kann dann einfach `self.info(..)`
    verwendet werden.

    Attributes:
        logger: Zu verwendende Logger-Instanz. Ist immer gesetzt.
    """
    def __init__(self, logger = None, name = None):
        """
        Initialisiert die logbare Instanze.
        Args:
            logger: Instanz eines Loggers, der verwendetet werden soll.
                Wenn `None` oder nicht angegeben, wird mittels getLogger
                eine neue Logger-Instanz erzeugt.
            name (str, optional): Name für einen etwaigen neu zu erzeugenden
                Logger (also nur zutreffend, wenn `logger` `None` ist).
                Dieser wird an getLogger übergeben.
        """
        if logger is None:
            self.logger = getLogger(name)
        else:
            self.logger = logger

    def __getattr__(self, name):
        if hasattr(self.logger, name):
            return getattr(self.logger, name)
        raise AttributeError("Instance of %s has no attribute '%s'" % (self.__class__, name))
# ------------------------------------------------------------------------
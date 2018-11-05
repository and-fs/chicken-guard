#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Enthält gemeinsam genutzte Klassen und Funktionen.
"""
# --------------------------------------------------------------------------------------------------
# pylint: disable=C0103, W0603, R0903
# --------------------------------------------------------------------------------------------------
import pathlib
import logging
import os
from logging import handlers
# --------------------------------------------------------------------------------------------------
from config import * # pylint: disable=W0614
# --------------------------------------------------------------------------------------------------
#: Basispfad, hier liegen auch die Skripte und Module.
root_path = pathlib.Path(__file__).parent

#: Pfad zu den Logging-Dateien.
log_path = root_path.joinpath(LOGDIR)

#: Enthält etwaige Ressourcen (Bilder etc.)
resource_path = root_path.joinpath(RESOURCEDIR)

#: Guard für die Ausführung von :func:`configureLogging`
logging_configured = False
# --------------------------------------------------------------------------------------------------
def configureLogging(name:str, filemode:str = 'a'):
    """
    Führt eine Basiskonfiguration des logging durch.
    Verwendet :data:`config.LOGFORMAT`, :data:`config.LOGDATEFMT` und :data:`config.LOGLEVEL`.
    Wenn die Konfiguration in diesem Prozess bereits durchgeführt
    wurde, hat der Aufruf keinen Effekt (dazu wird :data:`logging_configured` verwendet).

    :param str name: Name des Loggers. Unter diesem wird mit der Dateinamenserweiterung (Extension)
            *.log* die Logdatei in :data:`log_path` erzeugt.

    :param str filemode: Dateimodus für die Logging-Datei.
            Muss ein Schreibmodus sein, Standard ist ``w``.
    """

    global logging_configured
    if logging_configured:
        return

    logging_configured = True

    log_path.mkdir(parents = True, exist_ok = True)

    logfilepath = log_path.joinpath(name + '.log')

    if 'w' not in filemode:
        with logfilepath.open(filemode) as f:
            f.write(os.linesep)
            f.write('-' * 80)
            f.write(os.linesep)

    formatter = logging.Formatter(LOGFORMAT, LOGDATEFMT)
    handler = handlers.TimedRotatingFileHandler(
        str(logfilepath),
        when = 'd',
        interval = 1,
        backupCount = 5
    )
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.setLevel(LOGLEVEL)
    logger.addHandler(handler)
    logger.info("Started, pid = %s.", os.getpid())
# ------------------------------------------------------------------------
def getLogger(name = None, filemode = 'a'):
    """
    Liefert eine Logger-Instanz.
    Ruft zuerst immer :func:`configureLogging` mit ``name`` und ``filemode`` auf,
    gibt dann einen Logger aus logging zurück.

    :param str name: Name des Loggers. Unter diesem wird mit der Dateinamenserweiterung (Extension)
            *.log* die Logdatei in :data:`log_path` erzeugt.

    :param str filemode: Dateimodus für die Logging-Datei.
            Muss ein Schreibmodus sein, Standard ist ``w``.
    """
    configureLogging('root' if (name is None) else name, filemode)
    return logging.getLogger(name)
# ------------------------------------------------------------------------
class LoggableClass:
    """
    Basisklasse für alle Klassen mit Logausgabe.
    Fügt ein Attribut ``logger`` zur Instanz hinzu, auf dessen Eigenschaften
    dann via ``self`` zugegriffen werden kann.
    Also statt ``self.logger.info(..)`` kann dann einfach ``self.info(..)``
    verwendet werden.
    """
    def __init__(self, logger:logging.Logger = None, name:str = None):
        """
        Initialisiert die logbare Instanz.

        :param logging.Logger logger: Instanz eines Loggers, der verwendetet werden soll.
            Wenn ``None`` oder nicht angegeben, wird mittels _func:`getLogger`
            eine neue Logger-Instanz erzeugt.

        :param str name: Name für einen etwaigen neu zu erzeugenden
            Logger (also nur zutreffend, wenn ``logger == None`` ist).
            Dieser wird an :func:`getLogger` übergeben.
        """
        #: Zu verwendende Logger-Instanz. Ist immer gesetzt.
        self.logger = getLogger(name) if logger is None else logger

    def __getattr__(self, name:str):
        """
        Überladung des Operators, prüft ob ``name`` als Attribut in :attr:`logger` vorhanden
        ist und liefert im positiven Fall dieses zurück.
        Ansonsten wird ein `AttributeError` geworfen.
        """
        if hasattr(self.logger, name):
            return getattr(self.logger, name)
        raise AttributeError("Instance of %s has no attribute '%s'" % (self.__class__, name))
# ------------------------------------------------------------------------
#! /usr/bin/python3
# -*- coding: utf8 -*-
# ------------------------------------------------------------------------
import pathlib
import logging
import os
# ------------------------------------------------------------------------
from config import *
# ------------------------------------------------------------------------
root_path = pathlib.Path(__file__).parent.parent
log_path = root_path.joinpath(LOGDIR)
script_path = root_path.joinpath(SCRIPTDIR)
resource_path = script_path.joinpath(RESOURCEDIR)
# ------------------------------------------------------------------------
logging_configured = False
# ------------------------------------------------------------------------
def configureLogging(name, filemode = 'w'):

    global logging_configured
    if logging_configured:
        return
    logging_configured = True

    logfilepath = log_path.joinpath(name + '.log')

    if not 'w' in filemode:
        with logfilepath.open(filemode) as f:
            f.write(os.linesep)
            f.write('-' * 80)
            f.write(os.linesep)

    logging.basicConfig(
        filename = logfilepath,
        filemode = filemode,
        format = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        datefmt = '%m-%d %H:%M:%S',
        level = logging.DEBUG
    )

    logging.info("Started.")
# ------------------------------------------------------------------------
def getLogger(name = None, filemode = 'w'):
    configureLogging('root' if (name is None) else name, filemode)
    return logging.getLogger(name)
# ------------------------------------------------------------------------
class LoggableClass(object):
    def __init__(self, logger = None, name = None):
        if logger is None:
            self.logger = getLogger(name)
        else:
            self.logger = logger

    def __getattr__(self, name):
        if hasattr(self.logger, name):
            return getattr(self.logger, name)
        raise AttributeError("Instance of %s has no attribute '%s'" % (self.__class__, name))
# ------------------------------------------------------------------------
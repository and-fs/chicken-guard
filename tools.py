#! /usr/bin/python3
# -*- coding: utf8 -*-
# ------------------------------------------------------------------------
import sys
import time
import threading
import xmlrpc.client
# ------------------------------------------------------------------------
from shared import LoggableClass
from gpio import GPIO, SMBus
from config import * # pylint: disable=W0614
# ------------------------------------------------------------------------
class CallError(object):
    def __init__(self, message, exc_info = None):
        self.message = message
        self.exc_info = exc_info
# ------------------------------------------------------------------------
class AsyncFunc(LoggableClass):
    def __init__(self, funame, callback = None):
        name = 'call-%s' % (funame,)
        LoggableClass.__init__(self, name = name)
        self.funame = funame
        self.callback = callback
        self.thread = None

    def join(self):
        if self.thread is None:
            raise RuntimeError("Call is joinable earliest after calling!")

        if self.thread.is_alive:
            self.debug("Joining thread for call to %r" % (self.funame,))
            self.thread.join()

    def __call__(self, *args, **kwargs):
        name = 'call-%s' % (self.funame,)
        self.thread = threading.Thread(target = self.__run, name = name, args = args, kwargs = kwargs)
        self.thread.setDaemon(True)
        self.thread.start()

    def __run(self, *args, **kwargs):
        proxy = xmlrpc.client.ServerProxy(
            CONTROLLER_URI,
            allow_none = True,
            use_builtin_types = True,
        )
        func = getattr(proxy, self.funame)

        try:
            result = func(*args, **kwargs)
        except Exception:
            self.exception("Failed to call %r.", self.funame)
            if self.callback:
                result = CallError("Failed.", exc_info = sys.exc_info())

        if self.callback:
            try:
               self.callback(result)
            except Exception:
                self.exception("Failed to callback.")

# ------------------------------------------------------------------------
def _StateChangeHandler(logger, handler, terminate_condition):
    proxy = xmlrpc.client.ServerProxy(
        CONTROLLER_URI,
        allow_none = True,
        use_builtin_types = True,
    )
    
    waittime = 30.0

    while not terminate_condition():
        now = time.time()
        logger.debug("Calling WaitForStateChange.")
        try:
            changed, state = proxy.WaitForStateChange(waittime)
        except ConnectionRefusedError:
            logger.warn("Proxy not reachable, trying again later.")
        except Exception:
            logger.exception("Error while calling WaitForStateChange.")
        else:
            logger.debug("Received status change: %r", changed)
            if terminate_condition():
                break
            if changed:
                try:
                    handler(state)
                except Exception:
                    logger.exception("Error while calling change state handler.")
                continue
        if terminate_condition():
            break
        time_left = waittime - (time.time() - now)
        if time_left < 1.0:
            continue
        logger.debug("Go sleeping for %.2f seconds.", time_left)
        time.sleep(time_left)

def InstallStateChangeHandler(*args):
    t = threading.Thread(target = _StateChangeHandler, args = args)
    t.setDaemon(True)
    t.start()
    return t
# ------------------------------------------------------------------------

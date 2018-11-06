#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Hilfsfunktionen und Klassen für XMLRPC-Aufrufe.
"""
# --------------------------------------------------------------------------------------------------
# pylint: disable=R0903
import sys
import time
import threading
import xmlrpc.client
# --------------------------------------------------------------------------------------------------
from shared import LoggableClass
from constants import * # pylint: disable=W0614
# --------------------------------------------------------------------------------------------------
class CallError:
    """
    Instanzen dieser Klasse werden in :class:`AsyncFunc` verwendet, um einen Aufruffehler
    im Rückgabewert der Funktion zu signalisieren.
    """
    def __init__(self, message:str, exc_info:tuple = None):

        #: Fehlernachricht.
        self.message = message

        #: Exceptioninformationen (siehe ``sys.exc_info``), ``None`` wenn keine Exception
        #: vorliegt.
        self.exc_info = exc_info
# --------------------------------------------------------------------------------------------------
class AsyncFunc(LoggableClass):
    """
    Wrapper für asynchrone Aufrufe an XMLRPCs unter der URI :data:`config.CONTROLLER_URI`
    (ähnlich eines Future oder Promise).

    Instanzen dieser Klasse können wie ein ``callable`` verwendet werden, nur das die
    Aufrufe in einem separatem Thread asynchron als XMLRPC aufgerufen werden.
    Die Ergebnisse des Aufrufs werden an das optionale Callback übermittelt.

    Beispiel:

    .. code-block:: python

        # callback-Funktion, wird aufgerufen, sobald der XMLRPC-Aufruf zurückkehrt
        def PrintState(result):
            if isinstance(result, CallError):
                print ("Error:", result.message)
            else:
                print ("State:", result)
        # Aufruf erzeugen
        fu = AsyncFunc("GetBoardState", callback = PrintState)
        # und aufrufen
        fu()
        # ab hier kann jetzt irgendetwas anderes gemacht werdenm, sobald der
        # Aufruf durch ist wird PrintState gerufen - aber: in einem anderen
        # Thread!

    """
    def __init__(self, funame:str, callback:callable = None):
        """
        Initialisiert den Aufruf mit dem Funktionsname ``funame`` und einem optionalen
        ``callback``, der bei Vorliegen des Ergebnis unmittelbar gerufen wird.

        :param str funame: Name der Funktion, die als XMLRPC am Server :data:`CONTROLLER_URI`
            gerufen werden soll.

        :param callable callback: Optionaler Handler, der bei Vorliegen des Ergebnis mit
            dem Ergebnis als einziges Argument aufgerufen wird. Im Fehlerfall ist dieser
            Parameter vom Typ :class:`CallError`.
        """
        name = 'call-%s' % (funame,)
        LoggableClass.__init__(self, name = name)

        #: Name der Funktion, die als XMLRPC am Server :data:`CONTROLLER_URI`
        #: gerufen werden soll.
        self.funame = funame

        #: Optionale Rückruffunktion für das Ergebnis. Bekommt nur ein Argument (das Ergebnis des
        #: Aufrufs). Im Fehlerfall ist dieses Argument vom Typ :class:`CallError`.
        self.callback = callback

        #: Der Thread, in der der Aufruf stattfindet.
        self.thread = None

    def Join(self):
        """
        Hängt den aufrufenden Thread an die Ausführung der Funktion in :attr:`thread`.
        Kehrt erst zurück, wenn der Funktionsaufruf im :attr:`thread` beendet wurde.
        """
        if self.thread is None:
            raise RuntimeError("Call is joinable earliest after calling!")

        if self.thread.is_alive:
            self.debug("Joining thread for call to %r" % (self.funame,))
            self.thread.join()

    def __call__(self, *args, **kwargs):
        """
        Startet den Aufruf des XMLRPC :attr:`funame` mit den hier übergebenen Argumenten.
        Dazu wird ein separater Thread gestartet, der den Aufruf durchführt und das
        Ergebnis an den :attr:`callback` weitergibt.
        """
        name = 'call-%s' % (self.funame,)
        self.thread = threading.Thread(
            target = self._run, name = name, args = args, kwargs = kwargs
        )
        self.thread.setDaemon(True)
        self.thread.start()

    def _run(self, *args, **kwargs):
        """
        Die eigentliche Aufrufmethode, wird in :attr:`thread` ausgeführt und kehrt
        erst zurück, wenn der XMLRPC zurückgekehrt oder ein Fehler aufgetreten ist.
        """
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

# --------------------------------------------------------------------------------------------------
def _StateChangeHandler(logger, handler:callable, terminate_condition:callable):
    """
    Diese Funktion ruft in einer Endlosschleife :meth:`controlserver.Controller.WaitForStateChange`
    als XMLRPC. Diese Schleife wird erst dann beendet, wenn der Aufruf von ``terminate_condition``
    ``True`` liefert.
    Das Ergebnis von :meth:`controlserver.Controller.WaitForStateChange` wird an den ``handler``
    übermittelt, wenn eine Änderung am Status vorlag.

    :param logging.Logger logger: Logger für die Ausgabe von Ablaufinfos.

    :param callable handler: Handler der aufgerufen wird, wenn eine Statusänderung
        vorliegt. Erhält als einzigen Parameter das Statusdictionary der Rückgabe
        des Aufrufs von :meth:`controlserver.Controller.WaitForStateChange`. Wird nur
        gerufen, wenn auch wirklich eine Statusänderung stattgefunden hat.

    :param callable terminate_condition: Ein Callable, dass ohne Parameter gerufen wird
        und ein mit ``bool`` evaluierbares Ergebnis liefern muss, dass signalisiert, ob
        dieser Handler beendet werden soll.
        Bei einer Rückgabe von ``False`` läuft der Thread weiter.
    """
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
# --------------------------------------------------------------------------------------------------
def InstallStateChangeHandler(*args)->threading.Thread:
    """
    Startet einen Thread, der den :func:`_StateChangeHandler` mit den Argumenten aus ``args``
    aufruft.
    """
    t = threading.Thread(target = _StateChangeHandler, args = args)
    t.setDaemon(True)
    t.start()
    return t
# ------------------------------------------------------------------------

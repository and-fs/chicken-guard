#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Script startet einen XMLRPC-Server unter der
Adresse :data:`config.CONTROLLER_HOST` auf dem Port :data:`config.CONTROLLER_PORT`
und stellt darüber die Schnittstelle zum Board zur Verfügung.

Alle Zugriffe sollten über diesen Server erfolgen (abgesehen vom TFT),
da so parallele Zugriffe ausgeschlossen sind.
"""
# ------------------------------------------------------------------------
import os
import xmlrpc.server
import socketserver
import threading
import time
import datetime
# --------------------------------------------------------------------------------------------------
import shared
import board
import sunrise
import notifier
from shared import LoggableClass, resource_path
from config import * # pylint: disable=W0614
# --------------------------------------------------------------------------------------------------
class JobTimer(LoggableClass):
    """
    Diese Klasse triggert zeitgesteuert fest programmierte Aktionen.
    Die Aktionszeiten sind dabei nur minutengenau, das vereinfacht die Berechnung der
    Aktionszeiten und ist für eine Hühnerstalltür mehr als ausreichend.

    Folgende Aktionen sind implementiert:

      - :meth:`Berechnung der Tür-Schaltzeiten<DoSunriseCheck>`
      - :meth:`Öffnen / Schließen der Tür nach den berechneten Zeiten<DoDoorCheck>`
      - :meth:`Schalten der Innenbeleuchtung<DoLightCheck>`
      - :meth:`Erfassen und Speichern der Sensorwerte<DoSensorCheck>`

    """
    def __init__(self, controller):
        """
        Initialisiert die Instanz. Logging erfolgt als ``JobTimer``.

        :param controller: Instanz des :class:`Controller`, über den die Schaltungen
            erfolgen.
        """
        LoggableClass.__init__(self, name = 'JobTimer')

        #: Verweis auf den :class:`Controller`, der den Timer hält und über diesen
        #: die Aktionen ausgeführt werden.
        self.controller = controller

        #: Termination-Flag, solange dieses ``False`` ist, wird der Timer weiter
        #: ausgeführt
        self._terminate = False

        #: Mit dem :attr:`Termination-Flag<_terminate>` verknüpfte Condition,
        #: wird u.a. zum Schlafenlegen des :attr:`Timer-Threads<_thread>` verwendet.
        self._terminate_condition = threading.Condition()

        #: Der Thread, in dem der Timer ausgeführt wird (die Thread-Loop läuft über
        #: :meth:`__call__`). Läuft als ``daemon`` damit der Thread den Shutdown nicht
        #: blockieren kann.
        self._thread = threading.Thread(target = self, name = 'JobTimer', daemon = True)

        #: Zeitpunkt der letzten Berechnung der Tür-Schaltzeiten als Sekunden (``time.time()``).
        #: Siehe dazu :meth:`DoSunriseCheck`.
        self.last_sunrise_check = 0

        #: Zeitpunkt der letzten Prüfung des Türzustands in Sekunden.
        #: Siehe dazu :meth:`DoDoorCheck`
        self.last_door_check = 0

        #: Zeitpunkt der letzten Erfassung der Sensorwerte in Sekunden.
        #: Siehe dazu :meth:`DoSensorCheck`
        self.next_sensor_check = 0

        #: Berechneter Zeitpunkt der Ausschaltzeit der Innenbeleuchtung.
        #: Nur gültig, wenn :attr:`light_switch_on_time` nicht ``None`` ist.
        self.light_switch_off_time = None

        #: Berechneter Zeitpunkt der Einschaltzeit der Innenbeleuchtung.
        #: Falls ``None``, erfolgt kein Zeitgesteuertes Schalten der Innenbeleuchtung.
        self.light_switch_on_time = None

    def Terminate(self):
        """
        Setzt das :attr:`Termination-Flag<_terminate>` und veranlasst so den
        :attr:`Timer-Thread<_thread>`, die Loop beim nächstmöglichen Zeitpunkt zu beenden.

        .. seealso::
            :meth:`Join`
            :meth:`IsRunning`
        """
        self.info("Terminating JobTimer.")
        with self._terminate_condition:
            self._terminate = True
            self._terminate_condition.notify_all()

    def Start(self):
        """
        Startet den :attr:`Timer-Thread<_thread>`.

        .. seealso::
            :meth:`Join`
            :meth:`IsRunning`
            :meth:`Terminate`
        """
        self.info("Starting JobTimer.")
        self._thread.start()

    def Join(self, timeout = None)->bool:
        """
        Hängt den aktuellen Thread an den :attr:`Timer-Thread<_thread>` bis dieser
        sich beendet oder das Timeout ``timeout`` erreicht wurde.

        :param float timeout: Timeout in Sekunden. ``None`` == unendlich.

        :returns: ``True`` wenn sich der :attr:`Timer-Thread<_thread>` in der angegebenen
            Zeit beendet hat.
        """
        if not self.IsRunning():
            return True
        with self._terminate_condition:
            return self._terminate_condition.wait(timeout)

    def IsRunning(self)->bool:
        """
        Gibt zurück, ob der :attr:`Timer-Thread<_thread>` noch läuft.
        """
        return self._thread.is_alive()

    def ShouldTerminate(self)->bool:
        """
        Liefert ``True`` wenn das :attr:`Termination-Flag<_terminate>` gesetzt ist.
        """
        with self._terminate_condition:
            return self._terminate

    def WakeUp(self):
        """
        Setzt die Ausführung des :attr:`Timer-Thread<_thread>` fort, wenn sich dieser
        gerade in einem Sleep befindet.
        """
        self.debug("WakeUp called.")
        with self._terminate_condition:
            self._terminate_condition.notify_all()

    def ResetCheckTimes(self):
        """
        Setzt die Prüfzeiten der Tür und der Schaltzeiten zurück, so dass im nächsten
        Loop eine Neuberechnung stattfindet.
        """
        with self._terminate_condition:
            self.last_door_check = 0
            self.last_sunrise_check = 0
            self._terminate_condition.notify_all()

    def DoSunriseCheck(
            self,
            dtnow: datetime.datetime,
            now: float,
            open_time: datetime.datetime,
            close_time: datetime.datetime):
        """
        Prüft ob eine nächste Berechnung der Türschließzeiten (basierend auf Sonnenauf-/untergang)
        durchgeführt werden muss und führt dieses ggf. aus.

        Wenn der letzte Prüfzeitpunkt in :attr:`last_sunrise_check` länger als die in
        :data:`config.SUNRISE_INTERVAL` angegebenen Sekunden her ist, erfolgt eine Neuberechnung.
        Diese kann auch mittels :meth:`ResetCheckTimes` erzwungen werden.

        Die Türzeiten richten sich nach Sonnenauf- und -untergang und werden in
        :func:`sunrise.GetNextActions` ermittelt (hier werden z.Bsp. noch konfigurierte Offsets
        oder früheste Öffnungszeiten berücksichtigt).

        Wenn der Wert für die Einschaltzeit des Lichts vor dem Schließen der Tür (siehe
        :data:`config.SWITCH_LIGHT_ON_BEFORE_CLOSING`) nicht 0 ist, werden diese Zeiten ebenfalls
        berechnet (:attr:`light_switch_on_time` und :attr:`light_switch_off_time`).

        .. warning:: Eine Berechnung der Lichtschaltzeit wird nicht durchgeführt, wenn die aktuelle
            Zeit ``now`` sich gerade zwischen Ein- und Ausschaltzeit befindet. Das dient dazu,
            dass eine Ausschaltzeit für das nächste Mal berechnet wird und somit das Licht bis
            dahin nicht mehr deaktiviert wird.

        :param datetime dtnow: Aktuelle Zeit als datetime - Objekt.

        :param float now: Aktuelle Zeit in Sekunden (siehe ``time.time()``).

        :param datetime open_time: Die aktuell verwendete (also zuletzt berechnete) Zeit
            zu der die Tür geöffnet werden soll.

        :param datetime close_time: Wie ``open_time`` allerdings zum Schließen.

        :returns: Ein Tuple aus Öffnungs- und Schließzeit für den aktuellen Zeitpunkt ``dtnow``.
            Diese können dann direkt in :meth:`DoDoorCheck` verwendet werden.
        """
        # aktuelle Sonnenaufgangs / Untergangszeiten holen
        if self.last_sunrise_check + SUNRISE_INTERVAL < now:
            # es wird wieder mal Zeit (dawn = Morgens, dusk = Abends)
            self.info("Doing sunrise time check.")
            open_time, close_time = sunrise.GetSuntimes(dtnow)
            # jetzt noch die nächsten beiden Aktionen ermitteln (für
            # die Anzeige im Display)
            next_steps = sunrise.GetNextActions(dtnow, open_time, close_time)
            self.controller.SetNextActions(next_steps)
            self.last_sunrise_check = now

            if SWITCH_LIGHT_ON_BEFORE_CLOSING > 0:
                # Wichtig: wenn das Licht zur Schließzeit der Tür automatisch
                # getriggert wird, darf in dieser Zeit die Lichtschaltzeit nicht
                # berechnet werden!
                can_calculate = True
                # die Start- und Endzeit des Intervall runden wir noch in die entsprechende
                # Richtung um die Zeit des Türprüfintervalls (weil in diesem auch die
                # Lichtschaltzeiten # geprüft werden)
                if not self.light_switch_on_time is None:
                    light_ivl_start = self.light_switch_on_time - datetime.timedelta(seconds = DOORCHECK_INTERVAL)
                    light_ivl_end = self.light_switch_off_time + datetime.timedelta(seconds = DOORCHECK_INTERVAL)

                    if (dtnow >= light_ivl_start) and (dtnow <= light_ivl_end):
                        # hier sind wir genau in der Lichtschaltzeit, also lassen wir hier
                        # die Berechnung aus und führen wir diese erst beim nächsten Mal durch,
                        # das reicht aus.
                        self.info("Skipped light switch times calculation due to beeing "
                                  "currently in light interval.")
                        can_calculate = False

                if can_calculate:
                    # jetzt ermitteln wir die Einschaltzeit für die Innenbeleuchtung
                    for item in next_steps:
                        if item is None:
                            break
                        dt, action = item
                        if dt < dtnow:
                            continue
                        if action == DOOR_CLOSED:
                            self.light_switch_on_time = (
                                dt - datetime.timedelta(seconds = SWITCH_LIGHT_ON_BEFORE_CLOSING)
                            )
                            self.light_switch_off_time = (
                                dt + datetime.timedelta(seconds = SWITCH_LIGHT_OFF_AFTER_CLOSING)
                            )
                            self.info(
                                "Calculated new light switch times: on at %s, off at %s.",
                                self.light_switch_on_time, self.light_switch_off_time
                            )
        return (open_time, close_time)

    def DoDoorCheck(
            self,
            dtnow: datetime.datetime,
            now: float,
            open_time: datetime.datetime,
            close_time: datetime.datetime):
        """
        Prüft, ob aktuell die Tür zu Öffnen oder Schließen ist.

        Hier wird auch der Wert der Automatik im :class:`Controller` herangezogen (siehe
        dazu auch :data:`Controller.automatic`). Diese wird wie folgt ausgewertet:

        ==================================== =======================================================
        :data:`config.DOOR_AUTO_DEACTIVATED` Automatik ist deaktiviert und muss explizit
                                             aktiviert werden.
        :data:`config.DOOR_AUTO_OFF`         Automatik ist inaktiv, wird aber spätestens
                                             :data:`config.DOOR_AUTOMATIC_OFFTIME` Sekunden nach
                                             dem letzten Inaktivierungsbefehl wieder aktiviert.
                                             Siehe dazu auch :meth:`Controller.DisableAutomatic`.
        :data:`config.DOOR_AUTO_ON`          Automatik ist aktiv, Tür und Licht wird gesteuert.
        ==================================== =======================================================

        :param datetime dtnow: Aktuelle Zeit als datetime - Objekt.

        :param float now: Aktuelle Zeit in Sekunden (siehe ``time.time()``).

        :param datetime open_time: Die aktuell zu verwendende Zeit
            zu der die Tür geöffnet werden soll.

        :param datetime close_time: Wie ``open_time`` allerdings zum Schließen.

        .. seealso::
            :meth:`DoSunriseCheck`
        """
        if self.controller.automatic == DOOR_AUTO_OFF:
            # wenn am controller die Automatik deaktiviert ist,
            # müssen wir prüfen, ob diese wieder angeschaltet werden muss
            if self.controller.automatic_enable_time <= now:
                self.info("Enabling door automatic due to reaching manual control timeout.")
                self.controller.EnableAutomatic()

        if self.controller.automatic == DOOR_AUTO_ON:
            # müssen wir die Tür öffnen / schließen?
            if self.last_door_check + DOORCHECK_INTERVAL < now:
                self.logger.debug("Doing door automatic check.")
                self.last_door_check = now
                action = sunrise.GetDoorAction(dtnow, open_time, close_time)
                if action == DOOR_CLOSED:
                    if not self.controller.IsDoorClosed():
                        self.info("Closing door, currently is night.")
                        self.controller._CloseDoorFromTimer() # pylint: disable=W0212
                        notifier.NotifyDoorAction(
                            self.logger, DOOR_CLOSED, dtnow, open_time, close_time
                        )
                else:
                    # wir sind nach Sonnenauf- aber vor Sonnenuntergang
                    if not self.controller.IsDoorOpen():
                        self.info("Opening door, currently is day.")
                        self.controller._OpenDoorFromTimer() # pylint: disable=W0212
                        notifier.NotifyDoorAction(
                            self.logger, DOOR_OPEN, dtnow, open_time, close_time
                        )
        else:
            self.logger.debug("Skipped door check, automatic is off.")

    def DoSensorCheck(self, now):
        """
        Prüft über :attr:`next_sensor_check` ob ein Lesen der Sensorwerte durchgeführt werden
        soll und triggert das ggf. durch einen Aufruf von :meth:`Controller._ReadSensors`.

        Das Intervall beträgt dabei immer :data:`config.SENSOR_INTERVALL` Sekunden.

        :param float now: Aktuelle Zeit in Sekunden (siehe ``time.time()``).
        """
        if self.next_sensor_check < now:
            self.next_sensor_check = now + SENSOR_INTERVALL
            self.controller._ReadSensors() # pylint: disable=W0212

    def DoLightCheck(self, dtnow:datetime.datetime):
        """
        Falls die Türautomatik aktiv (:data:`config.DOOR_AUTO_ON`) und eine Lichtschaltzeit in
        Abhängigkeit der Tür konfiguriert ist (:data:`config.SWITCH_LIGHT_ON_BEFORE_CLOSING`), wird
        hier geprüft, ob das Innenlicht ein- oder auszuschalten ist und die Aktion ggf.
        durchgeführt.

        :param datetime dtnow: Aktuelle Zeit als datetime - Objekt.

        .. seealso::
            :meth:`DoSunriseCheck`
            :meth:`Controller.IsIndoorLightOn`
            :meth:`Controller.SwitchIndoorLight`
        """
        if (self.controller.automatic == DOOR_AUTO_ON) and (not self.light_switch_on_time is None):
            if dtnow >= self.light_switch_off_time:
                if self.controller.IsIndoorLightOn():
                    self.info(
                        "Switching light off %.0f seconds after closing door.",
                        SWITCH_LIGHT_OFF_AFTER_CLOSING
                    )
                    self.controller.SwitchIndoorLight(False)
                self.light_switch_on_time = None
                self.light_switch_off_time = None
            elif dtnow >= self.light_switch_on_time:
                if not self.controller.IsIndoorLightOn():
                    self.info(
                        "Switching light on %.0f seconds before closing door.",
                        SWITCH_LIGHT_ON_BEFORE_CLOSING
                    )
                    self.controller.SwitchIndoorLight(True)

    def _run(self):
        """
        Die Loop des :attr:`Timer-Thread<_thread>`.

        Hier wird im Intervall von :data:`config.DOORCHECK_INTERVAL` Sekunden folgendes ausgeführt:
          - :meth:`Berechnung der Tür-Schaltzeiten<DoSunriseCheck>`
          - :meth:`Öffnen / Schließen der Tür nach den berechneten Zeiten<DoDoorCheck>`
          - :meth:`Schalten der Innenbeleuchtung<DoLightCheck>`
          - :meth:`Erfassen und Speichern der Sensorwerte<DoSensorCheck>`

        Sollte das :attr:`Termination-Flag<_terminate>` gesetzt sein, wird die Loop
        beendet.

        .. seealso::
            :meth:`IsRunning`
            :meth:`Terminate`
            :meth:`Join`
            :meth:`WakeUp`
        """
        self.info("JobTimer started.")
        open_time, close_time = sunrise.GetSuntimes(datetime.datetime.now())
        while not self.ShouldTerminate():
            now = time.time()
            dtnow = datetime.datetime.now()

            # Öffnen / Schließen berechnen
            (open_time, close_time) = self.DoSunriseCheck(dtnow, now, open_time, close_time)

            # Türstatus prüfen
            self.DoDoorCheck(dtnow, now, open_time, close_time)

            # Licht prüfen
            self.DoLightCheck(dtnow)

            # Sensorwerte holen
            self.DoSensorCheck(now)

            if self.ShouldTerminate():
                break

            with self._terminate_condition:
                if self._terminate_condition.wait(DOORCHECK_INTERVAL):
                    self.debug("Terminate condition is notified.")

        # falls jetzt noch jemand im Join hängt, wird der auch benachrichtigt.
        with self._terminate_condition:
            self._terminate_condition.notify_all()

        self.info("JobTimer stopped.")

    def __call__(self):
        """
        Einstiegspunkt des :attr:`Timer-Thread<_thread>`.
        Ruft im wesentlichen :meth:`_run`, fängt hier aber etwaige Exceptions ab
        und gibt diese im Log aus.
        """
        try:
            self._run()
        except Exception:
            self.exception("Error in JobTimer thread loop.")
# ------------------------------------------------------------------------
class Controller(LoggableClass):
    """
    Diese Klasse dient als XMLRPC-Proxy zum Board.
    Alle öffentlichen Methoden können in einem XMLRPC-Server als aufrufbar
    registriert werden.

    .. code-block:: python

        from xmlrpc.server import SimpleXMLRPCServer
        controller = Controller()
        server = SimpleXMLRPCServer(('localhost', 8081), allow_none = True)
        server.register_instance(controller)
        server.serve_forever()
    """
    def __init__(self, start_jobs:bool = True):
        """
        :param bool start_jobs: Gibt an, ob der :class:`JobTimer` gestartet
            werden soll.
        """
        LoggableClass.__init__(self, name = "Controller")
        self.board = board.Board()

        #: Liste der nächsten Schritte, jeder besteht aus einem Tupel
        #: mit Zeitstempel und der Aktion, die dann vorgenommen wird
        #: (DOOR_OPEN oder DOOR_CLOSED)
        self.next_actions = tuple()

        #: Gibt an, ob die Tür über die Automatic gesteuert wird
        #: oder manuell. Wird vom job_timer verwendet.
        self.automatic = DOOR_AUTO_ON

        #: Zeitpunkt an dem die Türautomatik wieder aktiviert wird, wenn
        #: der Türstatur DOOR_AUTO_OFF ist.
        self.automatic_enable_time = -1

        self._state_lock = threading.Lock()
        self._state = (False, self.board.GetState())
        self._state_cond = threading.Condition(self._state_lock)

        self.temperature = 0.0
        self.light_sensor = 0
        self.sensor_file = resource_path / SENSORFILE

        self.board.SetStateChangeHandler(self._BoardStateChanged)

        self.job_timer = JobTimer(self)
        if start_jobs:
            self.job_timer.Start()

    def SetNextActions(self, actions:tuple):
        """
        Wird vom :class:`JobTimer` gerufen, wenn neue Zeiten für die Türbewegung
        kalkuliert wurden. Triggert einen Board-Status-Update, der etwaige wartende
        Change-Handler ruft.

        :param tuple actions: Ein Tuple mit zwei Werten, jeder Wert ist wiederum ein
            Tuple bestehend aus Zeitpunkt und Aktion: ``((Zeit, Aktion), (Zeit, Aktion))``.
            ``Zeit`` ist hier der Zeitpunkt, an dem die zugehörige ``Aktion`` durchzuführen ist.
            ``Aktion`` ist entweder :data:`config.DOOR_OPEN` oder :data:`config.DOOR_CLOSED`

        .. seealso::
            :meth:`sunrise.GetNextActions`
        """
        self.logger.debug("Received next actions list: %s", actions)
        if actions != self.next_actions:
            # wenn sich nichts geändert hat, machen wir auch nichts
            # ansonsten merken und den State-Setter rufen
            # (der setzt dann den Status entsprechend)
            self.next_actions = actions
            self._UpdateBoardState()

    def SwitchIndoorLight(self, swon:bool) -> bool:
        """
        Schaltet die Innenbeleuchtung in Abhängigkeit von ``swon`` (``True`` = an).
        Liefert den Wert von ``swon`` zurück.

        .. seealso::
            :meth:`board.Board.SwitchIndoorLight`
            :meth:`IsIndoorLightOn`
            :meth:`SwitchOutdoorLight`
        """
        self.debug("Received indoor light switch to %r request.", swon)
        self.board.SwitchIndoorLight(swon)
        return swon

    def SwitchOutdoorLight(self, swon:bool)->bool:
        """
        Schaltet die Außenbeleuchtung in Abhängigkeit von ``swon`` (``True`` = an).
        Liefert den Wert von ``swon`` zurück.

        .. seealso::
            :meth:`board.Board.SwitchOutdoorLight`
            :meth:`IsOutdoorLightOn`
            :meth:`SwitchIndoorLight`
        """
        self.debug("Received outdoor light switch to %r request.", swon)
        self.board.SwitchOutdoorLight(swon)
        return swon

    def IsIndoorLightOn(self)->bool:
        """
        Gibt zurück, ob die Innenbeleuchtung an ist.
        """
        return self.board.IsIndoorLightOn()

    def IsOutdoorLightOn(self)->bool:
        """
        Gibt zurück, ob die Außenbeleuchtung an ist.
        """
        return self.board.IsOutdoorLightOn()

    def _CloseDoorFromTimer(self):
        self.info("Timer requests door to close.")
        return self.board.CloseDoor()

    def _OpenDoorFromTimer(self):
        self.info("Timer requests door to open.")
        return self.board.OpenDoor()

    def CloseDoor(self)->bool:
        """
        Deaktiviert die Türautomatik vorübergehend und schließt die Tür.

        :returns: Ob die Tür geschlossen wurde.

        .. warning:: Der Rückgabewert bedeutet nicht, ob die Tür geschlossen ist.
            Er kann auch dann ``False`` sein, wenn das Kommando abgesetzt wurde
            obwohl die Tür bereits geschlossen war.

        .. seealso::
            :meth:`DisableAutomatic`
            :meth:`EnableAutomatic`
            :meth:`board.Board.IsDoorClosed`
            :meth:`board.Board.CloseDoor`
        """
        self.info("Received CloseDoor request.")
        self.DisableAutomatic()
        return self.board.CloseDoor()

    def OpenDoor(self) -> bool:
        """
        Deaktiviert die Türautomatik vorübergehend und öffnet die Tür.

        :returns: Ob die Tür geöffnet wurde.

        .. warning:: Der Rückgabewert bedeutet nicht, ob die Tür geöffnet ist.
            Er kann auch dann ``False`` sein, wenn das Kommando abgesetzt wurde
            obwohl die Tür bereits geöffnet war.

        .. seealso::
            :meth:`DisableAutomatic`
            :meth:`EnableAutomatic`
            :meth:`board.Board.IsDoorOpen`
            :meth:`board.Board.OpenDoor`
        """
        self.info("Received OpenDoor request.")
        self.DisableAutomatic()
        return self.board.OpenDoor()

    def StopDoor(self):
        """
        Deaktiviert die Türautomatik vorübergehend und stoppt die Türbewegung,
        falls aktuell eine stattfindet.

        .. seealso::
            :meth:`DisableAutomatic`
            :meth:`EnableAutomatic`
            :meth:`board.Board.StopDoor`
        """
        self.debug("Received StopDoor request.")
        self.board.StopDoor()
        self.DisableAutomatic()

    def IsDoorOpen(self)->bool:
        """
        Gibt zurück, ob die Tür offen ist (siehe :meth:`board.Board.IsDoorOpen`).
        """
        return self.board.IsDoorOpen()

    def IsDoorClosed(self) -> bool:
        """
        Gibt zurück, ob die Tür geschlossen ist (siehe :meth:`board.Board.IsDoorClosed`).
        """
        return self.board.IsDoorClosed()

    def SwitchDoorAutomatic(self, new_state:int)->int:
        """
        Schaltet die Türautomatik in den Status ``new_state`` und liefert
        den neuen Status zurück.

        :param int new_state: einer der Werte aus:
          - :data:`config.DOOR_AUTO_ON`
          - :data:`config.DOOR_AUTO_OFF`
          - :data:`config.DOOR_AUTO_DEACTIVATED`

        .. seealso::
            :meth:`EnableAutomatic`
            :meth:`DisableAutomatic`
        """
        self.debug("Switching door automatic to %d.", new_state)
        if new_state == 1:
            self.EnableAutomatic()
        else:
            self.DisableAutomatic(new_state == -1)
        return self.automatic

    def _AddStateInfo(self, state:dict):
        """
        Reichert das Status-Dictionary ``state`` inline um die folgenden Werte an:
          - :attr:`next_actions`
          - :attr:`automatic`
          - :attr:`automatic_enable_time`
          - :attr:`temperature`
          - :attr:`light_sensor`

        Die Werte werden dabei mit ihrem Attributnamen als Schlüssel hinterlegt.

        .. seealso::
            :meth:`GetBoardState`
        """
        state.update(
            next_actions = self.next_actions,
            automatic = self.automatic,
            automatic_enable_time = self.automatic_enable_time,
            temperature = self.temperature,
            light_sensor = self.light_sensor
        )

    def GetBoardState(self)->dict:
        """
        Liefert den aktuellen Status des :class:`board<board.Board>` angereichert
        um die Informationen aus :meth:`_AddStateInfo` als Dictionary zurück.

        .. seealso::
            :meth:`board.Board.GetState`
        """
        self.debug("Received state request.")
        state = self.board.GetState()
        self._AddStateInfo(state)
        return state

    def _UpdateBoardState(self):
        """
        Wird innerhalb dieser Instanz gerufen um zu signalisieren,
        dass sich an einem der Zustände etwas geändert hat.
        Hierbei kann es sich nur um einen der Werte handeln, die
        bei :meth:`_AddStateInfo` hinzugefügt werden.

        .. seealso::
            :meth:`board.Board.GetState`
        """
        state = self.board.GetState()
        self._BoardStateChanged(state)

    def _BoardStateChanged(self, state: dict):
        """
        Handler für Änderungen am Status des Boards.
        Reichert den Board-Status mit Daten aus :meth:`_AddStateInfo` an.
        Wird entweder über die :attr:`board`-Instanz direkt bei dort
        getriggerten Änderungen oder via :meth:`_UpdateBoardState` aufgerufen.
        Benachrichtig die Status-Condition, so das in :meth:`WaitForStateChange`
        wartende Threads weiterarbeiten können.
        """
        self._AddStateInfo(state)
        self.debug("Board state changed: %s", state)
        with self._state_lock:
            self._state = (True, state)
            self._state_cond.notify_all()

    def WaitForStateChange(self, waittime:float = 30.0)->tuple:
        """
        Hängt den aufrufenden Thread an die nächste Statusänderung.
        Diese Methode kehrt erst dann zurück, wenn über :meth:`_BoardStateChanged`
        der Status geändert wurde oder das in ``waittime`` (Sekunden) gesetzte Timeout
        erreicht wurde.

        :returns: Ein Tuple aus zwei Werten. Der erste ist ein ``bool`` das angibt, ob in der
            Wartezeit eine Statusänderung getriggert wurde und der zweite das Status-
            Dictionary wie in :meth:`GetBoardState` zurückgeliefert.
        """
        with self._state_lock:
            self._state_cond.wait(timeout = waittime)
            notified, state = self._state
            if notified:
                self._state = (False, state)
        return (notified, state)

    def GetNextAction(self)->tuple:
        """
        Liefert ein Tuple mit dem Zeitpunkt der nächsten Aktion als ``datetime`` und der Aktion
        selbst zurück.
        Die Aktion ist dabei entweder :data:`config.DOOR_OPEN` oder :data:`config.DOOR_CLOSED`.

        .. seealso::
            :meth:`SetNextActions`
        """
        dtnow = datetime.datetime.now()
        for dt, action in self.next_actions:
            if dtnow < dt:
                return (dt, action)
        return (None, None)

    def DisableAutomatic(self, forever:bool = False):
        """
        Deaktiviert die Tür-Automatik für die in :data:`config.DOOR_AUTOMATIC_OFFTIME`
        gesetzte Anzahl von Sekunden.

        :param bool forever: Gibt an, ob die Automatic dauerhaft deaktiviert werden soll.

        .. warning:: Wenn diese Methode mit bereits dauerhaft deaktivierter Automatik
            gerufen wird, bleibt die Automatik dauerhaft deaktiviert, egal wie ``forever``
            belegt ist.
        """
        if self.automatic == DOOR_AUTO_DEACTIVATED:
            return

        if forever:
            self.automatic = DOOR_AUTO_DEACTIVATED
            self.warn("Door automatic disabled.")
        else:
            # nur wenn die Automatik nicht bereits dauerhaft deaktiviert war,
            # stellen wir hier eine zeitbegrenzte Automatik ein
            self.automatic_enable_time = time.time() + DOOR_AUTOMATIC_OFFTIME
            self.automatic = DOOR_AUTO_OFF
            self.info(
                "Door automatic disabled for the next %.2f seconds", float(DOOR_AUTOMATIC_OFFTIME)
            )

        self._UpdateBoardState()

    def EnableAutomatic(self):
        """
        Aktiviert die Türautomatik (wieder).
        """
        if self.automatic == DOOR_AUTO_ON:
            return
        self.automatic = DOOR_AUTO_ON
        self.automatic_enable_time = -1
        self.info("Door automatic has been enabled.")
        self._UpdateBoardState()
        self.job_timer.WakeUp()

    def CleanUp(self):
        """
        Räumt die Instanz auf und hält den :class:`JobTimer` synchron an.
        """
        self.job_timer.Terminate()
        self.job_timer.Join(6.0)
        self.job_timer = None

    def _ReadSensors(self):
        """
        Wird im Intervall :data:`config.SENSOR_INTERVAL` vom :class:`JobTimer` aufgerufen und
        hinterlegt die Messergebnisse der angebundenen Sensoren und
        aktualisiert den Board-Status.
        """
        self.temperature = self.board.GetTemperature()
        self.light_sensor = self.board.GetLight()
        self.info(
            "Measured sensors. Light = %d, temperature = %.1f",
            self.light_sensor, self.temperature
        )
        self._UpdateBoardState()
        try:
            with self.sensor_file.open('w') as f:
                f.write(SENSOR_LINE_TPL % (self.light_sensor, self.temperature))
        except Exception:
            self.exception("Error while writing to %s", self.sensor_file)
# ------------------------------------------------------------------------
class DataServer(socketserver.ThreadingMixIn, xmlrpc.server.SimpleXMLRPCServer):
    """
    SimpleXMLRPC-Server, jeder Request wird in einem eigenen Thread ausgeführt.
    """
    def __init__(self, *args, **kwargs):
        #: Instanz des Loggers.
        self.logger = shared.getLogger("xmlrpc-server")
        super().__init__(*args, **kwargs)

    def _dispatch(self, method, params):
        """
        Überlädt die Basisklassenmethode um etwaige Exceptions
        im :attr:`logger` auszugeben.
        """
        try:
            return super()._dispatch(method, params)
        except Exception:
            self.logger.exception("Error in %s%r.", method, params)
            raise
# ------------------------------------------------------------------------
def Main():
    """
    Initialisiert das Logging und den Controller und startet diesen.
    Ausführung bis CTRL-C oder `kill -INT <PID>`.
    """
    logger = shared.getLogger("controller")
    address = ("", CONTROLLER_PORT)
    logger.info("Starting XML-RPC-Server as %r, pid = %s", address, os.getpid())
    try:
        try:
            controller = Controller()
        except Exception:
            logger.exception("Error during initialization, stopped.")
            return

        try:
            ds = DataServer(address, allow_none = True)
            ds.register_instance(controller)
            logger.debug("Start serving.")
            ds.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutdown due to keyboardinterrupt.")
        except Exception:
            logger.exception("Unhandled error, stopped.")
        finally:
            controller.CleanUp()
    finally:
        logger.info("Finished.")
        shared.logging.shutdown()
# ------------------------------------------------------------------------
if __name__ == "__main__":
    Main()

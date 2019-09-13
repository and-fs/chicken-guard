#! /usr/bin/python3
# -*- coding: utf8 -*-
"""
Dieses Script stellt unter dem Port :data:`config.CAM_PORT` einen HTTP-Server
zur Verfügung, der das Bild der angeschlossenen Kamera überträgt.

Logging
-------

Das Logging erfolgt nach *server*.

Restriktionen
-------------

Die Auflösung ist auf :data:`config.CAM_WIDTH` x  :data:`config.CAM_HEIGHT` Bildpunkte
begrenzt, die maximale Framerate beträgt :data:`config.CAM_FRAMERATE`.

Da die Ressourcen des verwendeten *PiZero* knapp sind, werden auch die Zeit für das Streaming
auf :data:`config.MAX_STREAM_TIME` Sekunden beschränkt, ausserdem sind nicht mehr als
:data:`config.MAX_STREAM_COUNT` parallele Zugriffe erlaubt.
Falls diese Restriktionen greifen, wird ein 503-Response ausgeliefert (mit entsprechender Meldung)

Achtung!
--------

Falls ``PiCamera`` aus dem ``picamera``-Modul nicht importiert werden kann, wird eine
Mockup-Klasse erzeugt, die nacheinander die Bilder im Ordner */pics* unterhalb des
:data:`resource_path` mit dem Pattern ``<nr>.jpg``  (also *0.jpg*, *1.jpg* u.s.w) statt des
Kamerabildes ausliefert. Nur zum Testen!

Klassen und Funktionen
----------------------
"""
# --------------------------------------------------------------------------------------------------
# pylint: disable=C0103,R0903
# --------------------------------------------------------------------------------------------------
import io
import socketserver
import time
from threading import Condition, RLock
from http import server
# --------------------------------------------------------------------------------------------------
from config import * # pylint: disable=W0614
from shared import LoggableClass, getLogger, resource_path
# --------------------------------------------------------------------------------------------------
#: Tuple aus (:data:`config.CAM_WIDTH`, :data:`config.CAM_HEIGHT`).
RESOLUTION = (CAM_WIDTH, CAM_HEIGHT)
# --------------------------------------------------------------------------------------------------
try:
    from picamera import PiCamera
except ImportError:
    from threading import Thread
    class PiCamera(LoggableClass):
        """
        Test-Mockup für PiCamera.
        """
        # pylint: disable=W0613,C0111,W0622
        def __init__(self, resolution = RESOLUTION, framerate = CAM_FRAMERATE):
            super().__init__(name = "PiCamDummy")
            self.framerate = framerate
            self.resolution = resolution
            self.output = None
            self._terminate = False
            self._recording = False
            self._img_path = resource_path / 'pics'
            self._waiter = Condition()
            self._thread = Thread(target = self._ThreadLoop, name = "camera")
            self._thread.start()

        def start_recording(
                self, output,
                format = None, resize = None, splitter_port = 1, **options):
            self.info("Starting recording to %r, format = %r", output, format)
            self.output = output
            self._recording = True
            with self._waiter:
                self._waiter.notify_all()

        def stop_recording(self):
            self._recording = False
            with self._waiter:
                self._waiter.notify_all()
            self.info("Recording stopped.")

        def close(self):
            self.info("Camera closed.")
            self._terminate = True
            with self._waiter:
                self._waiter.notify_all()
            self._thread.join()

        def _ThreadLoop(self):
            self.info("Camera thread started.")

            img_num = 0
            frame_time = 1.0 / float(self.framerate)
            while not self._terminate:
                loop_t = time.time()
                if self._recording:
                    p = self._img_path / (str(img_num) + '.jpg')
                    img_num += 1
                    if img_num == 10:
                        img_num = 0
                    with p.open('rb') as f:
                        self.output.write(f.read())
                if self._terminate:
                    break
                sleep_time = frame_time - (time.time() - loop_t)
                with self._waiter:
                    self._waiter.wait(sleep_time)

            self.info("Camera thread stopped.")
# --------------------------------------------------------------------------------------------------
#: Template für die HTML-Seite die ausgeliefert wird, wenn
#: im WebServer eine Root-Anfrage (also ohne Pfad) stattfindet.
PAGE = """\
<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <title>H&uuml;hner-Kamera mit {CAM_FRAMERATE} f/s</title>
  </head>
  <body>
    <h1>H&uuml;hner-Kamera ({CAM_FRAMERATE} Bilder pro Sekunde)</h1>
    <img src="stream.mjpg" width="{CAM_WIDTH}" height="{CAM_HEIGHT}" />
  </body>
</html>
""".format(**globals())
# --------------------------------------------------------------------------------------------------
class StreamingOutput:
    """
    File-like-proxy für die Aufnahme des Kamerabildes in einen Buffer
    und signalisierung wartender Threads auf Vorhandensein eines neuen
    Bildes.
    """
    def __init__(self):

        #: Enthält den jeweils aktuellen Frame der Kamera nach Benachrichtung der :attr:`condition`.
        #: Darf nur im Kontext der :attr:`condition` abgefragt werden!
        self.frame = None

        #: Binärer Zwischenbuffer, der die einzelnen Frames der Kamera in :meth:`write` entgegen-
        #: nimmt. Wenn ein vollständiges Bild empfangen wurde, wird der Frame in :attr:`frame``
        #: zwischengespeichert und die :attr:`conditon` benachrichtigt.
        self.buffer = io.BytesIO()

        #: Condition zu Synchronisierung des Zugriffs auf den :attr:`frame`.
        self.condition = Condition()

    def write(self, buf:bytes)->int:
        """
        Diese Methode nimmt die Binärdaten aus ``buf`` entgegen und
        speichert diese in einem Buffer zwischen. Sobald ein neues Bild beginnt,
        wird der Inhalt des Buffers in das Attribut :attr:`frame` übertragen und die
        Condition :attr:`condition` benachrichtigt, so dass alle wartenden Threads nach
        Erhalt der Benachrichtung das Bild aus :attr:`frame` abrufen können.
        Der Zugriff auf :attr:`frame` muss immer im Kontext der :attr:`condition` stattfinden!

        :returns: Die Anzahl der in den Buffer übertragenen Bytes.
        """
        if buf[:2] == b'\xff\xd8':
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)
# --------------------------------------------------------------------------------------------------
class Camera(LoggableClass):
    """
    Wrapper für den Zugriff auf die Kamera aus verschiedenen Threads zur möglichst ressourcen-
    schonenden Verteilung des Kamerabildes auf mehrere Requests.

    Diese Instanz sollte ein Singleton sein und als Kontext verwendet werden, damit die
    Verwaltung der Ressourcen korrekt funktioniert:

    .. code-block:: python

        camera = Camera()                  # Kamera anlegen
        assert camera.counter == 0
        with camera as output:             # Akquirieren und StreamingOutput holen
            assert camera.counter == 1
            condition = output.condition   # Condition aus output referenzieren
            for i in range(10):            # die nächsten 10 Bilder holen
                with condition:            # Über die condition Sperren
                    condition.wait()       # Auf den nächsten Frame warten (entsperrt)
                    frame = output.frame   # Frame holen (im Sperrkontext der condition)
                pass                       # ab hier ist die Condition wieder ensperrt
        assert camera.counter == 0.0       # ab hier ist die Kamera wieder deaktiviert (da nur
                                           # eine Instanz zugreift)
    """
    def __init__(self):
        LoggableClass.__init__(self, name = "camera")

        #: Reentrater Lock zur Synchronisierung des Zugriffs auf die Attribute:
        #:  - :attr:`camera`
        #:  - :attr:`output`
        #:  - :attr:`counter`
        self._lock = RLock()

        #: Verweis auf die :class:`PiCamera`-Instanz zur Aufnahme der Bilder.
        self.camera = None

        #: :class:`StreamingOutput` Instanz, die als Recorder an die :attr:`camera` übergeben und
        #: zur Abnahme der Bilder für die Streamingclients verwendet wird.
        self.output = None

        #: Zähler für die Anzahl angemeldeter Streamingclients. 0 = Kamera aus, > 0 = Kamera an.
        self.counter = 0

    def __enter__(self):
        try:
            self._AcquireCamera()
        except Exception:
            self.exception("Error while acquiring camera.")
            raise

        return self.output

    def __exit__(self, *exc_info):
        if exc_info:
            exc_type = exc_info[0]
            if exc_type not in (None, ConnectionAbortedError, TimeoutError, BrokenPipeError):
                self.error("Exception in camera context.", exc_info = exc_info)

        try:
            self._ReleaseCamera()
        except Exception:
            self.exception("Error while releasing camera.")
            raise

    def _AcquireCamera(self):
        with self._lock:
            self.counter += 1
            self.debug("Acquired camera, counter: %d", self.counter)
            if self.counter == 1:
                self.counter = 1
                self.camera = PiCamera(resolution = RESOLUTION, framerate = CAM_FRAMERATE)
                self.output = StreamingOutput()
                self.camera.start_recording(self.output, format = 'mjpeg')
                self.debug("Switched camera on.")
            return self.camera

    def _ReleaseCamera(self):
        with self._lock:
            self.counter -= 1
            self.debug("Released camera, counter: %d", self.counter)
            if self.counter == 0:
                self.camera.stop_recording()
                self.camera.close()
                self.camera = None
                self.output = None
                self.debug("Switched camera off.")

    def CleanUp(self):
        """
        Räumt die Instanz auf.
        Im Gegensatz zu :meth:`_ReleaseCamera` wird hier der Counter nicht heruntergezählt
        sondern die Kamera und alle Ressourcen freigegeben, wenn diese noch akquiriert waren.
        Nach dem Aufruf ist der Counter == 0, die Kamera ist deaktiviert und gelöscht, genauso
        wie der Output.
        """
        with self._lock:
            if self.counter > 0:
                self.camera.stop_recording()
                self.camera.close()
                self.camera = None
                self.output = None
                self.counter = 0
                self.debug("Switched camera off due to cleanup.")
# --------------------------------------------------------------------------------------------------
#: Singleton-Instanz der Kamera.
camera = Camera()
# --------------------------------------------------------------------------------------------------
class StreamingHandler(server.BaseHTTPRequestHandler):
    """
    Handler für GET-Requests an den :class:`StreamingServer`.
    """
    def do_GET(self):
        """
        Wird gerufen, um ein GET-Request zu behandeln.
        In Abhängigkeit des Request-Pfades werden hier entsprechende Aktionen getriggert:

            - ``/`` (kein Pfad): Weiterleitung nach ``/index.html`` (301)
            - ``/index.html``: Ausgabe von :data:`PAGE` (Standard-HTML-Seite mit einem Bild
                               das ``/stream.mjpg`` lädt)
            - ``/stream.mjpg``: Ausgabe des Kamerastreams. Siehe den Abschnitt *Restriktionen*
                                weiter oben.

        In allen anderen Fällen wird ein 404-Response ausgegeben.
        """
        name = '%s:%s' % self.client_address
        logger = getLogger(name)
        logger.debug("Handling request: %r", self.path)
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            if camera.counter >= MAX_STREAM_COUNT:
                self.send_error(
                    503,
                    message = "Maximum stream count reached.",
                    explain = "Server is limited to a maximum of %d "
                              "parallel streams which has been reached now." % (MAX_STREAM_COUNT,)
                )
                return

            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()

            try:
                end_time = time.time() + MAX_STREAM_TIME
                logger.info("Started streaming")
                with camera as output:
                    while end_time > time.time():
                        with output.condition:
                            if not output.condition.wait(20.0):
                                logger.warning("Condition not notified in time.")
                                raise TimeoutError("Camera timeout.")
                            frame = output.frame
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                logger.info("Stream reached timeout, stopped.")
                self.wfile.write(b'--FRAME\r\n')
                self.send_error(
                    503,
                    message = "Stream timeout reached",
                    explain = "Stream has a time limit of %.0f "
                              "seconds which exceeded." % (MAX_STREAM_TIME,))
                self.end_headers()
            except Exception as e:
                logger.info("Disconnected, stopped streaming (%s).", e)
        else:
            self.send_error(404, message = "Invalid path %r" % (self.path,))
            self.end_headers()
# --------------------------------------------------------------------------------------------------
class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    """
    Server für threaded HTTP-Requests.
    """
    allow_reuse_address = False
    daemon_threads = True
# --------------------------------------------------------------------------------------------------
def Main():
    """
    Startet den Streamingserver öffentlich erreichbar mit dem Port :data:`config.CAM_PORT`.
    Die Methode beendet sich erst durch Beenden des Servers resp. ein ``SIGINT``.
    """
    logger = getLogger(name = "server")

    logger.info(
        "Starting using port %d. Max streams = %d, timeout per stream = %.2f secs.",
        CAM_PORT, MAX_STREAM_COUNT, MAX_STREAM_TIME
    )

    try:
        StreamingServer(('', CAM_PORT), StreamingHandler).serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped due to keyboard interrupt.")
    except Exception:
        logger.exception("Unhandled error, abort.")
    finally:
        camera.CleanUp()
# --------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    Main()
# --------------------------------------------------------------------------------------------------
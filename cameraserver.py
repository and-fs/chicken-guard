#! /usr/bin/python3
# -*- coding: utf8 -*-
# ------------------------------------------------------------------------
import io
import socketserver
import time
from threading import Condition, RLock
from http import server
# ------------------------------------------------------------------------
from config import * # pylint: disable=W0614
from shared import LoggableClass, getLogger, resource_path
# ------------------------------------------------------------------------
RESOLUTION = (CAM_WIDTH, CAM_HEIGHT)
# ------------------------------------------------------------------------
try:
    from picamera import PiCamera
except ImportError:
    from threading import Thread
    import pathlib
    class PiCamera(LoggableClass):
        """
        Test-Mockup für PiCamera.
        """
        def __init__(self, resolution = RESOLUTION, framerate = CAM_FRAMERATE):
            super().__init__(name = "PiCamDummy")
            self.framerate = framerate
            self.resolution = resolution
            self._terminate = False
            self._recording = False
            self._img_path = resource_path / 'pics'
            self._waiter = Condition()
            self._thread = Thread(target = self._ThreadLoop, name = "camera")
            self._thread.start()

        def start_recording(self, output, format = None, resize = None, splitter_port = 1, **options):
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
# ------------------------------------------------------------------------
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
# ------------------------------------------------------------------------
class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf[:2] == b'\xff\xd8':
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)
# ------------------------------------------------------------------------
class Camera(LoggableClass):
    def __init__(self):
        LoggableClass.__init__(self, name = "camera")
        self._lock = RLock()
        self.camera = None
        self.output = None
        self.counter = 0
    
    def __enter__(self):
        try:
            self.acquireCamera()
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
            self.releaseCamera()
        except Exception:
            self.exception("Error while releasing camera.")
            raise

    def acquireCamera(self):
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

    def releaseCamera(self):
        with self._lock:
            self.counter -= 1
            self.debug("Released camera, counter: %d", self.counter)
            if self.counter == 0:
                self.camera.stop_recording()
                self.camera.close()
                self.camera = None
                self.output = None
                self.debug("Switched camera off.")

    def cleanUp(self):
        with self._lock:
            if self.counter > 0:
                self.camera.stop_recording()
                self.camera.close()
                self.camera = None
                self.output = None
                self.counter = 0
                self.debug("Switched camera off due to cleanup.")
# ------------------------------------------------------------------------
camera = Camera()
# ------------------------------------------------------------------------
class StreamingHandler(server.BaseHTTPRequestHandler):

    def do_GET(self):
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
                self.send_error(503,
                    message = "Maximum stream count reached.",
                    explain = "Server is limited to a maximum of %d parallel streams which has been reached now." % (MAX_STREAM_COUNT,)
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
                                logger.warn("Condition not notified in time.")
                                raise TimeoutError("Camera timeout.")
                            frame = output.frame
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                    else:
                        logger.info("Stream reached timeout, stopped.")
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_error(503,
                            message = "Stream timeout reached",
                            explain = "Stream has a time limit of %.0f seconds which exceeded." % (MAX_STREAM_TIME,))
                        self.end_headers()
            except Exception as e:
                logger.info("Disconnected, stopped streaming (%s).", e)
        else:
            self.send_error(404, message = "Invalid path %r" % (self.path,))
            self.end_headers()
# ------------------------------------------------------------------------
class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = False
    daemon_threads = True
# ------------------------------------------------------------------------
def main():
    logger = getLogger(name = "server")
    logger.info("Starting using port %d. Max streams = %d, timeout per stream = %.2f secs.", 
        CAM_PORT, MAX_STREAM_COUNT, MAX_STREAM_TIME)
    try:
        address = ('', CAM_PORT)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped due to keyboard interrupt.")
    except Exception:
        logger.exception("Unhandled error, abort.")
    finally:
        camera.cleanUp()
# ------------------------------------------------------------------------
if __name__ == '__main__':
    main()
# ------------------------------------------------------------------------
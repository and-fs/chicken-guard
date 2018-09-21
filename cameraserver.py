#! /usr/bin/python3
# -*- coding: utf8 -*-
# ------------------------------------------------------------------------
import io
import picamera
import logging
import socketserver
from threading import Condition
from http import server
# ------------------------------------------------------------------------
WIDTH = 640
HEIGHT = 480
FRAMERATE = 10
PORT = 8000
# ------------------------------------------------------------------------
logging.basicConfig(
    filename = '/usr/www/log/cameraserver.log',
    filemode = 'w',
    format = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
    datefmt = '%m-%d %H:%M:%S',
    level = logging.DEBUG    
)
# ------------------------------------------------------------------------
PAGE = """\
<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <title>H&uuml;hner-Kamera mit {FRAMERATE} f/s</title>
  </head>
  <body>
    <h1>H&uuml;hner-Kamera ({FRAMERATE} Bilder pro Sekunde)</h1>
    <img src="stream.mjpg" width="{WIDTH}" height="{HEIGHT}" />
  </body>
</html>
""".format(**globals())
# ------------------------------------------------------------------------
RESOLUTION = "{WIDTH}x{HEIGHT}".format(**globals())
# ------------------------------------------------------------------------
class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)
# ------------------------------------------------------------------------
class Camera(object):
    def __init__(self):    
        self.camera = None
        self.output = None
        self.counter = 0
    
    def __enter__(self):
        self.acquireCamera()
        logging.debug("Acquired camera, counter: %d", self.counter)
        return self.output

    def __exit__(self, *x):
        self.releaseCamera()
        logging.debug("Released camera, counter: %d", self.counter)

    def acquireCamera(self):
        self.counter += 1
        if self.counter == 1:
            self.counter = 1
            self.camera = picamera.PiCamera(resolution = RESOLUTION, framerate = FRAMERATE)
            self.output = StreamingOutput()
            self.camera.start_recording(self.output, format = 'mjpeg')
            logging.debug("Switched camera on.")
        return self.camera

    def releaseCamera(self):
        self.counter -= 1
        if self.counter == 0:
            self.camera.stop_recording()
            self.camera.close()
            self.camera = None
            self.output = None
            logging.debug("Switched camera off.")

    def cleanUp(self):
        if self.counter > 0:
            self.camera.stop_recording()
            self.camera.close()
            self.camera = None
            self.output = None
            self.counter = 0
            logging.debug("Switched camera off due to cleanup.")
# ------------------------------------------------------------------------
camera = Camera()            
# ------------------------------------------------------------------------
class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
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
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()

            try:
                logging.info("Streaming camera to client %s.",
                             self.client_address)
                with camera as output:
                    while True:
                        with output.condition:
                            output.condition.wait()
                            frame = output.frame
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')            
            except Exception as e:
                logging.info("Client %s disconnected, stopped streaming (%s).",
                             self.client_address, e)
        else:
            self.send_error(404)
            self.end_headers()
# ------------------------------------------------------------------------
class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
# ------------------------------------------------------------------------
def main():
    try:
        address = ('', PORT)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Stopped due to keyboard interrupt.")
    except Exception:
        logging.exception("Unhandled error, abort.")
    finally:
        camera.cleanUp()
# ------------------------------------------------------------------------
if __name__ == '__main__':
    main()
# ------------------------------------------------------------------------
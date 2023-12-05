#!/usr/bin/python3

import io
import logging
import socketserver

import time
import cv2

from picamera2          import MappedArray, Picamera2, Preview
from picamera2.encoders import JpegEncoder, H264Encoder
from picamera2.outputs  import FileOutput
from http               import server
from threading          import Condition
from urllib.parse       import parse_qs

PAGE = """\
<!DOCTYPE html>
<html>
    <head>
        <title>Camera streaming</title>
        <style>
            .square {
                height: 50px;
                width: 50px;
                background-color: #555;
            }
            .thumbnail {
                position: relative;
                width: 700px;
                height: 500px;
                overflow: hidden;
            }
            .thumbnail img {
                position: absolute;
                left: 50%;
                top: 50%;
                height: 100%;
                width: auto;
                -webkit-transform: translate(-50%,-50%);
                    -ms-transform: translate(-50%,-50%);
                        transform: translate(-50%,-50%);
            }
            .thumbnail img.portrait {
                width: 100%;
                height: auto;
            }
        </style>
    </head>
    <body>
        <center>
            <h1>Camera Streaming</h1>
            
            <button type = "button" name = "button1" style="width: 80px; height:50px;" onclick="submitForm('1')">
                <b>Original</b>
            </button>
            
            <button type = "button" name = "button2" style = "width: 80px; height:50px;" onclick="submitForm('2')">
                <b>x2</b>
            </button>
            
            <button type = "button" name = "button3" style = "width: 80px; height:50px;" onclick="submitForm('3')">
                <b>x3</b>
            </button>
            
            <button type = "button" name = "button4" style = "width: 80px; height:50px;" onclick="submitForm('4')">
                <b>x4</b>
            </button>
            
            <button type = "button" name = "button5" style = "width: 80px; height:50px;" onclick="submitForm('5')">
                <b>x5</b>
            </button><br><br>

            <script>
                function submitForm(value) {
                    var xhr = new XMLHttpRequest();
                    xhr.open("POST", "/handle_button_click", true);
                    xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
                    xhr.send("button_value=" + value);
                }
            </script>
            <div class="thumbnail">
                <img src="stream.mjpg" alt="Image"/>
            </div>
        </center>
    </body>
</html>
"""

def set_zoom(camera, zoom_factor):
    # Отримуємо повний розмір матриці пікселів
    full_res = camera.camera_properties['PixelArraySize']
    
    # Обчислюємо новий розмір області "ScalerCrop" на основі зум-фактора
    new_size = [int(s / zoom_factor) for s in full_res]
    
    # Обчислюємо відступ, щоб зображення залишалося по центру
    offset = [(r - s) // 2 for r, s in zip(full_res, new_size)]
    
    # Встановлюємо нові значення "ScalerCrop"
    camera.set_controls({"ScalerCrop": offset + new_size})

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

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
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
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
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')

        # -- Розбираємо дані POST-запиту
        post_params = parse_qs(post_data)
        button_value = post_params.get('button_value', [''])[0]
        t = {button_value}

        # -- Код обробки значення
        if t == {'1'}:
            set_zoom(picam2, 1)
        elif t == {'2'}:
            set_zoom(picam2, 2)
        elif t == {'3'}:
            set_zoom(picam2, 3)
        elif t == {'4'}:
            set_zoom(picam2, 4)
        elif t == {'5'}:
            set_zoom(picam2, 5)
        # Відправляємо відповідь клієнту
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes(PAGE, 'utf-8'))

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (1920, 1080)}))

output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))

# -- Таймер
colour      = (0, 0, 0)
origin      = (230, 55)
font        = cv2.FONT_HERSHEY_SIMPLEX
scale       = 2
thickness   = 2

size = picam2.capture_metadata()['ScalerCrop'][2:]

full_res = picam2.camera_properties['PixelArraySize']

# -- Виводмо час та хрест
def apply_timestamp(request):
    timestamp = time.strftime("%Y-%m-%d %X")
    with MappedArray(request, "main") as m:
        cv2.putText (m.array, timestamp, origin, font, scale, colour, thickness)
        # cv2.line  (m.array, (320, 210), (320, 270), (255, 255, 255), 1) # -- горизонтальна
        # cv2.line  (m.array, (350, 240), (290, 240), (255, 255, 255), 1) # -- вертикальна

picam2.pre_callback = apply_timestamp

try:
    address = ('', 8000)
    server = StreamingServer(address, StreamingHandler)
    server.serve_forever()
finally:
    picam2.stop_recording()
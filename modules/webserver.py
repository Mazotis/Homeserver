#!/usr/bin/env python3
'''
    File name: webserver.py
    Author: Maxime Bergeron
    Date last modified: 22/08/2019
    Python Version: 3.5

    The web server interface module for the lightserver
'''

import requests
import socket
import socketserver
import urllib.parse
from devices.common import *
from functools import partial
from http.server import SimpleHTTPRequestHandler, HTTPServer
from io import BytesIO
from threading import Thread

class WebServerHandler(SimpleHTTPRequestHandler):
    def __init__(self, lmhost, lmport, *args, **kwargs):
        self.lmhost = lmhost
        self.lmport = lmport
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        return SimpleHTTPRequestHandler.translate_path(self, './web' + path)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        postvars = urllib.parse.parse_qs(self.rfile.read(content_length), keep_blank_values=1)
        request = bool(postvars[b'request'][0].decode('utf-8'))
        reqtype = int(postvars[b'reqtype'][0].decode('utf-8'))
        self._set_response()
        response = BytesIO()
        if request:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.lmhost, self.lmport))
            if reqtype == 1:
                try:
                    s.sendall("0008".encode('utf-8'))
                    s.sendall("getstate".encode('utf-8'))
                    data = s.recv(2048)
                    if data:
                        response.write(data)
                finally:
                    s.close()
            if reqtype == 2:
                devid = str(postvars[b'devid'][0].decode('utf-8'))
                value = str(postvars[b'value'][0].decode('utf-8'))
                skiptime = postvars[b'skiptime'][0].decode('utf-8') in ['true', True]
                try:
                    s.sendall("0008".encode('utf-8'))
                    s.sendall("setstate".encode('utf-8'))
                    s.sendall(devid.zfill(3).encode('utf-8'))
                    s.sendall(value.zfill(8).encode('utf-8'))
                    if skiptime:
                        s.sendall("1".encode('utf-8'))
                    else:
                        s.sendall("0".encode('utf-8'))
                    data = s.recv(1)
                    if data:
                        response.write(data)
                finally:
                    s.close()
            if reqtype == 3:
                cmode = postvars[b'mode'][0].decode('utf-8') in ['true', True]
                devid = str(postvars[b'devid'][0].decode('utf-8'))
                try:
                    s.sendall("0007".encode('utf-8'))
                    s.sendall("setmode".encode('utf-8'))
                    s.sendall(devid.zfill(3).encode('utf-8'))
                    if cmode:
                        s.sendall("1".encode('utf-8'))
                    else:
                        s.sendall("0".encode('utf-8'))
                    data = s.recv(1)
                    if data:
                        response.write(data)
                finally:
                    s.close()
            if reqtype == 4:
                group = str(postvars[b'group'][0].decode('utf-8'))
                value = str(postvars[b'value'][0].decode('utf-8'))
                skiptime = postvars[b'skiptime'][0].decode('utf-8') in ['true', True]
                try:
                    s.sendall("0008".encode('utf-8'))
                    s.sendall("setgroup".encode('utf-8'))
                    s.sendall(group.zfill(64).encode('utf-8'))
                    s.sendall(value.zfill(2).encode('utf-8'))
                    if skiptime:
                        s.sendall("1".encode('utf-8'))
                    else:
                        s.sendall("0".encode('utf-8'))
                    data = s.recv(1)
                    if data:
                        response.write(data)
                finally:
                    s.close()
            if reqtype == 5:
                try:
                    s.sendall("0012".encode('utf-8'))
                    s.sendall("getstatepost".encode('utf-8'))
                    data = s.recv(1024)
                    if data:
                        response.write(data)
                finally:
                    s.close()
            if reqtype == 6:
                try:
                    s.sendall("0010".encode('utf-8'))
                    s.sendall("setallmode".encode('utf-8'))
                    data = s.recv(1)
                    if data:
                        response.write(data)
                finally:
                    s.close()

        else:
            response.write("No request".encode("UTF-8"))
        self.wfile.write(response.getvalue())


class runWebServer(Thread):
    def __init__(self, port, config):
        Thread.__init__(self)
        self.port = port
        self.config = config
        self.running = True

    def run(self):
        debug.write("Starting control webserver on port {}".format(self.port), 0, "WEBSERVER")
        socketserver.TCPServer.allow_reuse_address = True
        _handler = partial(WebServerHandler, self.config['SERVER']['HOST'], int(self.config['SERVER'].getint('PORT')))
        httpd = socketserver.TCPServer(("", self.port), _handler)

        try:
            while self.running:
                httpd.handle_request()
        finally:
            httpd.server_close()
            debug.write("Stopped.", 0, "WEBSERVER")
            return

    def stop(self):
        debug.write("Stopping.", 0, "WEBSERVER")
        self.running = False
        # Needs a last call to shut down properly
        _r = requests.get("http://localhost:{}/".format(self.port))
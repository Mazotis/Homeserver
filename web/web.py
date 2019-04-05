#!/usr/bin/env python3
'''
    File name: web.py
    Author: Maxime Bergeron
    Date last modified: 05/04/2019
    Python Version: 3.7

    A python HTTP web interface for Lightserver
'''

import ast
import os
import socket
import socketserver
import sys
import time
import urllib
from http.server import SimpleHTTPRequestHandler
from io import BytesIO

PORT = int(sys.argv[1])
lmhost = sys.argv[2]
lmport = int(sys.argv[3])


class WebServerHandler(SimpleHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        postvars = urllib.parse.parse_qs(self.rfile.read(content_length), keep_blank_values=1)
        request = bool(postvars[b'request'][0].decode('utf-8'))
        reqtype = int(postvars[b'reqtype'][0].decode('utf-8'))
        self._set_response()
        response = BytesIO()
        if request:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((lmhost, lmport))
            if reqtype == 1:
                try:
                    s.sendall("0008".encode('utf-8'))
                    s.sendall("getstate".encode('utf-8'))
                    data = s.recv(1024)
                    if data:
                        response.write(data)
                finally:
                    s.close()
            if reqtype == 2:
                devid = str(postvars[b'devid'][0].decode('utf-8'))
                value = str(postvars[b'value'][0].decode('utf-8'))
                skiptime = postvars[b'skiptime'][0].decode('utf-8') in ['true', True]
                print(skiptime)
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
        else:
            response.write("No request".encode("UTF-8"))
        self.wfile.write(response.getvalue())


os.chdir("./web")

try:
    httpd = socketserver.TCPServer(("", PORT), WebServerHandler)
    httpd.serve_forever()
except KeyboardInterrupt:
    pass
except OSError as ex:
    print(ex)
    print("Webserver initialization failed...")
finally:    
    httpd.server_close()

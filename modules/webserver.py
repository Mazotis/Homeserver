#!/usr/bin/env python3
'''
    File name: webserver.py
    Author: Maxime Bergeron
    Date last modified: 10/10/2019
    Python Version: 3.5

    The web server interface module for the homeserver
'''

import json
import os
import re
import requests
import socket
import socketserver
import urllib.parse
from core.common import *
from core.devicemanager import StateRequestObject
from functools import partial
from http.server import SimpleHTTPRequestHandler
from io import BytesIO
from shutil import copyfile
from threading import Thread
from web.texts import getTextHTML


class WebServerHandler(SimpleHTTPRequestHandler):
    def __init__(self, config, dm, *args, **kwargs):
        self.config = config
        self.dm = dm
        self.dm_host = self.config['SERVER']['HOST']
        self.dm_port = self.config['SERVER'].getint('PORT')
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        return SimpleHTTPRequestHandler.translate_path(self, './web' + path)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        if ".html" in self.path or ".js" in self.path or self.headers.get('Referer') is None:
            _path = self.translate_path(self.path)
            if self.headers.get('Referer') is None:
                _path = os.path.join(_path, "index.html")
            with open(_path, 'rb') as f:
                _page = str(f.read().decode("unicode_escape"))
                match = re.findall(r'\_\((.*?)\)', _page)
                for _translatable in match:
                    _page = _page.replace("_(" + _translatable + ")", getTextHTML(_translatable.replace("\\", "")))
                self.send_response(200)
                self.send_header("Content-type", super().guess_type(_path))
                self.send_header("Content-length", len(_page))
                self.end_headers()
                self.wfile.write(_page.encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        postvars = urllib.parse.parse_qs(
            self.rfile.read(content_length), keep_blank_values=1)
        request = bool(postvars[b'request'][0].decode('utf-8'))
        reqtype = postvars[b'reqtype'][0].decode('utf-8')
        self._set_response()
        response = BytesIO()
        if request:
            if reqtype == "getstate":
                try:
                    # TODO Create a non-socketed getstate ?
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((self.dm_host, self.dm_port))
                    s.sendall("0008".encode('utf-8'))
                    s.sendall("getstate".encode('utf-8'))
                    data = s.recv(4096)
                    if data:
                        response.write(data)
                finally:
                    s.close()

            if reqtype == "getstatepost":
                try:
                    # TODO Create a non-socketed getstatepost ?
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((self.dm_host, self.dm_port))
                    s.sendall("0012".encode('utf-8'))
                    s.sendall("getstatepost".encode('utf-8'))
                    data = s.recv(1024)
                    if data:
                        response.write(data)
                finally:
                    s.close()

            if reqtype == "setstate":
                # TODO GET SUCCESS STATE ?
                req = StateRequestObject()
                devid = int(postvars[b'devid'][0].decode('utf-8'))
                value = str(postvars[b'value'][0].decode('utf-8'))
                isintensity = str(postvars[b'isintensity'][0].decode('utf-8'))
                skiptime = postvars[b'skiptime'][0].decode(
                    'utf-8') in ['true', True]
                _col = ["-1"] * len(self.dm.devices)
                try:
                    value = int(value)
                    if isintensity == "1" and self.dm.devices[devid].color_type == "255":
                        value = (None, value)
                except ValueError:
                    # Must be hexadecimal AARRGGBB
                    value = value[2:9]
                _col[devid] = value
                req.set_colors(_col, len(self.dm.devices))
                if skiptime:
                    req.set(skip_time=True)
                req.run(self.dm)
                response.write("1".encode("UTF-8"))

            if reqtype == "setmode":
                # TODO GET SUCCESS STATE ?
                cmode = postvars[b'mode'][0].decode('utf-8') in ['true', True]
                devid = int(postvars[b'devid'][0].decode('utf-8'))
                req = StateRequestObject()
                debug.write(
                    'Running a single device mode change', 0, "WEBSERVER")
                devid = int(client.recv(3).decode("UTF-8"))
                cmode = int(client.recv(1).decode("UTF-8"))
                req.set(set_mode_for_devid=devid)
                if cmode:
                    req.set(auto_mode=True)
                req.run(self.dm)
                debug.write('Device modes: {}'.format(
                    self.dm.get_modes()), 0, "WEBSERVER")
                response.write("1".encode("UTF-8"))

            if reqtype == "setgroup":
                # TODO GET SUCCESS STATE
                group = str(postvars[b'group'][0].decode('utf-8')).strip()
                value = int(postvars[b'value'][0].decode('utf-8'))
                skiptime = postvars[b'skiptime'][0].decode(
                    'utf-8') in ['true', True]
                req = StateRequestObject()
                debug.write('Running a group change of state', 0, "WEBSERVER")
                _col = ["0"] * len(self.dm.devices)
                if skiptime:
                    req.set(skip_time=True)
                if value == 1:
                    _col = ["1"] * len(self.dm.devices)
                req.set_colors(_col, len(self.dm.devices))
                req.set(group=[group.replace("0", "").lower()])
                req.run(self.dm)
                response.write("1".encode("UTF-8"))

            if reqtype == "setallmode":
                # TODO GET SUCCESS STATE ?
                req = StateRequestObject()
                debug.write(
                    'Running an all-devices mode change', 0, "WEBSERVER")
                req.set(force_auto_mode=True)
                req.run(self.dm)
                debug.write('Device modes: {}'.format(
                    self.dm.get_modes()), 0)
                response.write("1".encode("UTF-8"))

            if reqtype == "getmodule":
                module = str(postvars[b'module'][0].decode('utf-8'))
                debug.write(
                    'Getting module "{}" web content'.format(module), 0, "WEBSERVER")
                content = None
                for _mod in self.dm.modules:
                    if _mod.__class__.__name__ == module:
                        content = _mod.get_web()
                if content is None:
                    debug.write('Cannot find module', 1, "WEBSERVER")
                    response.write("0".encode("UTF-8"))
                else:
                    response.write(content.encode("UTF-8"))

            if reqtype == "dobackup":
                clientid = int(postvars[b'clientid'][0].decode('utf-8'))
                debug.write('Scheduling backup', 0, "WEBSERVER")
                for _mod in self.dm.modules:
                    if _mod.__class__.__name__ == "backup":
                        content = _mod.backup_queue.put(clientid)
                response.write("1".encode("UTF-8"))

            if reqtype == "setlock":
                lock = int(postvars[b'lock'][0].decode('utf-8'))
                devid = int(postvars[b'devid'][0].decode('utf-8'))
                self.dm.devices[devid].lock_unlock_requests(lock)
                response.write("1".encode("UTF-8"))

            if reqtype == "getconfig":
                _conf_dict = {s: dict(self.config.items(s))
                              for s in self.config.sections()}
                response.write(json.dumps(_conf_dict).encode('UTF-8'))

            if reqtype == "setconfig":
                section = str(postvars[b'section'][0].decode('utf-8'))
                configdata = json.loads(urllib.parse.unquote(
                    postvars[b'configdata'][0].decode('utf-8')))
                has_changes = False
                for entry in configdata:
                    if self.config[section.upper()][entry] != configdata[entry]:
                        debug.write("Changing configuration entry {} to {}".format(
                            entry.upper(), configdata[entry]), 0, "WEBSERVER")
                        self.config.set(section.upper(),
                                        entry.upper(), configdata[entry])
                        has_changes = True
                if has_changes:
                    debug.write(
                        "Changing local config file and creating backup 'home.old'", 0, "WEBSERVER")
                    with open('home.ini', 'w') as configfile:
                        copyfile('home.ini', 'home.old')
                        self.config.write(configfile)
                    self.dm.reload_configs()
                    response.write("1".encode("UTF-8"))

            if reqtype == "getdebuglog":
                debuglevel = postvars[b'debuglevel'][0].decode('utf-8')
                debug.write(
                    'Getting debug log for weblog module', 0, "WEBSERVER")
                for _mod in self.dm.modules:
                    if _mod.__class__.__name__ == "weblog":
                        content = _mod.get_web(debuglevel)
                if content is None:
                    debug.write('Cannot find module', 1, "WEBSERVER")
                    response.write("0".encode("UTF-8"))
                else:
                    response.write(content.encode("UTF-8"))

            if reqtype == "gettext":
                textid = postvars[b'textid'][0].decode('utf-8')
                response.write(getTextHTML(textid).encode("utf-8"))

            # ADD NECESSARY WEBSERVER REQUESTS HERE #

        else:
            response.write("No request or unknown request".encode("UTF-8"))
        self.wfile.write(response.getvalue())


class webserver(Thread):
    def __init__(self, config, dm):
        Thread.__init__(self)
        self.config = config
        self.dm = dm
        self.port = self.config['SERVER'].getint('WEBSERVER_PORT')
        self.running = True

    def run(self):
        debug.write("Starting control webserver on port {}".format(
            self.port), 0, "WEBSERVER")
        socketserver.TCPServer.allow_reuse_address = True
        _handler = partial(WebServerHandler, self.config, self.dm)
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
        try:
            requests.get("http://localhost:{}/".format(self.port))
        except requests.exceptions.ConnectionError:
            pass

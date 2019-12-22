#!/usr/bin/env python3
'''
    File name: webserver.py
    Author: Maxime Bergeron
    Date last modified: 22/12/2019
    Python Version: 3.7

    The web server interface module for the homeserver
'''

import json
import os
import re
import requests
import time
import traceback
import urllib.parse
from core.common import *
from core.devicemanager import StateRequestObject, ExecutionState
from functools import partial
from http.server import SimpleHTTPRequestHandler
from html.parser import HTMLParser
from io import BytesIO
from shutil import copyfile
from socketserver import ThreadingMixIn, TCPServer
from threading import Thread
from web.texts import getTextHTML


class ThreadingSimpleServer(ThreadingMixIn, TCPServer):
    pass


class HTMLGettextTranslator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.has_tag = False
        self.data = []

    def handle_starttag(self, tag, attributes):
        if tag != 'tl':
            return
        self.has_tag = True

    def handle_endtag(self, tag):
        if tag == 'tl':
            self.has_tag = False

    def handle_data(self, data):
        if self.has_tag:
            self.data.append(data)


class WebServerHandler(SimpleHTTPRequestHandler):
    def __init__(self, config, dm, *args, **kwargs):
        self.config = config
        self.dm = dm
        self.dm_host = self.config['SERVER']['HOST']
        self.dm_port = self.config.get_value('PORT', int, parent="SERVER")
        self.allowed_ips = []
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        return SimpleHTTPRequestHandler.translate_path(self, './web' + path)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        if self.config["WEBSERVER"]["SECURITY"] == "restrictive":
            if not self.allowed_ips:
                for _user in self.config["USERS"]:
                    _ips = self.config["USERS"][_user].split(",")
                    for _ip in _ips:
                        self.allowed_ips.append(_ip)
            if self.client_address[0] not in self.allowed_ips:
                _path = os.path.join(
                    self.translate_path(self.path), "index.html")
                _page = "<!doctype html><html><body><h1>You cannot access this page.</h1></body></html>"
                self.send_response(200)
                self.send_header("Content-type", super().guess_type(_path))
                self.send_header("Content-length", len(_page))
                self.end_headers()
                self.wfile.write(_page.encode('utf-8'))

        elif self.config["WEBSERVER"]["SECURITY"] != "permissive":
            debug.write("Unknown security level for webserver: {}".format(
                self.config["WEBSERVER"]["SECURITY"]), 1)
            return
        try:
            if ".html" in self.path or ".js" in self.path or self.path == "/":
                _path = self.translate_path(self.path)
                if self.path == "/":
                    _path = os.path.join(_path, "index.html")
                with open(_path, 'rb') as f:
                    _page = str(f.read().decode("unicode_escape"))
                    tagmatch = []
                    if ".html" in _path:
                        _parser = HTMLGettextTranslator()
                        _parser.feed(_page)
                        tagmatch = _parser.data
                        _parser.close()
                    match = re.findall(r'\_\((.*?)\)', _page)
                    for _translatable in tagmatch:
                        _page = _page.replace(
                            "<tl>" + _translatable + "</tl>", getTextHTML(_translatable.replace("\\", "")))
                    for _translatable in match:
                        _page = _page.replace(
                            "_(" + _translatable + ")", getTextHTML(_translatable.replace("\\", "")))
                    if self.path == "/":
                        for _user in self.config["USERS"]:
                            _ips = self.config["USERS"][_user].split(",")
                            if self.client_address[0] in _ips:
                                debug.write("{} connected to the webserver".format(
                                    _user.title()), 0, "WEBSERVER")
                                _page += '<script>setTimeout(function(){{$("#detector-user-name").html(" {}")}}, 500)</script>'.format(
                                    _user.split(" ")[0].title())
                                for _ip in _ips:
                                    _page += '<style>img[ip="{}"]{{box-shadow:0px 0px 5px 5px #B0C4DE; }}</style>'.format(
                                        _ip)
                    self.send_response(200)
                    self.send_header("Content-type", super().guess_type(_path))
                    if self.path != "/":
                        self.send_header("Content-length", len(_page))
                    self.end_headers()
                    self.wfile.write(_page.encode('utf-8'))
            else:
                super().do_GET()
        except Exception as ex:
            debug.write("Got exception in GET request: {}".format(ex), 1)

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            try:
                postvars = urllib.parse.parse_qs(
                    self.rfile.read(content_length), keep_blank_values=1)
            except UnicodeDecodeError:
                postvars = urllib.parse.unquote(
                    self.rfile.read(content_length), keep_blank_values=1)
                postvars = urllib.parse.parse_qs(postvars)
            request = postvars[b'request'][0].decode(
                'utf-8') in ["True", "true", True]
            reqtype = postvars[b'reqtype'][0].decode('utf-8')
            self._set_response()
            response = BytesIO()
            if request:
                if reqtype == "getstate":
                    is_async = postvars[b'isasync'][0].decode(
                        'utf-8') in ["True", "true", True]
                    devid = None
                    try:
                        devid = int(postvars[b'devid'][0].decode('utf-8'))
                    except KeyError:
                        pass
                    if devid is None:
                        response.write(json.dumps(
                            self.dm(is_async=is_async)).encode('UTF-8'))
                    else:
                        response.write(json.dumps(
                            self.dm(async_only_for_devid=devid)).encode('UTF-8'))

                if reqtype == "setstate":
                    # TODO GET SUCCESS STATE ?
                    req = StateRequestObject()
                    req.initialize_dm(self.dm)
                    devid = int(postvars[b'devid'][0].decode('utf-8'))
                    value = str(postvars[b'value'][0].decode('utf-8'))
                    debug.write(
                        'Running a single device ({}) state change to {}'.format(self.dm[devid].name, value), 0, "WEBSERVER")
                    isintensity = str(
                        postvars[b'isintensity'][0].decode('utf-8'))
                    skiptime = postvars[b'skiptime'][0].decode(
                        'utf-8') in ['true', True]
                    _col = ["-1"] * len(self.dm)
                    try:
                        value = int(value)
                        if isintensity == "1" and self.dm[devid].color_type == "255":
                            value = (None, value)
                    except ValueError:
                        pass
                    _col[devid] = value
                    req.set_colors(_col)
                    if skiptime:
                        req.set(skip_time=True)
                    req()
                    while ExecutionState().get():
                        time.sleep(0.5)
                    response.write("1".encode("UTF-8"))

                if reqtype == "setmode":
                    # TODO GET SUCCESS STATE ?
                    cmode = postvars[b'mode'][0].decode(
                        'utf-8') in ['true', True]
                    devid = int(postvars[b'devid'][0].decode('utf-8'))
                    req = StateRequestObject()
                    debug.write(
                        'Running a single device mode change', 0, "WEBSERVER")
                    req.set(set_mode_for_devid=devid)
                    if cmode:
                        req.set(auto_mode=True)
                    req()
                    while ExecutionState().get():
                        time.sleep(0.5)
                    debug.write('Device modes: {}'.format(
                        self.dm.modes), 0, "WEBSERVER")
                    response.write("1".encode("UTF-8"))

                if reqtype == "setgroup":
                    # TODO GET SUCCESS STATE
                    group = str(postvars[b'group'][0].decode('utf-8')).strip()
                    value = int(postvars[b'value'][0].decode('utf-8'))
                    skiptime = postvars[b'skiptime'][0].decode(
                        'utf-8') in ['true', True]
                    req = StateRequestObject()
                    req.initialize_dm(self.dm)
                    debug.write('Running a group change of state',
                                0, "WEBSERVER")
                    _col = ["0"] * len(self.dm)
                    if skiptime:
                        req.set(skip_time=True)
                    if value == 1:
                        _col = [DEVICE_ON]
                    req.set_colors(_col)
                    req.set(group=[group.replace("0", "").lower()])
                    req()
                    while ExecutionState().get():
                        time.sleep(0.5)
                    response.write("1".encode("UTF-8"))

                if reqtype == "setallmode":
                    # TODO GET SUCCESS STATE ?
                    req = StateRequestObject()
                    debug.write(
                        'Running an all-devices mode change', 0, "WEBSERVER")
                    req.set(force_auto_mode=True)
                    req()
                    while ExecutionState().get():
                        time.sleep(0.5)
                    debug.write('Device modes: {}'.format(
                        self.dm.modes), 0)
                    response.write("1".encode("UTF-8"))

                if reqtype == "getmodule":
                    module = str(postvars[b'module'][0].decode('utf-8'))
                    content = None
                    for _mod in self.dm.modules:
                        if _mod.__class__.__name__ == module:
                            content = _mod.get_web()
                    if content is None:
                        debug.write('Cannot find module', 1, "WEBSERVER")
                        response.write("0".encode("UTF-8"))
                    else:
                        response.write(json.dumps(content).encode('utf-8'))

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
                    self.dm[devid].lock_unlock_requests(lock)
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
                        return

                if reqtype == "reloadconfig":
                    self.dm.reload_configs()
                    return

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

                if reqtype == "reconnect":
                    devid = int(postvars[b'devid'][0].decode('utf-8'))
                    self.dm[devid].reconnect()
                    response.write("1".encode("UTF-8"))

                if reqtype == "confirmstate":
                    devid = int(postvars[b'devid'][0].decode('utf-8'))
                    state = str(postvars[b'state'][0].decode('utf-8'))
                    self.dm[devid].set_state(state)
                    response.write("1".encode("UTF-8"))

                if reqtype == "getconfigxml":
                    with open("core/configurables.xml", "r") as _f:
                        _parser = HTMLGettextTranslator()
                        _page = _f.read()
                        _parser.feed(_page)
                        tagmatch = _parser.data
                        _parser.close()
                        for _translatable in tagmatch:
                            _page = _page.replace(
                                "<tl>" + _translatable + "</tl>", getTextHTML(_translatable.replace("\\", "")))
                        response.write(_page.encode("UTF-8"))

                if reqtype == "getpresets":
                    presets = {}
                    presets["items"] = []
                    presets["descriptions"] = []
                    presets["devices"] = getDevices(True)
                    presets["preset"] = []
                    for _preset in self.config["PRESETS"].items():
                        req = StateRequestObject()
                        req.initialize_dm(self.dm)
                        if _preset[0] != "automatic_mode" and req.from_string(_preset[1]):
                            presets["items"].append(_preset[0])
                            presets["preset"].append(_preset[1])
                            presets["descriptions"].append(str(req))
                    response.write(json.dumps(presets).encode("UTF-8"))

                if reqtype == "setpreset":
                    preset = str(json.loads(
                        str(postvars[b'preset'][0].decode('utf-8'))))
                    presetname = str(
                        postvars[b'presetname'][0].decode('utf-8'))
                    debug.write("Parsing new preset {}, string: {}".format(
                        presetname, preset), 0, "WEBSERVER")
                    req = StateRequestObject()
                    req.initialize_dm(self.dm)
                    if req.from_string(preset):
                        self.config.set("PRESETS", presetname.upper(), preset)
                        response.write("1".encode("UTF-8"))
                        debug.write(
                            "Changing local config file and creating backup 'home.old'", 0, "WEBSERVER")
                        with open('home.ini', 'w') as configfile:
                            copyfile('home.ini', 'home.old')
                            self.config.write(configfile)
                        self.dm.reload_configs()
                    else:
                        response.write("0".encode("UTF-8"))

                if reqtype == "getroomgroups":
                    groups = {}
                    groups["groups"] = self.dm.all_groups
                    groups["rooms"] = self.config["WEBSERVER"]["ROOM_GROUPS"].split(
                        ",")
                    response.write(json.dumps(groups).encode("UTF-8"))

                if reqtype == "setroomgroups":
                    rooms = urllib.parse.unquote(json.loads(
                        str(postvars[b'rooms'][0].decode("UTF-8"))))
                    debug.write("Changing room groups to {}".format(
                        rooms), 0, "WEBSERVER")
                    response.write("1".encode("UTF-8"))
                    self.config.set("WEBSERVER", "ROOM_GROUPS", rooms)
                    with open('home.ini', 'w') as configfile:
                        copyfile('home.ini', 'home.old')
                        self.config.write(configfile)
                    self.dm.reload_configs()

                # ADD NECESSARY WEBSERVER REQUESTS HERE #

            else:
                response.write("No request or unknown request".encode("UTF-8"))
            self.wfile.write(response.getvalue())

        except Exception as ex:
            debug.write("Got exception in POST request: ({}) - {}, {}".format(
                type(ex).__name__, ex, traceback.format_exc()), 1)


class webserver(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.init_from_config()
        self.dm = dm

    def run(self):
        self.running = True
        debug.write("Starting control webserver on port {}".format(
            self.port), 0, "WEBSERVER")
        TCPServer.allow_reuse_address = True
        _handler = partial(WebServerHandler, self.config, self.dm)
        # httpd = socketserver.TCPServer(("", self.port), _handler)
        httpd = ThreadingSimpleServer(("", self.port), _handler)

        try:
            while self.running:
                httpd.handle_request()
        finally:
            httpd.server_close()
            debug.write("Stopped.", 0, "WEBSERVER")
            return

    def init_from_config(self):
        self.config = getConfigHandler()
        self.port = self.config.get_value(
            'WEBSERVER_PORT', int, parent="SERVER")

    def stop(self):
        debug.write("Stopping.", 0, "WEBSERVER")
        self.running = False
        # Needs a last call to shut down properly on python3.5
        try:
            requests.get("http://localhost:{}/".format(self.port))
        except requests.exceptions.ConnectionError:
            pass

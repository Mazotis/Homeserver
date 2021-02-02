#!/usr/bin/env python3
'''
    File name: webservernode.py
    Author: Maxime Bergeron
    Date last modified: 21/01/2021
    Python Version: 3.8

    The web server interface with nodeJS support module for the homeserver
'''

import json
import requests
import socketio
import subprocess
import time
import urllib3
import urllib.parse
from core.common import *
from core.devicemanager import StateRequestObject, ExecutionState
from shutil import copyfile
from threading import Thread
try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty


class webservernode(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.server_process = None
        self.init_from_config()
        self.dm = dm
        _req_sess = requests.Session()
        if self.protocol == "https":
            _req_sess.cert = (self.cert, self.key)
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.sio = socketio.Client(
            http_session=_req_sess, ssl_verify=False, reconnection_attempts=3)

    def run(self):
        self.running = True
        debug.write("Starting control webserver-node on port {}".format(
            self.port), 0, "WEBSERVERNODE")
        _lastStatus = None
        try:
            # TODO check for node.js install & packages
            _request = ""
            _req_sess_isconnected = False
            if self.protocol == "https":
                _request = "npm run start {} {} true {} {} --prefix {}/../web-node".format(
                    self.port, language.getLanguage(), self.key, self.cert, CORE_DIR)
            else:
                _request = "npm run start {} {} false --prefix {}/../web-node".format(
                    self.port, language.getLanguage(), CORE_DIR)
            # Delay server start to allow ports to get freed from last execution
            time.sleep(5)
            self.server_process = subprocess.Popen(
                _request, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            q = Queue()
            t = Thread(target=webservernode.enqueue_output,
                       args=(self.server_process.stdout, q))
            t.daemon = True
            t.start()
            while self.running:
                while not self.dm.running:
                    # TODO Fix race condition between module load and DM state getter?
                    time.sleep(1)
                if self.dm.status != _lastStatus and self.running:
                    debug.write("Sending update to websocket",
                                0, "WEBSERVERNODE")
                    try:
                        if not _req_sess_isconnected:
                            self.sio.connect(
                                '{}://localhost:{}'.format(self.protocol, self.port), transports="websocket")
                            self.sio.on('query', self.query)
                            _req_sess_isconnected = True
                            time.sleep(2)
                        self.sio.emit('set_hs_socket')
                        self.sio.emit('update_state', self.dm.status)
                    except Exception as ex:
                        debug.write(
                            "Failed to connect to websocket. Retrying", 1, "WEBSERVERNODE")
                        debug.write("Got error: {}".format(
                            ex), 1, "WEBSERVERNODE")
                        self.sio.disconnect()
                        _req_sess_isconnected = False
                        time.sleep(2)
                        continue
                _lastStatus = self.dm.status

                while True:
                    try:
                        line = q.get_nowait()  # or q.get(timeout=.1)
                    except Empty:
                        break
                    else:
                        debug.write("(NODE.JS) {}".format(
                            line.rstrip().decode("UTF-8")), 0, "WEBSERVERNODE")

                time.sleep(1)

        except Exception as ex:
            debug.write("GOT ERROR {}".format(ex), 1, "WEBSERVERNODE")

        finally:
            self.server_process.terminate()
            self.server_process.wait()
            subprocess.Popen("/usr/bin/killall node", shell=True)
            self.sio.disconnect()
            debug.write("Stopped.", 0, "WEBSERVERNODE")
            return

    def init_from_config(self):
        self.config = getConfigHandler()
        self.port = self.config.get_value(
            'WEBSERVER_PORT', int, parent="SERVER")
        self.protocol = self.config['WEBSERVER']['PROTOCOL']
        if self.protocol == "https":
            self.key = self.config['WEBSERVER']['WEBSERVER_HTTPS_CERTS_KEY']
            self.cert = self.config['WEBSERVER']['WEBSERVER_HTTPS_CERTS_CERT']
        self.hidden_presets = ""
        if self.config.has_option("WEBSERVER", "HIDDEN_PRESETS"):
            self.hidden_presets = self.config["WEBSERVER"]["HIDDEN_PRESETS"].split(
                ",")

    def stop(self):
        debug.write("Stopping.", 0, "WEBSERVERNODE")
        self.running = False

    def query(self, reqquery):
        reqtype = reqquery["reqtype"]
        _response = False

        debug.write("Handling query {}".format(reqquery), 0, "WEBSERVERNODE")

        if reqtype == "getstate":
            is_async = reqquery['isasync'] in ["True", "true", True]
            devid = None
            try:
                devid = int(reqquery['devid'])
            except KeyError:
                pass
            if devid is None:
                _response = self.dm(is_async=is_async)
            else:
                _response = self.dm(sync_only_for_devid=devid)

        elif reqtype == "setstate":
            # TODO GET SUCCESS STATE ?
            req = StateRequestObject()
            req.initialize_dm(self.dm)
            devid = int(reqquery['devid'])
            value = str(reqquery['value'])
            debug.write(
                'Running a single device ({}) state change to {}'.format(self.dm[devid].name, value), 0, "WEBSERVERNODE")
            isintensity = str(
                reqquery['isintensity'])
            _col = ["-1"] * len(self.dm)
            try:
                value = int(value)
                if isintensity == "1" and self.dm[devid].color_type == "255":
                    value = (None, value)
            except ValueError:
                pass
            _col[devid] = value
            req.set_colors(_col)
            req.set(skip_time=True, history_origin="Webserver")
            req()
            while ExecutionState().get():
                time.sleep(0.5)
            _response = "1"

        elif reqtype == "setmode":
            # TODO GET SUCCESS STATE ?
            cmode = reqquery['mode'] in ['true', True]
            devid = int(reqquery['devid'])
            req = StateRequestObject()
            req.initialize_dm(self.dm)
            debug.write(
                'Running a single device mode change', 0, "WEBSERVERNODE")
            req.set(set_mode_for_devid=devid, history_origin="Webserver")
            if cmode:
                req.set(auto_mode=True)
            req()
            while ExecutionState().get():
                time.sleep(0.5)
            debug.write('Device modes: {}'.format(
                self.dm.modes), 0, "WEBSERVERNODE")
            _response = "1"

        elif reqtype == "setgroup":
            # TODO GET SUCCESS STATE
            group = urllib.parse.unquote(
                str(reqquery['group']).strip().replace("_", " "))
            value = int(reqquery['value'])
            skiptime = reqquery['skiptime'] in ['true', True]
            req = StateRequestObject()
            req.initialize_dm(self.dm)
            debug.write('Running a group change of state',
                        0, "WEBSERVERNODE")
            _col = [str(value)] * len(self.dm)
            if skiptime:
                req.set(skip_time=True)
            req.set_colors(_col)
            req.set(group=[group.replace("0", "").lower()],
                    history_origin="Webserver")
            req()
            while ExecutionState().get():
                time.sleep(0.5)
            _response = "1"

        elif reqtype == "setallmode":
            # TODO GET SUCCESS STATE ?
            req = StateRequestObject()
            req.initialize_dm(self.dm)
            debug.write(
                'Running an all-devices mode change', 0, "WEBSERVERNODE")
            req.set(force_auto_mode=True, history_origin="Webserver")
            req()
            while ExecutionState().get():
                time.sleep(0.5)
            debug.write('Device modes: {}'.format(
                self.dm.modes), 0)
            _response = "1"

        elif reqtype == "getmodule":
            module = str(reqquery['module'])
            content = None
            for _mod in self.dm.modules:
                if _mod.__class__.__name__ == module:
                    content = _mod.get_web()
                    break
            if content is None:
                debug.write('Cannot find module {}. Setting as offline.'.format(module), 0, "WEBSERVERNODE")
                _response = "<div class='alert alert-secondary' role='alert' style='width:100%; height:100%'>N/A</div>"
            else:                
                _response = content

        elif reqtype == "dobackup":
            clientid = int(reqquery['clientid'])
            debug.write('Scheduling backup', 0, "WEBSERVERNODE")
            for _mod in self.dm.modules:
                if _mod.__class__.__name__ == "backup":
                    content = _mod.backup_queue.put(clientid)
            _response = "1"

        elif reqtype == "setlock":
            lock = int(reqquery['lock'])
            devid = int(reqquery['devid'])
            self.dm[devid].lock_unlock_requests(lock)
            _response = "1"

        elif reqtype == "getconfig":
            _conf_dict = {s: dict(self.config.items(s))
                          for s in self.config.sections()}
            _response = _conf_dict

        elif reqtype == "setconfig":
            section = str(reqquery['section'])
            configdata = json.loads(urllib.parse.unquote(
                reqquery['configdata']))
            has_changes = False
            for entry in configdata:
                if self.config[section.upper()][entry] != configdata[entry]:
                    debug.write("Changing configuration entry {} to {}".format(
                        entry.upper(), configdata[entry]), 0, "WEBSERVERNODE")
                    self.config.set(section.upper(),
                                    entry.upper(), configdata[entry])
                    has_changes = True
            if has_changes:
                debug.write(
                    "Changing local config file and creating backup 'home.old'", 0, "WEBSERVERNODE")
                with open('home.ini', 'w') as configfile:
                    copyfile('home.ini', 'home.old')
                    self.config.write(configfile)
                self.dm.reload_configs()

        elif reqtype == "reloadconfig":
            self.dm.reload_configs()

        elif reqtype == "getdebuglog":
            debuglevel = reqquery['debuglevel']
            debug.write(
                'Getting debug log for weblog module', 0, "WEBSERVERNODE")
            for _mod in self.dm.modules:
                if _mod.__class__.__name__ == "weblog":
                    content = _mod.get_web(debuglevel)
            if content is None:
                debug.write('Cannot find module weblog', 1, "WEBSERVERNODE")
                _response = "0"
            else:
                _response = content

        elif reqtype == "reconnect":
            devid = int(reqquery['devid'])
            self.dm[devid].reconnect()
            _response = "1"

        elif reqtype == "confirmstate":
            devid = int(reqquery['devid'])
            state = str(reqquery['state'])
            self.dm[devid].set_state(state)
            _response = "1"

        elif reqtype == "getpresets":
            presets = {}
            presets["items"] = []
            presets["descriptions"] = []
            presets["devices"] = getDevices(True)
            presets["preset"] = []
            presets["results"] = []
            presets["hidden"] = []
            for _preset in self.config["PRESETS"].items():
                req = StateRequestObject()
                req.initialize_dm(self.dm)
                if _preset[0] != "automatic_mode" and req.from_string(_preset[1]):
                    presets["items"].append(_preset[0])
                    presets["preset"].append(_preset[1].replace(
                        "True", "true").replace("False", "false"))
                    presets["descriptions"].append(str(req))
                    presets["results"].append(req.colors)
                    if _preset[0] in self.hidden_presets:
                        presets["hidden"].append("1")
                    else:
                        presets["hidden"].append("0")

            _response = presets

        elif reqtype == "setpreset":
            preset = str(json.loads(
                str(reqquery['preset'])))
            presetname = str(
                reqquery['presetname'])
            debug.write("Parsing new preset {}, string: {}".format(
                presetname, preset), 0, "WEBSERVERNODE")
            req = StateRequestObject()
            req.initialize_dm(self.dm)
            if req.from_string(preset):
                self.config.set("PRESETS", presetname.upper(), preset)
                debug.write(
                    "Changing local config file and creating backup 'home.old'", 0, "WEBSERVERNODE")
                with open('home.ini', 'w') as configfile:
                    copyfile('home.ini', 'home.old')
                    self.config.write(configfile)
                self.dm.reload_configs()
                _response = "1"
            else:
                _response = "0"

        elif reqtype == "runpreset":
            preset = str(reqquery['preset'])
            req = StateRequestObject()
            req.initialize_dm(self.dm)
            debug.write('Running a preset change of state',
                        0, "WEBSERVERNODE")
            req.set(preset=preset, history_origin="Webserver")
            req()
            while ExecutionState().get():
                time.sleep(0.5)
            _response = "1"

        elif reqtype == "getroomgroups":
            groups = {}
            groups["groups"] = self.dm.all_groups
            groups["rooms"] = self.config["WEBSERVER"]["ROOM_GROUPS"].split(
                ",")
            _response = groups

        elif reqtype == "setroomgroups":
            rooms = urllib.parse.unquote(json.loads(
                str(reqquery['rooms'])))
            debug.write("Changing room groups to {}".format(
                rooms), 0, "WEBSERVERNODE")
            self.config.set("WEBSERVERNODE", "ROOM_GROUPS", rooms)
            with open('home.ini', 'w') as configfile:
                copyfile('home.ini', 'home.old')
                self.config.write(configfile)
            self.dm.reload_configs()
            _response = "1"

        elif reqtype == "setpresetview":
            presetlist = urllib.parse.unquote(json.loads(
                str(reqquery['presetlist'])))
            debug.write("Changing preset visibility to {}".format(
                presetlist), 0, "WEBSERVERNODE")
            self.config.set("WEBSERVER", "HIDDEN_PRESETS", presetlist)
            with open('home.ini', 'w') as configfile:
                copyfile('home.ini', 'home.old')
                self.config.write(configfile)
            self.dm.reload_configs()
            _response = "1"

        else:
            debug.write("Requested query '{}' is not configured. Consider updating your Homeserver installation".format(
                reqtype), 1, "WEBSERVERNODE")

        return json.dumps(_response)

    @staticmethod
    def enqueue_output(out, queue):
        for line in iter(out.readline, b''):
            queue.put(line)
        out.close()

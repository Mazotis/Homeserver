#!/usr/bin/env python3
'''
    File name: ifttt.py
    Author: Maxime Bergeron
    Date last modified: 16/06/2020
    Python Version: 3.7

    The IFTTT receiver module for the homeserver
'''

import hashlib
import requests
import ssl
import unidecode
import urllib.parse
from core.common import *
from core.devicemanager import StateRequestObject
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


class IFTTTServer(BaseHTTPRequestHandler):
    def __init__(self, config, dm, *args, **kwargs):
        self.config = config
        self.dm = dm
        self.priority_groups = []
        if self.config.has_option("IFTTT", "PRIORITY_GROUPS"):
            self.priority_groups = self.config["PRIORITY_GROUPS"].split(",")
        self.global_group = None
        if self.config.has_option("IFTTT", "GLOBAL_GROUP"):
            self.global_group = self.config["GLOBAL_GROUP"]
        super().__init__(*args, **kwargs)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        self._set_response()

    def do_POST(self):
        """ Receives and handles POST request """
        SALT = self.config["SALT"]
        debug.write('Getting request', 0, "IFTTT")
        content_length = int(self.headers['Content-Length'])
        postvars = urllib.parse.parse_qs(self.rfile.read(
            content_length).decode('UTF-8'), keep_blank_values=1)
        self._set_response()

        if 'hash' in postvars:
            _hash = postvars['hash'][0]
            action = postvars['action'][0]
            if _hash != hashlib.sha512(bytes(SALT.encode('utf-8') + action.encode('utf-8'))).hexdigest():
                debug.write('Unauthorized action {}. Hash verification failed.'.format(
                    action), 1, "IFTTT")

            if action in self.config:
                debug.write('Running action : {}'.format(
                    self.config[action]), 0, "IFTTT")
                req = StateRequestObject()
                req.initialize_dm(self.dm)
                req.set(preset=self.config[action], history_origin="IFTTT")
                req()
            else:
                debug.write('Unknown action: {}'.format(action), 1, "IFTTT")

        else:
            req = StateRequestObject()
            func = postvars['function'][0]

            if func not in ["on", "off"]:
                debug.write(
                    "Function {} not defined. Request aborted.", 1, "IFTTT")
                return
            req.initialize_dm(self.dm)
            req.set(history_origin="IFTTT")
            if func == "on":
                req.set_colors([DEVICE_ON] * len(self.dm))
            elif func == "off":
                req.set(skip_time=True)
                req.set_colors([DEVICE_OFF] * len(self.dm))

            group = unidecode.unidecode(postvars['group'][0])
            groups = [unidecode.unidecode(x) for x in self.dm.all_groups]
            changed_groups = []
            has_priority_group = False
            has_global_group = False
            for _group in groups:
                if _group.lower() in group:
                    if _group.lower() in self.priority_groups:
                        has_priority_group = True
                    changed_groups.append(_group)
            # TODO add a proper pluralization ?
            for _group in group.split():
                if _group == self.global_group:
                    has_global_group = True
                    changed_groups.append(self.global_group)
                    debug.write(
                        "Got global group. Running request on all devices.", 0, "IFTTT")
                if _group.lower() + "s" in groups:
                    changed_groups.append(_group + "s")
            if len(changed_groups) != 0 and not has_global_group:
                req.set(group=changed_groups)
            elif not has_global_group:
                debug.write("No devices belong to group {}. Request aborted.".format(
                    group), 1, "IFTTT")
                return
            debug.write("Running function '{}' on group(s) {}".format(
                func, changed_groups), 0, "IFTTT")
            if has_global_group:
                for dev in self.dm:
                    if dev.ignore_global_group:
                        debug.write("Skipping device {} as it ignores global group requests".format(
                            dev.name), 1, "IFTTT")
                        req.set_color_for_devid(DEVICE_SKIP, dev.devid)
            if self.config.get_value('AUTOMATIC_MODE', bool):
                req.set(auto_mode=True)
            elif not has_priority_group:
                debug.write(
                    "No priority groups called. Setting back to AUTO mode.", 0, "IFTTT")
                req.set(reset_mode=True)
            req()

            if 'delay' in postvars and int(postvars['delay'][0]) != 0:
                if func == "on":
                    req.set_colors([DEVICE_OFF] * len(self.dm))
                elif func == "off":
                    req.set(skip_time=True)
                    req.set_colors([DEVICE_ON] * len(self.dm))
                req.set(delay=int(postvars['delay'][0]) * 60)
                req()

        if 'postaction' in postvars:
            post_action = postvars['postaction'][0]
            delay = int(postvars['delay'][0]) * 60

            if delay != 0:
                debug.write('Will run action {} in {} seconds'.format(
                    post_action, delay), 0, "IFTTT")
                if post_action in self.config:
                    req = StateRequestObject()
                    req.initialize_dm(self.dm)
                    req.set(
                        delay=delay, preset=self.config[post_action], history_origin="IFTTT")
                    if self.config.get_value('AUTOMATIC_MODE', bool):
                        req.set(auto_mode=True)
                    req()
                else:
                    #
                    # Complex delayed actions should be hardcoded here if needed
                    #
                    debug.write('Unknown action: {}'.format(
                        post_action), 1, "IFTTT")


class ifttt(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.init_from_config()
        self.dm = dm

    def run(self):
        self.running = True
        debug.write('Getting lightserver POST requests on port {} using {} protocol'
                    .format(self.port, self.protocol), 0, "IFTTT")
        IFTTTServerPartial = partial(IFTTTServer, self.config, self.dm)
        httpd = HTTPServer(('', self.port), IFTTTServerPartial)
        if self.protocol == "https":
            httpd.socket = ssl.wrap_socket(httpd.socket,
                                           keyfile=self.key,
                                           certfile=self.cert, server_side=True)
        try:
            while self.running:
                httpd.handle_request()
        finally:
            httpd.server_close()
            debug.write('Stopped.', 0, "IFTTT")
            return

    def init_from_config(self):
        self.config = getConfigHandler().set_section("IFTTT")
        self.port = self.config.get_value(
            'VOICE_SERVER_PORT', int, parent="SERVER")
        self.protocol = self.config['PROTOCOL']
        if self.protocol == "https":
            self.key = self.config['IFTTT_HTTPS_CERTS_KEY']
            self.cert = self.config['IFTTT_HTTPS_CERTS_CERT']

    def stop(self):
        debug.write('Stopping.', 0, "IFTTT")
        self.running = False
        # Needs a last call to shut down properly on python3.5
        try:
            requests.get("http://localhost:{}/".format(self.port))
        except requests.exceptions.ConnectionError:
            pass

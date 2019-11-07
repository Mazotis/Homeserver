#!/usr/bin/env python3
'''
    File name: ifttt.py
    Author: Maxime Bergeron
    Date last modified: 07/11/2019
    Python Version: 3.5

    The IFTTT receiver module for the homeserver
'''

import hashlib
import requests
import ssl
import time
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
            self.priority_groups = self.config["IFTTT"]["PRIORITY_GROUPS"].split(
                ",")
        super().__init__(*args, **kwargs)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        self._set_response()

    def do_POST(self):
        """ Receives and handles POST request """
        SALT = self.config["IFTTT"]["SALT"]
        debug.write('Getting request', 0, "IFTTT")
        content_length = int(self.headers['Content-Length'])
        postvars = urllib.parse.parse_qs(self.rfile.read(
            content_length).decode('UTF-8'), keep_blank_values=1)
        self._set_response()

        try:
            # TODO rewrite this more elegantly
            # TODO link directly to the LM server ?
            _hash = postvars['hash'][0]
            action = postvars['action'][0]
            if _hash != hashlib.sha512(bytes(SALT.encode('utf-8') + action.encode('utf-8'))).hexdigest():
                debug.write('Unauthorized action {}. Hash verification failed.'.format(
                    action), 1, "IFTTT")

            if action in self.config["IFTTT"]:
                debug.write('Running action : {}'.format(
                    self.config["IFTTT"][action]), 0, "IFTTT")
                os.system("./homeclient.py " + self.config["IFTTT"][action])
            else:
                debug.write('Unknown action: {}'.format(action), 1, "IFTTT")

        except KeyError:
            # TODO hash group requests somehow or require HTTPS?
            req = StateRequestObject()
            func = postvars['function'][0]

            if func not in ["on", "off"]:
                debug.write(
                    "Function {} not defined. Request aborted.", 1, "IFTTT")
                return
            if func == "on":
                req.set_colors(
                    [DEVICE_ON] * len(self.dm), len(self.dm))
            elif func == "off":
                req.set(skip_time=True)
                req.set_colors(
                    [DEVICE_OFF] * len(self.dm), len(self.dm))

            group = postvars['group'][0].split()
            group = [unidecode.unidecode(x) for x in group]
            groups = self.dm.all_groups
            changed_groups = []
            has_priority_group = False
            for _group in group:
                if _group in groups:
                    if _group in self.priority_groups:
                        has_priority_group = True
                    changed_groups.append(_group)
                # TODO add a proper pluralization and support for latin characters ?
                if _group + "s" in groups:
                    changed_groups.append(_group + "s")
            if len(changed_groups) != 0:
                req.set(group=changed_groups)
            else:
                debug.write("No devices belong to group {}. Request aborted.".format(
                    group), 1, "IFTTT")
                return
            debug.write("Running function '{}' on group(s) {}".format(
                func, changed_groups), 0, "IFTTT")
            if self.config["IFTTT"].getboolean('AUTOMATIC_MODE'):
                req.set(auto_mode=True)
            elif not has_priority_group:
                debug.write(
                    "No priority groups called. Setting back to AUTO mode.", 0, "IFTTT")
                req.set(reset_mode=True)
            req(self.dm)

            if "delay" in postvars and int(postvars['delay'][0]) != 0:
                if func == "on":
                    req.set_colors(
                        [DEVICE_OFF] * len(self.dm), len(self.dm))
                elif func == "off":
                    req.set(skip_time=True)
                    req.set_colors(
                        [DEVICE_ON] * len(self.dm), len(self.dm))
                req.set(delay=int(postvars['delay'][0]) * 60)
                req.run(self.dm)

        try:
            # TODO rewrite this more elegantly
            post_action = postvars['postaction'][0]
            delay = int(postvars['delay'][0]) * 60 - 5

            if delay != 0:
                debug.write('Will run action {} in {} seconds'.format(
                    post_action, delay + 5), 0, "IFTTT")
                time.sleep(5)
                if post_action in self.config["IFTTT"]:
                    if not self.config["IFTTT"].getboolean('AUTOMATIC_MODE'):
                        os.system(
                            "./homeclient.py --delay {} {}".format(delay, self.config["IFTTT"][post_action]))
                    else:
                        os.system("./homeclient.py --delay {} --auto-mode {}".format(
                            delay, self.config["IFTTT"][post_action]))
                else:
                    #
                    # Complex delayed actions should be hardcoded here if needed
                    #
                    debug.write('Unknown action: {}'.format(
                        post_action), 1, "IFTTT")
        except KeyError:
            pass


class ifttt(Thread):
    def __init__(self, config, dm):
        Thread.__init__(self)
        self.config = config
        self.port = self.config['SERVER'].getint('VOICE_SERVER_PORT')
        self.protocol = self.config['IFTTT']['PROTOCOL']
        self.dm = dm
        if self.protocol == "https":
            self.key = self.config['IFTTT']['IFTTT_HTTPS_CERTS_KEY']
            self.cert = self.config['IFTTT']['IFTTT_HTTPS_CERTS_CERT']
        self.running = True

    def run(self):
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

    def stop(self):
        debug.write('Stopping.', 0, "IFTTT")
        self.running = False
        # Needs a last call to shut down properly
        try:
            requests.get("http://localhost:{}/".format(self.port))
        except requests.exceptions.ConnectionError:
            pass


def run(config, dm):
    runIFTTTServer(config, dm)

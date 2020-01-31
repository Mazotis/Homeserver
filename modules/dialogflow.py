#!/usr/bin/env python3
'''
    File name: dialogflow.py
    Author: Maxime Bergeron
    Date last modified: 31/01/2020
    Python Version: 3.7

    The Google DIALOGFLOW receiver module for the homeserver
'''

import json
import requests
import ssl
from core.common import *
from core.devicemanager import StateRequestObject
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


class DFServer(BaseHTTPRequestHandler):
    def __init__(self, config, dm, *args, **kwargs):
        self.config = config
        self.dm = dm
        super().__init__(*args, **kwargs)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        self._set_response()

    def do_POST(self):
        """ Receives and handles POST request """
        debug.write('Getting request', 0, "DIALOGFLOW")
        data_string = self.rfile.read(int(self.headers['Content-Length']))
        request = json.loads(data_string.decode('UTF-8'))
        self._set_response()
        action = request['queryResult']['parameters']['LightserverAction']
        groups = request['queryResult']['parameters']['LightserverGroups']

        req = StateRequestObject()
        req.initialize_dm(self.dm)
        if action == "on":
            req.set(on=True)
        else:
            req.set(off=True)

        if self.config.get_value('AUTOMATIC_MODE', bool):
            req.set(auto_mode=True)
        req.set(skip_time=True, group=' '.join(groups))

        debug.write('Running detected request: {}'.format(
            request), 0, "DIALOGFLOW")
        req()


class dialogflow(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.dm = dm
        self.init_from_config()

    def run(self):
        self.running = True
        debug.write('Getting lightserver POST requests on port {}'
                    .format(self.port), 0, "DIALOGFLOW")
        DialogflowServerPartial = partial(DFServer, self.config, self.dm)
        httpd = HTTPServer(('', self.port), DialogflowServerPartial)
        httpd.socket = ssl.wrap_socket(httpd.socket,
                                       keyfile=self.key,
                                       certfile=self.cert, server_side=True)
        try:
            while self.running:
                httpd.handle_request()
        finally:
            httpd.server_close()
            debug.write('Stopped.', 0, "DIALOGFLOW")
            return

    def init_from_config(self):
        self.config = getConfigHandler().set_section("DIALOGFLOW")
        self.port = self.config.get_value('VOICE_SERVER_PORT', int, "SERVER")
        self.key = self.config['DIALOGFLOW_HTTPS_CERTS_KEY']
        self.cert = self.config['DIALOGFLOW_HTTPS_CERTS_CERT']

    def stop(self):
        debug.write('Stopping.', 0, "DIALOGFLOW")
        self.running = False
        # Needs a last call to shut down properly
        try:
            requests.get("http://localhost:{}/".format(self.port))
        except requests.exceptions.ConnectionError:
            pass

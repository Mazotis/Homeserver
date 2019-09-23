#!/usr/bin/env python3
'''
    File name: dialogflow.py
    Author: Maxime Bergeron
    Date last modified: 22/08/2019
    Python Version: 3.5

    The Google DIALOGFLOW receiver module for the homeserver
'''

import json
import requests
import ssl
from devices.common import *
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

class DFServer(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        self._set_response()

    def do_POST(self):
        config = configparser.ConfigParser()
        config.read('home.ini')
        """ Receives and handles POST request """
        debug.write('Getting request', 0, "DIALOGFLOW")
        data_string = self.rfile.read(int(self.headers['Content-Length']))
        request = json.loads(data_string.decode('UTF-8'))
        self._set_response()
        action = request['queryResult']['parameters']['LightserverAction']
        groups = request['queryResult']['parameters']['LightserverGroups']
        if config['DIALOGFLOW'].getboolean('AUTOMATIC_MODE'):
            request = "./homeclient.py --{} --auto-mode --notime --group {}".format(action, ' '.join(groups))
        else:
            request = "./homeclient.py --{} --notime --group {}".format(action, ' '.join(groups))

        debug.write('Running detected request: {}'.format(request), 0, "DIALOGFLOW")
        os.system(request)


class runDFServer(Thread):
    def __init__(self, config):
        Thread.__init__(self)
        self.port = config['SERVER'].getint('VOICE_SERVER_PORT')
        self.key = config['DIALOGFLOW']['DIALOGFLOW_HTTPS_CERTS_KEY']
        self.cert = config['DIALOGFLOW']['DIALOGFLOW_HTTPS_CERTS_CERT']
        self.running = True

    def run(self):
        debug.write('Getting lightserver POST requests on port {}' \
                    .format(self.port), 0, "DIALOGFLOW")
        httpd = HTTPServer(('', self.port), DFServer)
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

    def stop(self):
        debug.write('Stopping.', 0, "DIALOGFLOW")
        self.running = False
        # Needs a last call to shut down properly
        try:
            _r = requests.get("http://localhost:{}/".format(self.port))
        except requests.exceptions.ConnectionError:
            pass
#!/usr/bin/env python3
'''
    File name: ifttt.py
    Author: Maxime Bergeron
    Date last modified: 18/09/2019
    Python Version: 3.5

    The IFTTT receiver module for the lightserver
'''

import hashlib
import requests
import ssl
import time
import unidecode
import urllib.parse
from devices.common import *
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

class IFTTTServer(BaseHTTPRequestHandler):
    def __init__(self, config, lm, *args, **kwargs):
        self.config = config
        self.lm = lm
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
        #content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        #postvars = urllib.parse.parse_qs(self.rfile.read(content_length), keep_blank_values=1, encoding='utf-8')
        content_length = int(self.headers['Content-Length'])
        postvars = urllib.parse.parse_qs(self.rfile.read(content_length).decode('UTF-8'), keep_blank_values=1)
        self._set_response()

        try:
            #TODO rewrite this more elegantly
            #TODO link directly to the LM server ?
            _hash = postvars['hash'][0]
            action = postvars['action'][0]
            if _hash != hashlib.sha512(bytes(SALT.encode('utf-8') + action.encode('utf-8'))).hexdigest():
                debug.write('Unauthorized action {}. Hash verification failed.'.format(action), 1, "IFTTT")

            if action in self.config["IFTTT"]:
                debug.write('Running action : {}'.format(self.config["IFTTT"][action]), 0, "IFTTT")
                os.system("./playclient.py " + self.config["IFTTT"][action])
            else:
                debug.write('Unknown action: {}'.format(action), 1, "IFTTT")

        except KeyError:
            #TODO hash group requests somehow or require HTTPS?
            func = postvars['function'][0]
            if func not in ["on", "off"]:
                debug.write("Function {} not defined. Request aborted.", 1, "IFTTT")
                return
            if func == "on":
                self.lm.set_colors([LIGHT_ON] * len(self.lm.devices))
            elif func == "off":
                self.lm.set_colors([LIGHT_OFF] * len(self.lm.devices))

            group = postvars['group'][0].split()
            group = [unidecode.unidecode(x) for x in group]
            groups = self.lm.get_all_groups()
            changed_groups = [] 
            for _group in group:
                if _group in groups:
                    changed_groups.append(_group)
                #TODO add a proper pluralization and support for latin characters ?
                if _group + "s" in groups:
                    changed_groups.append(_group + "s")
            if len(changed_groups) != 0:
                self.lm.get_group(changed_groups)
            else:
                debug.write("No devices belong to group {}. Request aborted.".format(group), 1, "IFTTT")
                return
            debug.write("Running function '{}' on group(s) {}".format(func, changed_groups), 0, "IFTTT")
            self.lm.run()

            if "delay" in postvars and int(postvars['delay'][0]) != 0:
                if func == "on":
                    self.lm.set_colors([LIGHT_OFF] * len(self.lm.devices))
                elif func == "off":
                    self.lm.set_colors([LIGHT_ON] * len(self.lm.devices))
                self.lm.get_group(changed_groups)
                self.lm.run(int(postvars['delay'][0])*60)


        try: 
            #TODO rewrite this more elegantly
            post_action = postvars['postaction'][0]
            delay = int(postvars['delay'][0])*60-5

            if delay != 0:
                debug.write('Will run action {} in {} seconds'.format(post_action, delay+5), 0, "IFTTT")
                time.sleep(5)
                if post_action in self.config["IFTTT"]:
                    os.system("./playclient.py --delay {} {}".format(delay, self.config["IFTTT"][post_action]))
                else:
                    #
                    # Complex delayed actions should be hardcoded here if needed
                    #
                    debug.write('Unknown action: {}'.format(post_action), 1, "IFTTT")
        except KeyError:
            pass


class runIFTTTServer(Thread):
    def __init__(self, config, lm):
        Thread.__init__(self)
        self.config = config
        self.port = self.config['SERVER'].getint('VOICE_SERVER_PORT')
        self.protocol = self.config['IFTTT']['PROTOCOL']
        self.lm = lm
        if self.protocol == "https":
            self.key = self.config['IFTTT']['IFTTT_HTTPS_CERTS_KEY']
            self.cert = self.config['IFTTT']['IFTTT_HTTPS_CERTS_CERT']
        self.running = True

    def run(self):
        debug.write('Getting lightserver POST requests on port {} using {} protocol' \
                    .format(self.port, self.protocol), 0, "IFTTT")
        IFTTTServerPartial = partial(IFTTTServer, self.config, self.lm)
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
        _r = requests.get("http://localhost:{}/".format(self.port))
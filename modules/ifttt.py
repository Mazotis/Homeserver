#!/usr/bin/env python3
'''
    File name: ifttt.py
    Author: Maxime Bergeron
    Date last modified: 22/08/2019
    Python Version: 3.5

    The IFTTT receiver module for the lightserver
'''

import hashlib
import requests
import time
import urllib.parse
from devices.common import *
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

class IFTTTServer(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_GET(self):
        self._set_response()

    def do_POST(self):
        config = configparser.ConfigParser()
        config.read('play.ini')
        """ Receives and handles POST request """
        SALT = config["IFTTT"]["SALT"]
        debug.write('[IFTTTServer] Getting request', 0)
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        postvars = urllib.parse.parse_qs(self.rfile.read(content_length), keep_blank_values=1)
        has_delayed_action = False
        self._set_response()
        try: 
            #TODO rewrite this more elegantly
            action = postvars[b'preaction'][0].decode('utf-8')
            post_action = postvars[b'postaction'][0].decode('utf-8')
            delay = int(postvars[b'delay'][0].decode('utf-8'))*60-5
            has_delayed_action = True
        except KeyError as ex:
            action = postvars[b'action'][0].decode('utf-8')
        _hash = postvars[b'hash'][0].decode('utf-8')

        if _hash == hashlib.sha512(bytes(SALT.encode('utf-8') + action.encode('utf-8'))).hexdigest():
            debug.write('IFTTTServer running action : {}'.format(action), 0)
            if action in config["IFTTT"]:
                debug.write('[IFTTTServer] Running action : {}'.format(config["IFTTT"][action]), 0)
                os.system("./playclient.py " + config["IFTTT"][action])
            else:
                #
                # Complex actions should be hardcoded here if needed
                #
                debug.write('[IFTTTServer] Unknown action : {}'.format(action), 1)
            time.sleep(5)
            if has_delayed_action:
                debug.write('IFTTTServer will run action {} in {} seconds'.format(post_action, delay+5), 0)
                if post_action in config["IFTTT"]:
                    os.system("./playclient.py --delay {} {}".format(delay, config["IFTTT"][post_action]))
                else:
                    #
                    # Complex delayed actions should be hardcoded here if needed
                    #
                    debug.write('[IFTTTServer] Unknown action : {}'.format(post_action), 1)
        else:
            debug.write('[IFTTTServer] Got unwanted request with action : {}'.format(action), 1)


class runIFTTTServer(Thread):
    def __init__(self, port):
        Thread.__init__(self)
        self.port = port
        self.running = True

    def run(self):
        debug.write('[IFTTTServer] Getting lightserver POST requests on port {}' \
                    .format(self.port), 0)
        httpd = HTTPServer(('', self.port), IFTTTServer)
        try:
            while self.running:
                httpd.handle_request()
        finally:
            httpd.server_close()
            debug.write('[IFTTTServer] Stopped.', 0)
            return

    def stop(self):
        debug.write('[IFTTTServer] Stopping.', 0)
        self.running = False
        # Needs a last call to shut down properly
        _r = requests.get("http://localhost:{}/".format(self.port))
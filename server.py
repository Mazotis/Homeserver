#!/usr/bin/env python3
"""
Simple playserver IFTTT server
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import cgi
import argparse
import os, sys
import socket
import time
import datetime
import json
import hashlib
from argparse import RawTextHelpFormatter
from __main__ import *

class S(BaseHTTPRequestHandler):
	def _set_response(self):
		self.send_response(200)
		self.send_header('Content-type', 'x-www-form-urlencoded')
		self.end_headers()

	def do_POST(self):
		content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
		postvars = cgi.parse_qs(self.rfile.read(content_length), keep_blank_values=1)
		action = postvars[b'action'][0].decode('utf-8')
		_hash = postvars[b'hash'][0].decode('utf-8')

		if (_hash == hashlib.sha512(bytes("mazout360".encode('utf-8') + action.encode('utf-8'))).hexdigest()):
			logging.info('Running action : {}\n'.format(action))
			if (action == "lumieres_salon_off"):
				os.system('./playclient.py --off --notime --priority 2 --group salon')
			elif (action == "lumieres_salon_on"):
				os.system('./playclient.py --on --notime --priority 2 --group salon')
			elif (action == "luminaire_passage_off"):
				os.system('./playclient.py --off --notime --priority 2 --group passage')
			elif (action == "luminaire_passage_on"):
				os.system('./playclient.py --on --notime --priority 2 --group passage')
			elif (action == "television_salon_on"):
				os.system('./playclient.py --tvon')
				time.sleep(2);
				os.system('/usr/sbin/ether-wake 4C:CC:6A:F4:79:EC -i br0')
			elif (action == "television_salon_off"):
				os.system('./playclient.py --tvoff')
			elif (action == "television_salon_restart"):
				os.system('./playclient.py --tvrestart')
			elif (action == "salon_close"):
				os.system('./playclient.py --tvoff --off --notime --priority 3 --group salon')
			elif (action == "luminaire_salon_off"):
				os.system('./playclient.py --off --notime --priority 2 --group salon --subgroup luminaire')
			elif (action == "luminaire_salon_on"):
				os.system('./playclient.py --on --notime --priority 2 --group salon --subgroup luminaire')
		else:
			logging.info('Unwanted request for action : {}\n'.format(action))

		self._set_response()
		self.wfile.write("POST request for {}".format(self.path).encode('utf-8'))

class lightManager(object):
	""" Methods for instanciating and managing BLE lightbulbs """
	@staticmethod
	def debugger(msg, level):
			levels = {0: "DEBUG", 1: "ERROR", 2: "FATAL"}
			debugtext = "(" + str(datetime.datetime.now().time()) + ") - [" + levels[level] + "] " + str(msg)
			print(debugtext)


def run(server_class=HTTPServer, handler_class=S, port=1234):
	logging.basicConfig(level=logging.INFO)
	server_address = ('', port)
	httpd = server_class(server_address, handler_class)
	logging.info('Starting httpd...\n')
	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		pass
	httpd.server_close()
	logging.info('Stopping httpd...\n')

if __name__ == '__main__':
	run()


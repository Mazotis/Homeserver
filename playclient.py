#!/usr/bin/env python3
'''
    File name: playclient.py
    Author: Maxime Bergeron
    Date last modified: 09/11/2018
    Python Version: 3.6

    The stripped-down version of play.py
'''
import argparse
import sys
import socket
import time
import datetime
import json
import os
from argparse import RawTextHelpFormatter
from __main__ import *

class lightManager(object):
	""" Methods for instanciating and managing BLE lightbulbs """
	@staticmethod
	def debugger(msg, level):
		levels = {0: "DEBUG", 1: "ERROR", 2: "FATAL"}
		debugtext = "(" + str(datetime.datetime.now().time()) + ") - [" + levels[level] + "] " + str(msg)
		print(debugtext)
		with open("./play.0.log", "a") as jfile:
			jfile.write(debugtext + "\n")

""" Script executed directly """
if __name__ == "__main__":
	if os.path.isfile("./play.0.log"):
		if os.path.isfile("./play.1.log"):
			if os.path.isfile("./play.2.log"):
				os.remove("./play.2.log")
			os.rename("./play.1.log", "./play.2.log")
		os.rename("./play.0.log", "./play.1.log")
	lm = lightManager()

	parser = argparse.ArgumentParser(description='BLE light bulbs manager script', formatter_class=RawTextHelpFormatter)
	parser.add_argument('hexvalues', metavar='N', type=str, nargs="*", help='color hex values for the lightbulbs (see list below)')
	parser.add_argument('--playbulb', metavar='P', type=str, nargs="*", help='Change playbulbs colors only')
	parser.add_argument('--milight', metavar='M', type=str, nargs="*", help='Change milights colors only')
	parser.add_argument('--priority', metavar='prio', type=int, nargs="?", default=1, help='Request priority from 1 to 3')
	parser.add_argument('--group', metavar='group', type=str, nargs="?", default=None, help='Apply light actions on specified light group')
	parser.add_argument('--subgroup', metavar='group', type=str, nargs="?", default=None, help='Apply light actions on specified light subgroup')	
	parser.add_argument('--notime', action='store_true', default=False, help='Skip the time check and run the script anyways')
	parser.add_argument('--on', action='store_true', default=False, help='Turn everything on')
	parser.add_argument('--off', action='store_true', default=False, help='Turn everything off')
	parser.add_argument('--toggle', action='store_true', default=False, help='Toggle all lights on/off')
	parser.add_argument('--server', action='store_true', default=False, help='Start as a socket server daemon')
	parser.add_argument('--journal', action='store_true', default=False, help='Enables file journaling')
	parser.add_argument('--tvon', action='store_true', default=False, help='Turns TV on')
	parser.add_argument('--tvoff', action='store_true', default=False, help='Turns TV off')
	parser.add_argument('--tvrestart', action='store_true', default=False, help='Reboots KODI')
	parser.add_argument('--stream-dev', metavar='str-dev', type=int, nargs="?", default=None, help='Stream colors directly to device id')
	parser.add_argument('--stream-group', metavar='str-grp', type=str, nargs="?", default=None, help='Stream colors directly to device group')

	args = parser.parse_args()

	if (args.server and (args.playbulb or args.milight or args.on or args.off or args.toggle or args.stream_dev or args.stream_group)):
		lightManager.debugger("You cannot start the daemon and send arguments at the same time.", 2)
		sys.exit()

	#todo do not hardcode this
	HOST = '192.168.1.50'
	PORT = 1111
	
	if args.stream_dev or args.stream_group:
		colorval = ""
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((HOST, PORT))
		if (args.stream_dev):
			s.sendall("0006".encode('utf-8'))
			s.sendall("stream".encode('utf-8'))
			s.sendall(('%04d' % args.stream_dev).encode('utf-8'))
			s.sendall(str(args.stream_dev).encode('utf-8'))
		else:
			s.sendall("0011".encode('utf-8'))
			s.sendall("streamgroup".encode('utf-8'))
			s.sendall(('%04d' % len(args.stream_group)).encode('utf-8'))
			s.sendall(args.stream_group.encode('utf-8'))
		while (colorval != "quit"):
			if (args.stream_dev):
				colorval = input("Set device {} to colorvalue ('quit' to exit): ".format(args.stream_dev))
			else:
				colorval = input("Set group '{}' to colorvalue ('quit' to exit): ".format(args.stream_group))
			try:
				if (colorval == "quit"):
					s.sendall("0008".encode('utf-8'))
					s.sendall("nostream".encode('utf-8'))
					break
				s.sendall(('%04d' % len(colorval)).encode('utf-8'))
				s.sendall(colorval.encode('utf-8'))
			except BrokenPipeError:
				if (colorval != "quit"):
					s.close()
					s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					s.connect((HOST, PORT))
					if (args.stream_dev):
						s.sendall("0006".encode('utf-8'))
						s.sendall("stream".encode('utf-8'))
						s.sendall(('%04d' % args.stream_dev).encode('utf-8'))
						s.sendall(str(args.stream_dev).encode('utf-8'))
					else:
						s.sendall("0011".encode('utf-8'))
						s.sendall("streamgroup".encode('utf-8'))
						s.sendall(('%04d' % len(args.stream_group)).encode('utf-8'))
						s.sendall(args.stream_group.encode('utf-8'))
					s.sendall(('%04d' % len(colorval)).encode('utf-8'))
					s.sendall(colorval.encode('utf-8'))
					continue
		s.close()
	else:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((HOST, PORT))
		#todo report connection errors or allow feedback response
		lightManager.debugger('Connecting with lightmanager daemon', 0)
		lightManager.debugger('Sending request: ' + json.dumps(vars(args)), 0)
		s.sendall("1024".encode('utf-8'))
		s.sendall(json.dumps(vars(args)).encode('utf-8'))
		s.close()
		sys.exit()

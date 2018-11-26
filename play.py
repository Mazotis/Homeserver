#!/usr/bin/env python3
'''
    File name: play.py
    Author: Maxime Bergeron
    Date last modified: 15/11/2018
    Python Version: 3.7

    A python websocket server/client to control various cheap IoT RGB BLE lightbulbs and HDMI-CEC-to-TV RPi3
'''
import os
import os.path
import sys
import argparse
import time
import datetime
import socket
import threading
import functools
import configparser
import traceback
from multiprocessing.pool import ThreadPool
import json
import signal
import bluepy.btle as ble
from queue import Queue
from argparse import RawTextHelpFormatter
from argparse import Namespace
from __main__ import *

journaling = False #do not edit - use the --journal option

###

def connect_ble(f):
	@functools.wraps(f)
	def _conn_wrap(self, *args):
		if (self._connection is None):
			try:
				lightManager.debugger("CONnecting to device ({}) {}".format(self.deviceType, self.device), 0)
				connection = ble.Peripheral(self.device)
				self._connection = connection.withDelegate(self)
			except Exception as ex:
				lightManager.debugger("Device ({}) {} connection failed. Exception: {}".format(self.deviceType, self.device, ex), 1)
				self._connection = None
		return f(self, *args)
	return _conn_wrap

###
# CONSTANTS
LIGHT_SKIP = "-1"
LIGHT_OFF = "0"
LIGHT_ON = "1"
###

class lightServer(object):
	def __init__(self, lm, host, port):
		self.host = host
		self.port = port
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sock.bind((self.host, self.port))
		signal.signal(signal.SIGTERM, self.removeServer)
		lm.setColors([LIGHT_ON] * len(lm.devices))
		lm.run()

	def listen(self):
		lightManager.debugger('Server started', 0)
		self.sock.listen(5)
		while True:
			client, address = self.sock.accept()
			lightManager.debugger('Connected with ' + address[0] + ':' + str(address[1]), 0)
			client.settimeout(30)
			threading.Thread(target = self.listenToClient,args = (client,address)).start()

	def listenToClient(self, client, address):
		olddata = None
		streamingdev = False
		streaminggrp = False
		streaming_id = None
		try:
			while True:
				msize = int(client.recv(4).decode('utf-8'))
				#lightManager.debugger("Set message size {}".format(msize), 0)
				data = client.recv(msize)
				if data:
					if (data.decode('utf-8') == "getstate"):
						lightManager.debugger('Sending lightserver status', 0)
						client.send(str.encode(str(lm.state)))
						break
					if (data.decode('utf-8') == "stream"):
						lightManager.debugger('Starting streaming mode', 0)
						streamingdev = True
						continue
					if (data.decode('utf-8') == "streamgroup"):
						lightManager.debugger('Starting group streaming mode', 0)
						streaminggrp = True
						continue
					if (data.decode('utf-8') == "nostream"):
						lightManager.debugger('Ending streaming mode', 0)
						streamingdev = False
						streaminggrp = False
						streaming_id = None
						break
					if streamingdev:
						if (streaming_id is None):
							streaming_id = int(data.decode('utf-8'))
							lightManager.debugger('Set streaming devid to {}'.format(streaming_id), 0)
							continue
						lightManager.debugger("Sending request to devid {} for color: {}".format(streaming_id, data.decode('utf-8')), 0)
						lm.setLightStream(streaming_id, data.decode('utf-8'), False)
						continue
					if streaminggrp:
						if (streaming_id is None):
							streaming_id = data.decode('utf-8')
							lightManager.debugger('Set streaming group to {}'.format(streaming_id), 0)
							continue
						lightManager.debugger("Sending request to group '{}' for color: {}".format(streaming_id, data.decode('utf-8')), 0)
						lm.setLightStream(streaming_id, data.decode('utf-8'), True)
						continue
					try:
						args = self._sanitize(json.loads(data.decode('utf-8')))
					except: #fallback - data is not formatted
						lightManager.debugger("Error - improperly formatted JSON", 2)
						break
					lightManager.debugger('Change of lights requested with args: ' + str(args), 0)
					self._validate_and_execute_req(args)
					break

		except socket.timeout:
			pass

		except Exception as ex:
			lightManager.debugger('Unhandled exception of type {}: {}, {}'.format(type(ex), ex, ''.join(traceback.format_tb(ex.__traceback__))), 2)

		finally:
			lightManager.debugger('Closing connection.', 0)
			lm.setLock(0)
			lm.reinit()
			client.close()
			return False

	def removeServer(self, signal, frame):
		lightManager.debugger("Closing down server and lights.", 0)
		lm.skipTime(0)
		lm.setColors([LIGHT_OFF] * len(lm.devices))
		lm.run()
		time.sleep(3)
		self.sock.close()

	def _validate_and_execute_req(self, args):
		lightManager.debugger("Validating arguments", 0)
		if (args["hexvalues"] and (args["playbulb"] or args["milight"])):
			lightManager.debugger("change Got color hexvalues for milights and/or playbulbs and/or both devices in the same request, which is not supported. Use '" + sys.argv[0] + " -h' for help. Quitting", 2)
			return;
		if (args["tvon"] and args["tvoff"]):
			lightManager.debugger("Cannot ON and OFF the TV in the same request. Quitting.", 2)
			return;			
		if len(args["hexvalues"]) != len(lm.devices) and not any([args["notime"],args["off"], args["on"],args["playbulb"],args["milight"],args["toggle"],args["tvon"],args["tvoff"],args["tvrestart"]]):
			lightManager.debugger("Got " + str(len(args["hexvalues"])) + " color hexvalues, " + str(len(lm.devices)) + " expected. Use '" + sys.argv[0] + " -h' for help. Quitting", 2)
			return;
		if args["tvon"]:
			lightManager.debugger("Setting TV on", 0)
			self._setTv(1)
			return; #Do not accept any more requests for now.
		if args["tvoff"]:
			lightManager.debugger("Setting TV off", 0)
			self._setTv(0)
		if args["tvrestart"]:
			lightManager.debugger("Rebooting KODI", 0)
			self._setTv(2)
			return;
		if args["priority"]:
			lm.priority = args["priority"]
		if args["hexvalues"]:
			lightManager.debugger("Received color hexvalues length " + str(len(args["hexvalues"])) + " for " + str(len(lm.devices)) + " devices", 0) 
			lm.setColors(args["hexvalues"])
		else:
			if args["playbulb"] is not None:
				lightManager.debugger("Received playbulb change request", 0) 
				lm.setTypedColors(args["playbulb"], "Playbulb")
			if args["milight"] is not None:
				lightManager.debugger("Received milight change request", 0) 
				lm.setTypedColors(args["milight"], "Milight")
			if args["off"]:
				lightManager.debugger("Received OFF change request", 0) 
				lm.setColors([LIGHT_OFF] * len(lm.devices))
			if args["on"]:
				lightManager.debugger("Received ON change request", 0) 
				lm.setColors([LIGHT_ON] * len(lm.devices))
			if args["toggle"]:
				lightManager.debugger("Received TOGGLE change request", 0) 
				lm.setColors(lm.getToggle())
		if args["notime"] or args["off"]:
			lm.skipTime(0)
		if args["group"] is not None:
			lm.setGroup(args["group"], args["subgroup"])
		lightManager.debugger("Arguments are OK", 0)
		lm.run()
		return;

	def _sanitize(self, args):
		if "hexvalues" not in args:
			args["hexvalues"] = [];
		if "off" not in args:
			args["off"] = False;
		if "tvrestart" not in args:
			args["tvrestart"] = False;
		if "on" not in args:
			args["on"] = False;
		if "tvon" not in args:
			args["tvon"] = False;
		if "toggle" not in args:
			args["toggle"] = False;
		if "playbulb" not in args:
			args["playbulb"] = None;
		if "milight" not in args:
			args["milight"] = None;
		if "server" not in args:
			args["server"] = False;
		if "journal" not in args:
			args["journal"] = False;
		if "notime" not in args:
			args["notime"] = False;
		if "tvoff" not in args:
			args["tvoff"] = False;
		if "priority" in args and args["priority"] is None:
			args["priority"] = 1;
		if "priority" not in args:
			args["priority"] = 1;
		if "group" not in args:
			args["group"] = None;
		if "subgroup" not in args:
			args["subgroup"] = None;
		if type(args["playbulb"]).__name__ == "str":
			lightManager.debugger('Converting values to lists for playbulb', 0)
			args["playbulb"] = args["playbulb"].replace("'","").split(',')
		if type(args["milight"]).__name__ == "str":
			lightManager.debugger('Converting values to lists for milight', 0)
			args["milight"] = args["milight"].replace("'","").split(',')
		return args

	def _setTv(self, value):
		if (value == 0): ## TV OFF
			os.system("echo 'standby 0' | cec-client -s")
			os.system("ssh kodi@192.168.1.200 'sudo shutdown now'")
			lightManager.debugger('Set the TV and KODI to OFF', 0)
		elif (value == 1): ## TV ON
			os.system("echo 'on 0' | cec-client -s")
			lightManager.debugger('Set the TV ON', 0)
		elif (value == 2): ## TV RESTART		
			os.system("ssh kodi@192.168.1.200 'sudo reboot'")
			lightManager.debugger('Restarted KODI', 0)

class lightManager(object):
	""" Methods for instanciating and managing BLE lightbulbs """
	def __init__(self, config = None):
		self.config = config
		## TWEAKABLES ##
		self.devices = []
		i = 0
		while True:
			try:
				if (self.config["DEVICE"+str(i)]["TYPE"] == "Playbulb"):
					self.devices.append(Playbulb(i, self.config["DEVICE"+str(i)]["ADDRESS"], self.config["DEVICE"+str(i)]["DESCRIPTION"], self.config["DEVICE"+str(i)]["GROUP"], self.config["DEVICE"+str(i)]["SUBGROUP"], self.config["DEVICE"+str(i)]["DEFAULT_INTENSITY"], self))
					lightManager.debugger("Created device Playbulb {}. Description: {}".format(self.config["DEVICE"+str(i)]["ADDRESS"],self.config["DEVICE"+str(i)]["DESCRIPTION"]) , 0)
				elif (self.config["DEVICE"+str(i)]["TYPE"] == "Milight"):
					self.devices.append(Milight(i, self.config["DEVICE"+str(i)]["ADDRESS"], self.config["DEVICE"+str(i)]["ID1"], self.config["DEVICE"+str(i)]["ID2"], self.config["DEVICE"+str(i)]["DESCRIPTION"], self.config["DEVICE"+str(i)]["GROUP"], self.config["DEVICE"+str(i)]["SUBGROUP"], self))
					lightManager.debugger("Created device Milight {}. Description: {}".format(self.config["DEVICE"+str(i)]["ADDRESS"],self.config["DEVICE"+str(i)]["DESCRIPTION"]) , 0)
				else:
					lightManager.debugger('Unsupported device type {}'.format(self.config["DEVICE"+str(i)]["TYPE"]), 1)
			except KeyError:
				break
			i = i + 1

		#todo allow reporting of device state to the lightserver
		self.starttime = datetime.time(18,00) #Light change minimal time
		self.skiptime = 0
		self.queue = Queue()
		self.colors = [LIGHT_OFF] * len(self.devices)
		self.setLock(0)
		self.lockcount = 0
		self.journaling = False
		self.priority = 0
		self.threaded = False

	def startThreaded(self):
		self.threaded = True

	def skipTime(self, serverwide = 0):
		if (serverwide):
			lightManager.debugger("Skipping time check for all requests", 0)
			self.starttime = None
		else:
			lightManager.debugger("Skipping time check", 0)
			self.skiptime = 1

	def setColors(self, color):
		self.colors = color

	def setGroup(self, group, subgroup):
		for _cnt,device in enumerate(self.devices):
			if (device.group != group):
				lightManager.debugger("Skipping device {} as it does not belong in the '{}' group".format(device.device, group), 0)
				self.colors[_cnt] = LIGHT_SKIP
			else:
				if (subgroup is not None and device.subgroup != subgroup):
					lightManager.debugger("Skipping device {} as it does not belong in the '{}' subgroup".format(device.device, subgroup), 0)
					self.colors[_cnt] = LIGHT_SKIP

	def getToggle(self):
		colors = [LIGHT_ON] * len(lm.devices)
		i = 0
		for color in self.getState():
			if color != LIGHT_OFF:
				colors = [LIGHT_OFF] * len(lm.devices)
			i = i+1
		return colors

	def setTypedColors(self, colorargs, atype):
		cvals = self._getTypeIndex(atype)
		if (cvals[0] != len(colorargs)):
			lightManager.debugger("Received color hexvalues length " + str(len(colorargs)) + " for " + str(cvals[0]) + " devices. Quitting", 2)
			return;
		self.colors[cvals[1]:cvals[1]+cvals[0]] = colorargs

	def run(self):
		if(self._checkTime()):
			self.queue.put(self.colors)
			#todo Manage locking out when the run thread hangs
			lightManager.debugger("Locked status: " + str(self.locked), 0)
			if not self.locked or self.lockcount == 2:
				self._setLights()
			else:
				self.lockcount = self.lockcount + 1

	def descriptions(self):
		desctext = ""
		i = 1
		for obj in self.devices:
			if type(obj) == Playbulb or type(obj) == Milight:
				desctext += str(i) + " - " + obj.descriptions() + "\n"
			else:
				desctext += str(i) + " - " + "Unknown bulb type\n"
			i += 1
		return desctext

	def enableJournaling(self):
		global journaling
		journaling = True
		#todo Dynamic history limits
		if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play.0.log"):
			if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play.1.log"):
				if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play.2.log"):
					os.remove(self.config['SERVER']['JOURNAL_DIR'] + "/play.2.log")
				os.rename(self.config['SERVER']['JOURNAL_DIR'] + "/play.1.log", self.config['SERVER']['JOURNAL_DIR'] + "/play.2.log")
			os.rename(self.config['SERVER']['JOURNAL_DIR'] + "/play.0.log", self.config['SERVER']['JOURNAL_DIR'] + "/play.1.log")

	def setLock(self, isLocked):
		self.locked = isLocked

	def getState(self, devid = None):
		states = [None] * len(self.devices)
		for _cnt, dev in enumerate(self.devices):
			states[_cnt] = dev.getState()
		if devid is not None:
			return states[devid]
		else:
			return states

	def setLightStream(self, devid, color, is_group):
		if (is_group):
			for device in self.devices:
				if (device.group == devid):
					cnt = 0
					_color = device.convert(color)
					while True:
						if (cnt == 4):
							break
						if (device.color(_color,3)):
							break
						time.sleep(0.3)
						cnt = cnt + 1
		else:
			cnt = 0
			_color = device.convert(color)
			while True:
				if (cnt == 4):
					break
				if (self.devices[devid].color(_color,3)):
					break
				time.sleep(0.3)
				cnt = cnt + 1
		self.reinit()

	def reinit(self):
		# Resets the Success bool to False to force a light change
		i = 0
		while i < len(self.devices):
			self.devices[i].reinit()
			i += 1

	def _setLights(self):
		""" Threading du changement des couleurs """
		lightManager.debugger("Running a change of lights (priority level: {}, lock: {})...".format(self.priority, self.locked), 0)
		try:
			self.lockcount = 0
			firstran = False
			if self.threaded:
				lightThreads = [None] * len(self.devices)
				lightPool = ThreadPool(processes=4)
			while not self.queue.empty():
				colors = None
				try:
					if firstran:
						lightManager.debugger("Getting remainder of queue", 0)
						self.reinit()
					colors = self.queue.get() #todo Check performance
					lightManager.debugger("Changing colors to " + str(colors) + " from state " + str(self.getState()), 0)
					self.setLock(1)
					i = 0
					tries = 0
					firstran = True

					while i < len(self.devices):
						_state = self.getState(i)
						_color = self.devices[i].convert(colors[i])

						if (not self.devices[i].success):
							lightManager.debugger("DEVICE: {}, REQUESTED COLOR: {}, FROM STATE: {}, PRIORITY: {}".format(self.devices[i].device, _color, _state, self.devices[i].priority), 0)
							if self.threaded:
								lightThreads[i] = lightPool.apply_async(self.devices[i].color, args=(_color,self.priority,))
							else:
								self.devices[i].color(_color,self.priority)
						i += 1

						if (i == len(self.devices)):
							if (self.threaded):
								lightManager.debugger("Awaiting results", 0)
								for _cnt, _thread in enumerate(lightThreads):
									if (_thread is not None):
										try:
											if (not _thread.get(5)):
												i = 0
										except:
											i = 0
								tries = tries + 1
								if (tries == 5):
									break
							else:
								for _cnt, _dev in enumerate(self.devices):
									_state = self.getState(_cnt)
									if colors[_cnt] != _state or (colors[_cnt] == self.devices[_cnt].convert(LIGHT_OFF) and _state == self.devices[_cnt].convert(LIGHT_OFF)):
										i = 0
								tries = tries + 1
								if (tries == 5):
									break

					if self.threaded:
						lightPool.close()

				except Queue.queue.Empty:
					lightManager.debugger("Nothing in queue", 0)
					pass

				finally:
					if colors:
						self.queue.task_done()

		except Exception as e:
			lightManager.debugger("Unhandled error of type {}, Args: {} ".format(type(e).__name__, e.args), 3)

		finally:
			self.reinit()
			self.setLock(0)

		lightManager.debugger("Change of lights completed.", 0)

	def _checkTime(self, hours = 3, minutes = 0):
		#todo Check if we keep this...
		if (self.skiptime or self.starttime is None):
			self.skiptime = 0
			return 1
		else:
			if datetime.time(6,00) < datetime.datetime.now().time() < self.starttime:
				lightManager.debugger("Too soon, no change of light required", 0)
				return 0;
			else:
				return 1;

	def _getTypeIndex(self, atype):
		i = 0
		count = 0
		firstindex = 0
		for obj in self.devices:
			if type(obj) == eval(atype):
				if count == 0: 
					firstindex = i
				count += 1
			i += 1
		if count == 0:
			raise Exception('Invalid bulb type given. Quitting')
		return [count, firstindex]

	@staticmethod
	def debugger(msg, level):
		playconfig = configparser.ConfigParser()
		playconfig.read('play.ini')
		levels = {0: "DEBUG", 1: "ERROR", 2: "FATAL"}
		debugtext = "(" + str(datetime.datetime.now().time()) + ") - [" + levels[level] + "] " + str(msg)
		print(debugtext)
		if journaling:
			with open(playconfig['SERVER']['JOURNAL_DIR'] + "/play.0.log", "a") as jfile:
				jfile.write(debugtext + "\n")


class Bulb(object):
	""" Global bulb functions and variables """
	def __init__(self, devid, device, description, group, subgroup, server):
		self.devid = devid
		self.device = device
		self.description = description
		self.success = False
		self._connection = None
		self.group = group
		self.subgroup = subgroup
		self.server = server
		self.priority = 0

	def reinit(self):
		self.success = False

	def getState(self):
		return self.state

	def disconnect(self):
		try:
			if (self._connection is not None):
				lightManager.debugger("DISconnecting from device {}".format(self.device), 0)
				self._connection.disconnect()
		except ble.BTLEException:
			lightManager.debugger("Device ({}) {} disconnection failed. Already disconnected?".format(self.deviceType, self.device), 1)
			pass

		self._connection = None


lock = threading.Lock()
class Playbulb(Bulb):
	""" Methods for driving a rainbow BLE lightbulb """
	def __init__(self, devid, device, description, group, subgroup, intensity, server):
		super().__init__(devid, device, description, group, subgroup, server)
		self.deviceType = "Playbulb"
		#todo get actual color at instanciation
		self.state = "00000000"
		self.intensity = intensity

	def convert(self, color):
		if (color == LIGHT_OFF):
			color = "00000000"
		elif (color == LIGHT_ON):
			color = self.intensity
		return color

	def color(self, color, priority):
		if (len(color) not in (1,8) and color != self.convert(LIGHT_SKIP)):
			lightManager.debugger("Unhandled color format {}".format(color), 1)
			return True
		if (self.success):
			return True
		if (color == self.convert(LIGHT_SKIP)):
			self.success = True
			return True
		if (self.priority > priority):
			lightManager.debugger("Playbulb bulb {} is set with higher priority ({}), skipping.".format(self.device, self.priority), 0)
			self.success = True
			return True
		if (priority == 3):
			self.priority = 1
		else:
			self.priority = priority
		if (self.state == color and color != self.convert(LIGHT_OFF)):
			self.success = True
			lightManager.debugger("Bulb {} is already of the requested color, skipping.".format(self.device), 0)
			return True
		lightManager.debugger("Changing playbulb " + str(self.device) + " color to " + color, 0)
		if (not self._write(color)): return False
		return True

	def descriptions(self):
		desctext = "[Playbulb MAC: " + self.device + "] " + self.description
		return desctext

	@connect_ble
	def _write(self, color):
		try:
			if (self._connection is not None):
				with lock:
					#NOT YET STABLE
#					state = self.server.getState(self.devid)
#					if (state == "0"):
#						state = "00000000"
#					elif (state == "1"):
#						state = self.intensity
#					lightManager.debugger("Got color: {} and state: {}".format(color, state), 0)
#					delta_w = (int(color[0:2]) - int(state[0:2]))/20
#					delta_r = (int(color[2:4]) - int(state[2:4]))/20
#					delta_g = (int(color[4:6]) - int(state[4:6]))/20
#					delta_b = (int(color[6:8]) - int(state[6:8]))/20
#					lightManager.debugger("deltaw: {}, deltar: {}, deltag: {}, deltab: {}".format(delta_w, delta_r, delta_g, delta_b), 0)
#					for _iter in range(20):
#						if (int(_iter*delta_w) != 0 and int(_iter*delta_r) != 0 and int(_iter*delta_g) != 0 and int(_iter*delta_b) != 0):
#							deltacolor = str(int(color[0:2]) + int(_iter*delta_w)) + str(int(color[2:4]) + int(_iter*delta_r)) + str(int(color[4:6]) + int(_iter*delta_g)) + str(int(color[6:8]) + int(_iter*delta_b))
#							self._connection.getCharacteristics(uuid="0000fffc-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(deltacolor))
#							time.sleep(0.5)



					self._connection.getCharacteristics(uuid="0000fffc-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(color))
					self.state = color
		
					#Prebuilt animations: blink=00, pulse=01, hard rainbow=02, smooth rainbow=03, candle=04
					#self._connection.getCharacteristics(uuid="0000fffb-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(color+"02ffffff"))
					self.success = True
					lightManager.debugger("Playbulb " + str(self.device) + " color changed to " + color, 0)
					return True
			else:
				lightManager.debugger("Connection error to device (playbulb) " + str(self.device) + ". Retrying", 1)
				time.sleep(0.2)
				return False				
		except Exception as ex:
			#todo manage "overwritten" thread by queued requests
			lightManager.debugger("Unhandled response. Thread died?\n{}".format(ex), 0)
			self.disconnect()
			return False


class Milight(Bulb):
	""" Methods for driving a milight BLE lightbulb """
	def __init__(self, devid, device, id1, id2, description, group, subgroup, server):
		super().__init__(devid, device, description, group, subgroup, server)
		self.deviceType = "Milight"
		self.id1 = id1
		self.id2 = id2
		self.state = "0"

	def turnon(self):
		return self._write(self.getquery(32, 161, 1, self.id1, self.id2), "1")

	def turnoff(self):
		return self._write(self.getquery(32, 161, 2, self.id1, self.id2), "0")

	def turnOnAndSetColor(self, color):
		if (not self.turnon()): return False
		return self._write(self.getquery(45, 161, 4, self.id1, self.id2, color, 2, 50), color)

	def turnOnAndDimOn(self, color):
		if (not self.turnon()): return False
		return self.dimon(color)

	def dimon(self, color):
		return self._write(self.getquery(20, 161, 5, self.id1, self.id2, 200, 4, 50), color)

	def convert(self, color):
		#todo rrggbb to ...this format...
		return color

	def color(self, color, priority):
		if (len(color) > 3):
			lightManager.debugger("Unhandled color format {}".format(color), 1)
			return True
		if (self.success):
			return True
		if (color == self.convert(LIGHT_SKIP)):
			self.success = True
			return True
		if (self.priority > priority):
			lightManager.debugger("Milight bulb {} is set with higher priority ({}), skipping.".format(self.device, self.priority), 0)
			self.success = True
			return True
		if (priority == 3):
			self.priority = 1
		else:
			self.priority = priority
		mlTarget = None
		if (color == self.convert(LIGHT_OFF)):
			lightManager.debugger("Turning milight " + self.device + " off", 0)
			if (not self.turnoff()): return False
			return True
		elif (self.state == color):
			self.success = True
			lightManager.debugger("Device (milight) " + str(self.device) + " is already of the requested color, skipping.", 0)
			return True
		elif (color == LIGHT_ON):
			lightManager.debugger("Turning milight " + self.device + " on", 0)
			if (not self.turnOnAndDimOn(color)): 
				return False
			return True
		else:
			lightManager.debugger("Changing milight " + self.device + " color", 0)
			if (not self.turnOnAndSetColor(color)): return False
			return True

	def getquery(self, value1, value2, value3, id1, id2, value4 = 0, value5 = 2, value6 = 0):
		"""
		Generate encrypted request string. 
		ON (value3 = 1)/OFF (value3 = 2): value1 = 32, value2 = 161
		CHANGE COLOR: value1 = 45, value2 = 161, value3 = 4, value4 = colorid
		"""
		packet = self._createcommand("[" + str(value1) + ", " + str(value2) + ", " + str(id1) + ", " + str(id2) + ", " + str(value5) + ", " + str(value3) + ", " + str(value4) + ", " + str(value6) + ", 0, 0, 0]")
		return packet

	def descriptions(self):
		desctext = "[Milight MAC: " + self.device + ", ID1: " + self.id1 + ", ID2: " + self.id2 + "] " + self.description
		return desctext

	@connect_ble
	def _write(self, command, color):
		try:
			if (self._connection is not None):
				with lock:
					self._connection.getCharacteristics(uuid="00001001-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(command.replace('\n', '').replace('\r', '')))
					self.success = True
					self.state = color
					return True
			else:
				lightManager.debugger("Connection error to device (milight) " + str(self.device) + ". Retrying", 1)
				return False
		except:
			lightManager.debugger("Error sending data to device (milight) " + str(self.device) + ". Retrying", 1)
			self._connection = None		
			return False

	def _createcommand(self, bledata):
		input = eval(bledata)
		k = input[0]
		j = 0
		i = 0
		while i <= 10:
			j += input[i] & 0xff
			i += 1
		checksum = ((( (k ^ j) & 0xff) + 131) & 0xff)
		xored = [(s&0xff)^k for s in input]
		offs = [0, 16, 24, 1, 129, 55, 169, 87, 35, 70, 23, 0]
		adds = [x+y&0xff for(x,y) in zip(xored, offs)]
		adds[0] = k
		adds.append(checksum)
		hexs = [hex(x) for x in adds]
		hexs = [x[2:] for x in hexs]
		hexs = [x.zfill(2) for x in hexs]

		return ''.join(hexs)


""" Script executed directly """
if __name__ == "__main__":
	#todo externalize?
	playconfig = configparser.ConfigParser()
	playconfig.read('play.ini')
	lm = lightManager(playconfig)

	parser = argparse.ArgumentParser(description='BLE light bulbs manager script', epilog=lm.descriptions(), formatter_class=RawTextHelpFormatter)
	parser.add_argument('hexvalues', metavar='N', type=str, nargs="*",
					help='color hex values for the lightbulbs (see list below)')
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
	parser.add_argument('--threaded', action='store_true', default=False, help='Starts the server daemon with threaded light change requests')
	parser.add_argument('--journal', action='store_true', default=False, help='Enables file journaling')
	parser.add_argument('--tvon', action='store_true', default=False, help='Turns TV on')
	parser.add_argument('--tvoff', action='store_true', default=False, help='Turns TV off')
	parser.add_argument('--tvrestart', action='store_true', default=False, help='Reboots KODI')
	parser.add_argument('--stream-dev', metavar='str-dev', type=int, nargs="?", default=None, help='Stream colors directly to device id')
	parser.add_argument('--stream-group', metavar='str-grp', type=str, nargs="?", default=None, help='Stream colors directly to device group')

	args = parser.parse_args()

	if (args.server and (args.playbulb or args.milight or args.on or args.off or args.toggle or args.stream_dev or args.stream_group)):
		lightManager.debugger("You cannot start the daemon and send arguments at the same time. Quitting.", 2)
		sys.exit()

	if (args.stream_dev and args.stream_group):
		lightManager.debugger("You cannot stream data to both devices and groups. Quitting.", 2)
		sys.exit()

	if args.journal:
		lm.enableJournaling()

	if args.server:
		if args.notime:
			lm.skipTime(1)
		if args.threaded:
			lm.startThreaded()
		lightServer(lm,playconfig['SERVER']['HOST'],int(playconfig['SERVER']['PORT'])).listen()

	elif args.stream_dev or args.stream_group:
		colorval = ""
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((playconfig['SERVER']['HOST'],int(playconfig['SERVER']['PORT'])))
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
					s.connect((playconfig['SERVER']['HOST'],int(playconfig['SERVER']['PORT'])))
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
		s.connect((playconfig['SERVER']['HOST'],int(playconfig['SERVER']['PORT'])))
		#todo report connection errors or allow feedback response
		lightManager.debugger('Connecting with lightmanager daemon', 0)
		lightManager.debugger('Sending request: ' + json.dumps(vars(args)), 0)
		s.sendall("1024".encode('utf-8'))
		s.sendall(json.dumps(vars(args)).encode('utf-8'))
		s.close()

	sys.exit()

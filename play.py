#!/usr/bin/env python3
'''
    File name: play.py
    Author: Maxime Bergeron
    Date last modified: 04/27/2018
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
			except:
				lightManager.debugger("Device ({}) {} connection failed.".format(self.deviceType, self.device), 1)
				self._connection = None
		return f(self, *args)
	return _conn_wrap

###

class lightServer(object):
	def __init__(self, lm, host, port):
		self.host = host
		self.port = port
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sock.bind((self.host, self.port))
		signal.signal(signal.SIGTERM, self.removeServer)
		lm.setColors(["1"] * len(lm.devices))
		lm.run()

	def listen(self):
		lightManager.debugger('Server started', 0)
		self.sock.listen(5)
		while True:
			client, address = self.sock.accept()
			lightManager.debugger('Connected with ' + address[0] + ':' + str(address[1]), 0)
			client.settimeout(10)
			threading.Thread(target = self.listenToClient,args = (client,address)).start()

	def listenToClient(self, client, address):
		size = 1024
		try:
			while True:
				data = client.recv(size)
				if data:
					if data.decode('utf-8') == "getstate":
						client.send(str.encode(str(lm.state)))
						client.close()
						break
					try:
						args = self._sanitize(json.loads(data.decode('utf-8')))
					except: #fallback - data is not formatted
						lightManager.debugger("Error - improperly formatted JSON", 2)
						break
					lightManager.debugger('Change of lights requested with args: ' + str(args), 0)
					self._validate_and_execute_req(args)
					break
		finally:
			lightManager.debugger('Closing connection.', 0)
			lm.setLock(0)
			client.close()
			return False

	def removeServer(self, signal, frame):
		lightManager.debugger("Closing down server and lights.", 0)
		lm.skipTime(0)
		lm.setColors(["0"] * len(lm.devices))
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
		if (args["priority"] < lm.priority):
			lightManager.debugger("Request priority too low, skipping light change", 0)
			return;
		else:
			if (args["priority"] == 3):
				# Priority 3 runs the light change then resets the priority level
				lm.priority = 1
			else:
				lm.priority = args["priority"]
		if args["hexvalues"]:
			lightManager.debugger("Received color hexvalues length " + str(len(args["hexvalues"])) + " for " + str(len(lm.devices)) + " devices", 0) 
			lm.setColors(args["hexvalues"])
		else:
			if args["playbulb"] is not None:
				lightManager.debugger("Received playbulb change request", 0) 
				lm.setTypedColors(args["playbulb"], "playbulb")
			if args["milight"] is not None:
				lightManager.debugger("Received milight change request", 0) 
				lm.setTypedColors(args["milight"], "milight")
			if args["off"]:
				lightManager.debugger("Received OFF change request", 0) 
				lm.setColors(["0"] * len(lm.devices))
			if args["on"]:
				lightManager.debugger("Received ON change request", 0) 
				lm.setColors(["1"] * len(lm.devices))
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
	def __init__(self):
		## TWEAKABLES ##
		self.devices = []
		#todo Dynamic instanciation
		#todo allow reporting of device state to the lightserver
		#
		# DeviceType(MAC_ADDRESS, DESCRIPTION, GROUP, SUBGROUP, DEFAULT 'ON' VALUE (playbulbs))
		# PLAYBULBS
		self.devices.append(playbulb("D1:F6:4B:14:AC:E6", "Playbulb facing the sofa", "salon", "luminaire", "05000000"))
		self.devices.append(playbulb("09:5F:4B:15:AC:E6", "Playbulb facing the entrance", "salon", "luminaire", "05000000"))
		self.devices.append(playbulb("07:B2:4B:15:AC:E6", "Playbulb facing the TV", "salon", "luminaire", "05000000"))
		self.devices.append(playbulb("07:94:4B:15:AC:E6", "Playbulb in the passage", "passage", "passage", "12000000"))
		# MILIGHTS
		self.devices.append(milight("88:C2:55:01:02:B1", "80", "112", "Milight living room, TV side", "salon", "sofa"))
		self.devices.append(milight("80:30:DC:DE:73:74", "38", "98", "Milight living room, sofa side", "salon", "sofa"))
		self.starttime = datetime.time(18,00) #Light change minimal time
		self.skiptime = 0
		self.queue = Queue()
		self.colors = ["0"] * len(self.devices)
		self.state = ["0"] * len(self.devices)
		self.setLock(0)
		self.lockcount = 0
		self.journaling = False
		self.priority = 0

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
				self.colors[_cnt] = self.state[_cnt]
			else:
				if (subgroup is not None and device.subgroup != subgroup):
					lightManager.debugger("Skipping device {} as it does not belong in the '{}' subgroup".format(device.device, subgroup), 0)
					self.colors[_cnt] = self.state[_cnt]

	def getToggle(self):
		colors = ["1"] * len(lm.devices)
		i = 0
		for color in self.state:
			if color != "0":
				colors = ["0"] * len(lm.devices)
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
			if type(obj) == playbulb or type(obj) == milight:
				desctext += str(i) + " - " + obj.descriptions() + "\n"
			else:
				desctext += str(i) + " - " + "Unknown bulb type\n"
			i += 1
		return desctext

	def enableJournaling(self):
		global journaling
		journaling = True
		#todo Dynamic history limits
		if os.path.isfile("/home/pi/play/play.0.log"):
			if os.path.isfile("/home/pi/play/play.1.log"):
				if os.path.isfile("/home/pi/play/play.2.log"):
					os.remove("/home/pi/play/play.2.log")
				os.rename("/home/pi/play/play.1.log", "/home/pi/play/play.2.log")
			os.rename("/home/pi/play/play.0.log", "/home/pi/play/play.1.log")

	def setLock(self, state):
		self.locked = state

	def _setLights(self):
		""" Threading du changement des couleurs """
		lightManager.debugger("Running a change of lights (priority level: {}, lock: {})...".format(self.priority, self.locked), 0)
		try:
			self.lockcount = 0
			firstran = False
			while not self.queue.empty():
				colors = None
				try:
					if firstran:
						lightManager.debugger("Getting remainder of queue", 0)
						self._reinit()
					colors = self.queue.get() #todo Check performance
					lightThreads = [None] * len(self.devices)
					lightPool = ThreadPool(processes=4)
					lightManager.debugger("Changing colors to " + str(colors) + " from state " + str(self.state), 0)
					self.setLock(1)
					oldstates = [None] * len(self.devices)
					i = 0
					tries = 0
					firstran = True

					while i < len(self.devices):
						lightManager.debugger("Requested colors: " + str(colors) + " from state " + str(self.state) + " i = " + str(i), 0)
						if colors[i] != self.state[i] or (colors[i] == "0" and self.state[i] == "0"):
							lightThreads[i] = lightPool.apply_async(self.devices[i].color, args=(colors[i],))
							if (colors[i] != "-1"):
								oldstates[i] = self.state[i]
								self.state[i] = colors[i]
						i += 1

						if (i == len(self.devices)):
							lightManager.debugger("Awaiting results", 0)
							for _cnt, _thread in enumerate(lightThreads):
								if (_thread is not None):
									try:
										if (not _thread.get(5)):
											self.state[_cnt] = oldstates[_cnt]
											i = 0
									except:
										self.state[_cnt] = oldstates[_cnt]
										i = 0
							tries = tries + 1
							if (tries == 5):
								break

				except Queue.Empty:
					pass

				finally:
					if colors:
						self.queue.task_done()

		except Exception as e:
			lightManager.debugger("Unhandled error of type {}, Args: {1!r} ".format(type(e).__name__, e.args), 3)

		finally:
			self._reinit()
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

	def _reinit(self):
		# Resets the Success bool to False to force a light change
		i = 0
		while i < len(self.devices):
			self.devices[i].reinit()
			i += 1

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
		levels = {0: "DEBUG", 1: "ERROR", 2: "FATAL"}
		debugtext = "(" + str(datetime.datetime.now().time()) + ") - [" + levels[level] + "] " + str(msg)
		print(debugtext)
		if journaling:
			with open("/home/pi/play/play.0.log", "a") as jfile:
				jfile.write(debugtext + "\n")


lock = threading.Lock()
class playbulb(lightManager):
	""" Methods for driving a rainbow BLE lightbulb """
	def __init__(self, device, description, group, subgroup, intensity):
		self.deviceType = "playbulb"
		self.device = device
		self.description = description
		#todo get actual color at instanciation
		self.actualcolor = 0
		self.success = False
		self._connection = None
		self.group = group
		self.subgroup = subgroup
		self.intensity = intensity

	def reinit(self):
		self.success = False

	def color(self, color):
		if (self.success):
			return True
		elif (color == "-1"): #todo Skip color change. Put in constant for readability
			self.success = True
			return True
		if (self.actualcolor == color):
			self.success = True
			lightManager.debugger("Bulb " + str(self.device) + " is already of the requested color, skipping.", 0)
			return True
		if (color == "0"):
			color = "00000000"
		elif (color == "1"):
			color = self.intensity
		self.actualcolor = color
		lightManager.debugger("Changing playbulb " + str(self.device) + " color to " + color, 0)
		if (not self._write(color)): return False
		return True

	def descriptions(self):
		desctext = "[Playbulb MAC: " + self.device + "] " + self.description
		return desctext

	def disconnect(self):
		try:
			if (self._connection is not None):
				lightManager.debugger("DISconnecting to device  " + str(self.device), 0)
				self._connection.disconnect()
		except ble.BTLEException:
			lightManager.debugger("Device " + str(self.device) + " disconnection failed. Already disconnected?", 1)        	
			pass

		self._connection = None

	@connect_ble
	def _write(self, color):
		try:
			if (self._connection is not None):
				with lock:
					self._connection.getCharacteristics(uuid="0000fffc-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(color))
			else:
				lightManager.debugger("Connection error to device (playbulb) " + str(self.device) + ". Retrying", 1)
				return False				
		except:
			#todo manage "overwritten" thread by queued requests
			lightManager.debugger("Unhandled response. Thread died?", 0)
			self.disconnect()
			return False
		lightManager.debugger("Playbulb " + str(self.device) + " color changed to " + color, 0)
		self.success = True
		return True


class milight(lightManager):
	""" Methods for driving a milight BLE lightbulb """
	def __init__(self, device, id1, id2, description, group, subgroup):
		self.deviceType = "milight"
		self.device = device
		self.id1 = id1
		self.id2 = id2
		self.description = description
		self.success = False
		self.actualcolor = "0"
		self._connection = None
		self.group = group
		self.subgroup = subgroup

	def reinit(self):
		self.success = False

	def turnon(self):
		return self._sendrequest(self.getquery(32, 161, 1, self.id1, self.id2), "1")

	def turnoff(self):
		return self._sendrequest(self.getquery(32, 161, 2, self.id1, self.id2), "0")

	def turnOnAndSetColor(self, color):
		if (not self.turnon()): return False
		return self._sendrequest(self.getquery(45, 161, 4, self.id1, self.id2, color, 2, 50), color)

	def turnOnAndDimOn(self, color):
		if (not self.turnon()): return False
		return self.dimon(color)

	def dimon(self, color):
		return self._sendrequest(self.getquery(20, 161, 5, self.id1, self.id2, 200, 4, 50), color)

	def color(self, color, pool = None):
		#todo rrggbb to ...this format...
		if (self.success):
			return True
		elif (color == "-1"):
			self.success = True
			return True
		mlTarget = None
		if color == "0":
			lightManager.debugger("Turning milight " + self.device + " off", 0)
			if (not self.turnoff()): return False
			return True
		elif (self.actualcolor == color):
			self.success = True
			lightManager.debugger("Device (milight) " + str(self.device) + " is already of the requested color, skipping.", 0)
			return True
		elif color == "1":
			lightManager.debugger("Turning milight " + self.device + " on", 0)
			if (not self.turnOnAndDimOn(color)): 
				lightManager.debugger("DIMON returned false", 0)
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

	def disconnect(self):
		try:
			if (self._connection is not None):
				self._connection.disconnect()
		except:
			lightManager.debugger("Device (milight) " + str(self.device) + " disconnection failed. Already disconnected?", 1)        	
			pass

		self._connection = None

	@connect_ble
	def _sendrequest(self, command, color):
		try:
			if (self._connection is not None):
				with lock:
					self._connection.getCharacteristics(uuid="00001001-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(command.replace('\n', '').replace('\r', '')))
			else:
				lightManager.debugger("Connection error to device (milight) " + str(self.device) + ". Retrying", 1)
				return False
		except:
			lightManager.debugger("Error sending data to device (milight) " + str(self.device) + ". Retrying", 1)
			self._connection = None		
			return False
		self.success = True
		self.actualcolor = color
		return True

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
	lm = lightManager()

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
	parser.add_argument('--journal', action='store_true', default=False, help='Enables file journaling')
	parser.add_argument('--tvon', action='store_true', default=False, help='Turns TV on')
	parser.add_argument('--tvoff', action='store_true', default=False, help='Turns TV off')
	parser.add_argument('--tvrestart', action='store_true', default=False, help='Reboots KODI')

	args = parser.parse_args()

	if (args.server and (args.playbulb or args.milight or args.on or args.off or args.toggle)):
		lightManager.debugger("You cannot start the daemon and send arguments at the same time.", 2)
		sys.exit()

	#todo do not hardcode this
	HOST = '192.168.1.50'
	PORT = 1111
	
	if args.journal:
		lm.enableJournaling()
	if args.server:
		if args.notime:
			lm.skipTime(1)
		lightServer(lm,HOST,PORT).listen()
	else:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((HOST, PORT))
		#todo report connection errors or allow feedback response
		lightManager.debugger('Connecting with lightmanager daemon', 0)
		lightManager.debugger('Sending request: ' + json.dumps(vars(args)), 0)
		s.sendall(json.dumps(vars(args)).encode('utf-8'))
		s.close()

		sys.exit()
else:
	""" Script imported - var colors must be predefined and functions are limited"""
	#todo deprecate this?
	lm = lightManager()

	try:
		colors[1]
	except (IndexError, NameError): 
		lightManager.debugger("No arguments given, defaulting to lights off", 0)
		lm.setColors()
	else:
		lightManager.debugger("Received color length " + str(len(colors)) + " for " + str(len(lm.devices)) + " devices", 0) 
		lm.setColors(colors)
		if len(colors) == len(lm.devices)+1:
			if colors[len(lm.devices)] == "1":
				lm.skipTime(0)
	lm.run()
	sys.exit()







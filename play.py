#!/usr/bin/env python3
'''
    File name: play.py
    Author: Maxime Bergeron
    Date last modified: 05/03/2019
    Python Version: 3.7

    A python websocket server/client and IFTTT receiver to control various cheap IoT
    RGB BLE lightbulbs and HDMI-CEC-to-TV RPi3
'''
import os
import os.path
import re
import subprocess
import sys
import argparse
import sched
import time
import datetime
import socket
import threading
import configparser
import requests
import traceback
import json
import signal
import queue
import urllib.parse
import hashlib
from devices.common import *
from devices import *
from argparse import RawTextHelpFormatter, Namespace
from multiprocessing.pool import ThreadPool
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from __main__ import *


class HomeServer(object):
    """ Handles server-side request reception and handling """
    def __init__(self, lm):
        self.config = configparser.ConfigParser()
        self.config.read('play.ini')
        self.host = self.config['SERVER']['HOST']
        self.port = int(self.config['SERVER']['PORT'])
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sched_disconnect = sched.scheduler(time.time, time.sleep)
        self.scheduled_disconnect = None
        #TODO Fix signaling
        #signal.signal(signal.SIGTERM, self.remove_server)

    def listen(self):
        """ Starts the server """
        debug.write('Server started', 0)
        # Cleanup connection to allow new sock.accepts faster as sched is blocking
        self.disconnect_devices()
        self.sock.listen(5)
        while True:
            client, address = self.sock.accept()
            debug.write("Connected with {}:{}".format(address[0], address[1]), 0)
            client.settimeout(30)
            threading.Thread(target=self.listen_client, args=(client, address)).start()

    def listen_client(self, client, address):
        """ Listens for new requests and handle them properly """
        streamingdev = False
        streaminggrp = False
        streaming_id = None
        try:
            while True:
                msize = int(client.recv(4).decode('utf-8'))
                if self.scheduled_disconnect is not None:
                    self.sched_disconnect.cancel(self.scheduled_disconnect)
                    self.scheduled_disconnect = None
                #debug.write("Set message size {}".format(msize), 0)
                data = client.recv(msize)
                if data:
                    if data.decode('utf-8') == "getstate":
                        debug.write('Sending lightserver status', 0)
                        client.send(str.encode("State: " + str(lm.get_state()).replace("[","").replace("]","")))
                        break
                    if data.decode('utf-8') == "stream":
                        debug.write('Starting streaming mode', 0)
                        streamingdev = True
                        continue
                    if data.decode('utf-8') == "streamgroup":
                        debug.write('Starting group streaming mode', 0)
                        streaminggrp = True
                        continue
                    if data.decode('utf-8') == "nostream":
                        debug.write('Ending streaming mode', 0)
                        streamingdev = False
                        streaminggrp = False
                        streaming_id = None
                        break
                    if streamingdev:
                        if streaming_id is None:
                            streaming_id = int(data.decode('utf-8'))
                            debug.write('Set streaming devid to {}' \
                                                  .format(streaming_id), 0)
                            continue
                        debug.write("Sending request to devid {} for color: {}" \
                                              .format(streaming_id, data.decode('utf-8')), 0)
                        lm.set_light_stream(streaming_id, data.decode('utf-8'), False)
                        continue
                    if streaminggrp:
                        if streaming_id is None:
                            streaming_id = data.decode('utf-8')
                            debug.write('Set streaming group to {}' \
                                                  .format(streaming_id), 0)
                            continue
                        debug.write("Sending request to group '{}' for color: {}" \
                                              .format(streaming_id, data.decode('utf-8')), 0)
                        lm.set_light_stream(streaming_id, data.decode('utf-8'), True)
                        continue
                    try:
                        args = self._sanitize(json.loads(data.decode('utf-8')))
                    except: #fallback - data is not UTF-8 formatted and/or JSON compatible ?
                        debug.write("Error - improperly formatted JSON. Got: {}".format(data.decode('utf-8')), 2)
                        break
                    debug.write('Change of lights requested with args: ' + str(args), 0)
                    self._validate_and_execute_req(args)
                    break

        except socket.timeout:
            pass

        except Exception as ex:
            debug.write('Unhandled exception of type {}: {}, {}' \
                                  .format(type(ex), ex, 
                                          ''.join(traceback.format_tb(ex.__traceback__))
                                         ), 2)

        finally:
            debug.write('Closing connection.', 0)
            lm.set_lock(0)
            lm.reinit()
            client.close()
            self.scheduled_disconnect = self.sched_disconnect.enter(60, 1, 
                                                                    self.disconnect_devices, ())
            self.sched_disconnect.run()

    def disconnect_devices(self):
        """ Disconnects all configured devices """
        self.scheduled_disconnect = None
        debug.write("Server unused. Disconnecting devices.", 0)
        for _dev in lm.devices:
            _dev.disconnect()

    def remove_server(self, signal, frame):
        """ Shuts down server and cleans resources """
        debug.write("Closing down server and lights.", 0)
        lm.skip_time(0)
        lm.set_colors([LIGHT_OFF] * len(lm.devices))
        lm.run()
        time.sleep(3)
        self.sock.close()

    def _validate_and_execute_req(self, args):
        debug.write("Validating arguments", 0)
        if args["hexvalues"] and (args["playbulb"] or args["milight"] or args["decora"]
                                  or args["meross"]):
            debug.write("Got color hexvalues for milights and/or playbulbs \
                                   and/or other devices in the same request, which is not \
                                   supported. Use '{} -h' for help. Quitting".format(sys.argv[0]),
                                 2)
            return     
        if len(args["hexvalues"]) != len(lm.devices) and not any([args["notime"], args["off"], args["on"], 
                                                                  args["playbulb"], args["milight"], 
                                                                  args["toggle"], args["decora"], 
                                                                  args["preset"], args["restart"],
                                                                  args["meross"]]):
            debug.write("Got {} color hexvalues, {} expected. Use '{} -h' for help. Quitting" \
                                  .format(len(args["hexvalues"]), len(lm.devices), sys.argv[0]), 2)
            return
        if args["priority"]:
            lm.priority = args["priority"]
        if args["hexvalues"]:
            debug.write("Received color hexvalues length {} for {} devices" \
                                  .format(len(args["hexvalues"]), len(lm.devices)), 0)
            lm.set_colors(args["hexvalues"])
        else:
            if args["playbulb"] is not None:
                debug.write("Received playbulb change request", 0)
                if not lm.set_typed_colors(args["playbulb"], Playbulb.Playbulb):
                    return
            if args["milight"] is not None:
                debug.write("Received milight change request", 0)
                if not lm.set_typed_colors(args["milight"], Milight.Milight):
                    return
            if args["decora"] is not None:
                debug.write("Received decora change request", 0)
                if not lm.set_typed_colors(args["decora"], DecoraSwitch.DecoraSwitch):
                    return
            if args["meross"] is not None:
                debug.write("Received meross change request", 0)
                if not lm.set_typed_colors(args["meross"], MerossSwitch.MerossSwitch):
                    return
            if args["preset"] is not None:
                debug.write("Received change to preset [{}] request".format(args["preset"]), 0)
                try:
                    lm.set_colors(self.config["PRESETS"][args["preset"]].split(','))
                except:
                    debug.write("Preset {} not found in play.ini. Quitting.".format(args["preset"]), 3)
                    return                       
            if args["off"]:
                debug.write("Received OFF change request", 0)
                lm.set_colors([LIGHT_OFF] * len(lm.devices))
            if args["on"]:
                debug.write("Received ON change request", 0)
                lm.set_colors([LIGHT_ON] * len(lm.devices))
            if args["restart"]:
                debug.write("Received RESTART change request", 0)
                if not lm.set_typed_colors(2, GenericOnOff.GenericOnOff):
                    return
            if args["toggle"]:
                debug.write("Received TOGGLE change request", 0)
                lm.set_colors(lm.get_toggle())
        if args["notime"] or args["off"]:
            lm.skip_time(0)
        if args["group"] is not None or args["subgroup"] is not None:
            lm.get_group(args["group"], args["subgroup"])
        debug.write("Arguments are OK", 0)
        lm.run(args["delay"])
        return

    def _sanitize(self, args):
        if "hexvalues" not in args:
            args["hexvalues"] = []
        if "off" not in args:
            args["off"] = False
        if "on" not in args:
            args["on"] = False
        if "restart" not in args:
            args["restart"] = False
        if "toggle" not in args:
            args["toggle"] = False
        if "playbulb" not in args:
            args["playbulb"] = None
        if "milight" not in args:
            args["milight"] = None
        if "decora" not in args:
            args["decora"] = None
        if "meross" not in args:
            args["meross"] = None
        if "server" not in args:
            args["server"] = False
        if "ifttt" not in args:
            args["ifttt"] = False
        if "notime" not in args:
            args["notime"] = False
        if "delay" not in args:
            args["delay"] = False
        if "priority" in args and args["priority"] is None:
            args["priority"] = 1
        if "priority" not in args:
            args["priority"] = 1
        if "preset" not in args:
            args["preset"] = None
        if "group" not in args:
            args["group"] = None
        if "subgroup" not in args:
            args["subgroup"] = None
        if type(args["playbulb"]).__name__ == "str":
            debug.write('Converting values to lists for playbulb', 0)
            args["playbulb"] = args["playbulb"].replace("'", "").split(',')
        if type(args["milight"]).__name__ == "str":
            debug.write('Converting values to lists for milight', 0)
            args["milight"] = args["milight"].replace("'", "").split(',')
        if type(args["decora"]).__name__ == "str":
            debug.write('Converting values to lists for decora', 0)
            args["decora"] = args["decora"].replace("'", "").split(',')
        if type(args["meross"]).__name__ == "str":
            debug.write('Converting values to lists for meross', 0)
            args["meross"] = args["meross"].replace("'", "").split(',')
        return args


class IFTTTServer(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'x-www-form-urlencoded')
        self.end_headers()

    def do_POST(self):
        config = configparser.ConfigParser()
        config.read('play.ini')
        """ Receives and handles POST request """
        SALT = config["IFTTT"]["SALT"]
        debug.write('[IFTTTServer] Getting request', 0)
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        postvars = urllib.parse.parse_qs(self.rfile.read(content_length), keep_blank_values=1)
        action = postvars[b'action'][0].decode('utf-8')
        _hash = postvars[b'hash'][0].decode('utf-8')

        if _hash == hashlib.sha512(bytes(SALT.encode('utf-8') + action.encode('utf-8'))).hexdigest():
            debug.write('IFTTTServer running action : {}'.format(action), 0)
            if action in config["IFTTT"]:
                debug.write('[IFTTTServer] Running action : {}'.format(config["IFTTT"][action]), 0)
                os.system(config["IFTTT"][action])
            else:
                #
                # Complex actions should be hardcoded here if needed
                #
                debug.write('[IFTTTServer] Unknown action : {}'.format(action), 1)
        else:
            debug.write('[IFTTTServer] Got unwanted request with action : {}'.format(action), 1)

        self._set_response()


class DeviceManager(object):
    """ Methods for instanciating and managing devices """
    def __init__(self, config=None):
        self.config = config
        self.devices = []
        i = 0
        while True:
            try:
                if self.config["DEVICE"+str(i)]["TYPE"] in getDevices():
                    _module = __import__("devices." + self.config["DEVICE"+str(i)]["TYPE"])
                    #TODO Needed twice ? looks unpythonic
                    _class = getattr(_module,self.config["DEVICE"+str(i)]["TYPE"])
                    _class = getattr(_class,self.config["DEVICE"+str(i)]["TYPE"])
                    self.devices.append(_class(i, self.config))
                else:
                    debug.write('Unsupported device type {}' \
                                          .format(self.config["DEVICE"+str(i)]["TYPE"]), 1)
            except KeyError:
                break
            i = i + 1

        #TODO allow reporting of device state to the lightserver
        if str(self.config['SERVER']['EVENT_HOUR']) != "auto":
            self.lastupdate = None
            self.starttime = datetime.datetime.strptime(self.config['SERVER']['EVENT_HOUR'],'%H:%M').time()
        else:
            self.lastupdate = datetime.date.today()
            self.starttime = self._update_sunset_time(self.config['SERVER']['EVENT_LOCALIZATION'])
            debug.write("Event time set as sunset time: {}".format(self.starttime), 0)
        self.skiptime = 0
        self.queue = queue.Queue()
        self.colors = ["-1"] * len(self.devices)
        self.delays = [0] * len(self.devices)
        self.set_lock(0)
        self.lockcount = 0
        self.priority = 0
        self.threaded = False
        self.light_threads = [None] * len(self.devices)
        self.light_pool = None

    def start_threaded(self):
        """ Enables multithreaded light change requests """
        self.threaded = True
        self.light_pool = ThreadPool(processes=4)

    def skip_time(self, serverwide=0):
        """ Enables skipping time check """
        if serverwide:
            debug.write("Skipping time check for all requests", 0)
            self.starttime = None
        else:
            debug.write("Skipping time check", 0)
            self.skiptime = 1

    def set_colors(self, color):
        """ Setter function for color request. Required. """
        self.colors = color

    def get_group(self, group, subgroup):
        """ Gets devices from a specific group/subgroup for the light change """
        for _cnt, device in enumerate(self.devices):
            if group is not None and device.group != group:
                debug.write("Skipping device {} as it does not belong in the '{}' group" \
                                      .format(device.device, group), 0)
                self.colors[_cnt] = LIGHT_SKIP
            else:
                if subgroup is not None and device.subgroup != subgroup:
                    debug.write("Skipping device {} as it does not belong in the '{}' subgroup" \
                                          .format(device.device, subgroup), 0)
                    self.colors[_cnt] = LIGHT_SKIP

    def get_toggle(self):
        """ Toggles the devices on/off """
        colors = [LIGHT_ON] * len(lm.devices)
        i = 0
        for color in self.get_state():
            if color != LIGHT_OFF:
                colors = [LIGHT_OFF] * len(lm.devices)
            i = i+1
        return colors

    def set_typed_colors(self, colorargs, atype):
        """ Gets devices of a specific  type for the light change """
        self.colors = ["-1"] * len(self.devices)
        cvals = self._get_type_index(atype)
        if len(colorargs) == 1 and cvals[0] > 1:
            # Allow a single value to be repeated to n devices
            debug.write("Expanding color {} to {} devices." \
                                  .format(len(colorargs), cvals[0]), 0)
            colorargs = [colorargs[0]] * cvals[0]
        if cvals[0] != len(colorargs):
            debug.write("Received color hexvalues length {} for {} devices. Quitting" \
                                  .format(len(colorargs), cvals[0]), 2)
            return False
        self.colors[cvals[1]:cvals[1]+cvals[0]] = colorargs

        return True

    def run(self, delay=None):
        """ Validates the request and runs the light change """
        if delay is not None:
            debug.write("Delaying request for {} seconds".format(delay), 0)
            time.sleep(delay)
        if self._check_time():
            self.queue.put(self.colors)
            #TODO Manage locking out when the run thread hangs
            debug.write("Locked status: {}".format(self.locked), 0)
            if not self.locked or self.lockcount == 2:
                self._set_lights()
            else:
                self.lockcount = self.lockcount + 1

    def descriptions(self):
        """ Getter for configured devices descriptions """
        desctext = ""
        i = 1
        for obj in self.devices:
            #TODO make this dynamic
            if isinstance(obj, (Playbulb.Playbulb, Milight.Milight, DecoraSwitch.DecoraSwitch, 
                                GenericOnOff.GenericOnOff, MerossSwitch.MerossSwitch)):
                desctext += str(i) + " - " + obj.descriptions() + "\n"
            else:
                desctext += str(i) + " - " + "Unknown bulb type\n"
            i += 1
        return desctext

    def set_lock(self, is_locked):
        """ Locks the light change request """
        self.locked = is_locked

    def get_state(self, devid=None):
        """ Getter for configured devices actual colors """
        states = [None] * len(self.devices)
        for _cnt, dev in enumerate(self.devices):
            states[_cnt] = dev.get_state()
        if devid is not None:
            return states[devid]
        return states

    def set_light_stream(self, devid, color, is_group):
        """ Simplified function for quick, streamed light change requests """
        if is_group:
            for device in self.devices:
                if device.group == devid:
                    cnt = 0
                    _color = device.convert(color)
                    while True:
                        if cnt == 4:
                            break
                        if device.color(_color, 3):
                            break
                        time.sleep(0.3)
                        cnt = cnt + 1
        else:
            cnt = 0
            _color = device.convert(color)
            while True:
                if cnt == 4:
                    break
                if self.devices[devid].color(_color, 3):
                    break
                time.sleep(0.3)
                cnt = cnt + 1
        self.reinit()

    def reinit(self):
        """ Resets the Success bool to False """
        i = 0
        while i < len(self.devices):
            self.devices[i].reinit()
            i += 1

    def _decode_colors(self, colors):
        self.delays = [0] * len(self.devices)
        for _cnt, _col in enumerate(colors):
            if re.match("[0-9a-fA-F]+d[0-9]+", _col) is not None:
                _vals = _col.split("d")
                colors[_cnt] = _vals[0]
                self.delays[_cnt] = int(_vals[1])
        return colors

    def _set_lights(self):
        debug.write("Running a change of lights (priority level: {})..." \
                              .format(self.priority), 0)
        try:
            self.lockcount = 0
            firstran = False
            try:
                while not self.queue.empty():
                    colors = None
                    if firstran:
                        debug.write("Getting remainder of queue", 0)
                        self.reinit()
                    colors = self._decode_colors(self.queue.get()) #TODO Check performance
                    debug.write("Changing colors to {} from state {}" \
                                          .format(colors, self.get_state()), 0)
                    self.set_lock(1)
                    i = 0
                    tries = 0
                    firstran = True

                    while i < len(self.devices):
                        _state = self.get_state(i)
                        _color = self.devices[i].convert(colors[i])

                        if not self.devices[i].success:
                            if _color != LIGHT_SKIP:
                                debug.write(("DEVICE: {}, REQUESTED COLOR: {} "
                                                  "FROM STATE: {}, PRIORITY: {}")
                                                  .format(self.devices[i].device,
                                                          _color, _state,
                                                          self.devices[i].priority),
                                                  0)
                            if self.threaded:
                                if not self.queue.empty():
                                    break

                                self.light_threads[i] = self.light_pool.apply_async(self._set_device,
                                                                                    args=(i, _color, 
                                                                                          self.priority,
                                                                                          self.delays[i]))
                            else:
                                self._set_device(i, _color, self.priority, self.delays[i])
                        i += 1

                        if i == len(self.devices):
                            if self.threaded:
                                debug.write("Awaiting results", 0)
                                for _cnt, _thread in enumerate(self.light_threads):
                                    if not self.queue.empty():
                                        continue
                                    if _thread is not None:
                                        try:
                                            if _thread.get(self.delays[_cnt] + 5) is not None:
                                                i = 0
                                        except:
                                            i = 0
                                tries = tries + 1
                                if tries == 5:
                                    break
                            else:
                                for _cnt, _dev in enumerate(self.devices):
                                    _state = self.get_state(_cnt)
                                    if self.devices[i].convert(colors[i]) != _state:
                                        i = 0
                                tries = tries + 1
                                if tries == 5:
                                    break

            except queue.Empty:
                debug.write("Nothing in queue", 0)
                pass

            finally:
                debug.write("Clearing up light change queues.", 0)
                if colors:
                    self.queue.task_done()

        except Exception as ex:
            debug.write('Unhandled exception of type {}: {}, {}'
                                  .format(type(ex), ex, 
                                          ''.join(traceback.format_tb(ex.__traceback__))), 2)

        finally:
            self.reinit()
            self.set_lock(0)

        debug.write("Change of lights completed.", 0)

    def _set_device(self, count, color, priority, delay):
        #TODO Find a way to make the delays non blocking
        if delay is not 0:
            debug.write("Delaying for {} seconds request for device: {}"
                        .format(delay, self.devices[count].description), 0) 
            s = sched.scheduler(time.time, time.sleep)
            s.enter(delay, 1, self.devices[count].color, (color, priority,))
            s.run()
        else:
            self.devices[count].color(color, priority)

    def _check_time(self):
        if self.skiptime or self.starttime is None:
            self.skiptime = 0
            return 1
        if self.lastupdate != datetime.date.today():
            self.starttime = self._update_sunset_time(self.config['SERVER']['EVENT_LOCALIZATION'])
            debug.write("Event time set as sunset time: {}".format(self.starttime), 0)            
        if datetime.time(6, 00) < datetime.datetime.now().time() < self.starttime:
            debug.write("Too soon, no change of light required. Light changes begins at {}"
                        .format(self.starttime), 0)
            return 0
        return 1

    def _get_type_index(self, atype):
        # TODO This should not depend on an ordered set of devices
        i = 0
        count = 0
        firstindex = 0
        for obj in self.devices:
            if isinstance(obj, atype):
                if count == 0: 
                    firstindex = i
                count += 1
            i += 1
        if count == 0:
            raise Exception('Invalid bulb type given. Quitting')
        return [count, firstindex]

    def _update_sunset_time(self, localization):
        p1 = subprocess.Popen('./scripts/sunset.sh %s' % str(localization), stdout=subprocess.PIPE, \
                              shell=True)
        (output,_) = p1.communicate()
        p1.wait()
        return datetime.datetime.strptime(output.rstrip().decode('UTF-8'),'%H:%M').time()


def runServer():
    HomeServer(lm).listen()

def runIFTTTServer():
    port = 1234
    server_address = ('', port)
    httpd = HTTPServer(server_address, IFTTTServer)
    debug.write('[IFTTTServer] Getting lightserver POST requests on port {}' \
                          .format(port), 0)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    debug.write('[IFTTTServer] Stopping.', 0)

def runDetectorServer(config, lm):
    DEVICE_STATE_LEVEL = [0]*len(config['DETECTOR']['TRACKED_IPS'].split(","))
    DEVICE_STATE_MAX = int(config['DETECTOR']['MAX_STATE_LEVEL'])
    DEVICE_STATUS = [0]*len(config['DETECTOR']['TRACKED_IPS'].split(","))
    FIND3_SERVER = bool(config['DETECTOR']['FIND3_SERVER_ENABLE'])
    STATUS = 0
    DELAYED_START = 0
    debug.write("[Detector] Starting ping-based device detector", 0)

    if FIND3_SERVER:
        TRACKED_FIND3_DEVS = config['DETECTOR']['FIND3_TRACKED_DEVICES'].split(",")
        TRACKED_FIND3_TIMES = [0]*len(TRACKED_FIND3_DEVS)
        TRACKED_FIND3_LOCAL = [""]*len(TRACKED_FIND3_DEVS)
        for _cnt, _dev in enumerate(TRACKED_FIND3_DEVS):
            # Get last update times
            if _dev != "_":
                _r = requests.get("http://{}/api/v1/location/{}/{}".format(config['DETECTOR']['FIND3_SERVER_URL'],
                                                                           config['DETECTOR']['FIND3_FAMILY_NAME'],
                                                                           _dev))
                TRACKED_FIND3_TIMES[_cnt] = _r.json()['sensors']['t']

    for _cnt, device in enumerate(config['DETECTOR']['TRACKED_IPS'].split(",")):
        if int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
            DEVICE_STATE_LEVEL[_cnt] = DEVICE_STATE_MAX
            DEVICE_STATUS[_cnt] = 1
        else:
            DEVICE_STATE_LEVEL[_cnt] = 0
            DEVICE_STATUS[_cnt] = 0
    debug.write("[Detector] Got initial states {} and status {}".format(DEVICE_STATE_LEVEL, STATUS), 0)

    while True:
        EVENT_TIME = lm.starttime
        for _cnt, device in enumerate(config['DETECTOR']['TRACKED_IPS'].split(",")):
            #TODO Maintain the two pings requirement for status change ?
            if int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
                if DEVICE_STATE_LEVEL[_cnt] == DEVICE_STATE_MAX and DEVICE_STATUS[_cnt] == 0:
                    debug.write("[Detector] DEVICE {} CONnected".format(device), 0)
                    DEVICE_STATUS[_cnt] = 1
                elif DEVICE_STATE_LEVEL[_cnt] != DEVICE_STATE_MAX:
                    DEVICE_STATE_LEVEL[_cnt] = DEVICE_STATE_LEVEL[_cnt] + 1
                if FIND3_SERVER and TRACKED_FIND3_DEVS[_cnt] != "_":
                    _r = requests.get("http://{}/api/v1/location/{}/{}".format(config['DETECTOR']['FIND3_SERVER_URL'],
                                                                               config['DETECTOR']['FIND3_FAMILY_NAME'],
                                                                               TRACKED_FIND3_DEVS[_cnt]))
                    if TRACKED_FIND3_TIMES[_cnt] != _r.json()['sensors']['t'] and \
                       TRACKED_FIND3_LOCAL[_cnt] != _r.json()['analysis']['guesses'][0]['location']:
                        if _r.json()['analysis']['guesses'][0]['location'] in config['FIND3-PRESETS']:
                            os.system(config['FIND3-PRESETS'][_r.json()['analysis']['guesses'][0]['location']])
                            debug.write("[Detector-FIND3] Device {} found in '{}'. Running change of lights."
                                        .format(TRACKED_FIND3_DEVS[_cnt], 
                                                _r.json()['analysis']['guesses'][0]['location']), 0)

                        else:
                            debug.write("[Detector-FIND3] Device {} found in '{}' but preset is not configured."
                                        .format(TRACKED_FIND3_DEVS[_cnt], 
                                                _r.json()['analysis']['guesses'][0]['location']), 0)
                        if TRACKED_FIND3_LOCAL[_cnt]+"-off" in config['FIND3-PRESETS']:
                            os.system(config['FIND3-PRESETS'][TRACKED_FIND3_LOCAL[_cnt]+"-off"])
                            debug.write("[Detector-FIND3] Device {} left '{}'. Running change of lights."
                                        .format(TRACKED_FIND3_DEVS[_cnt], 
                                                TRACKED_FIND3_LOCAL[_cnt]), 0)
                        TRACKED_FIND3_TIMES[_cnt] = _r.json()['sensors']['t']
                        TRACKED_FIND3_LOCAL[_cnt] = _r.json()['analysis']['guesses'][0]['location']
            else:
                if DEVICE_STATE_LEVEL[_cnt] == 0 and DEVICE_STATUS[_cnt] == 1:
                    debug.write("[Detector] DEVICE {} DISconnected".format(device), 0)
                    DEVICE_STATUS[_cnt] = 0
                elif DEVICE_STATE_LEVEL[_cnt] != 0:
                    # Decrease state level down to zero (OFF)
                    DEVICE_STATE_LEVEL[_cnt] = DEVICE_STATE_LEVEL[_cnt] - 1

        if STATUS == 1 and all(s == 0 for s in DEVICE_STATE_LEVEL):
            debug.write("[Detector] STATE changed to {} and DELAYED_START {}, turned off" \
                                  .format(DEVICE_STATE_LEVEL, DELAYED_START), 0)
            os.system('./playclient.py --off --notime --priority 3')
            STATUS = 0
            DELAYED_START = 0
        if datetime.datetime.now().time() == EVENT_TIME and DELAYED_START == 1:
            debug.write("[Detector] DELAYED STATE with actual state {}, turned on".format(DEVICE_STATE_LEVEL), 
                                                                                          0)
            os.system('./playclient.py --on --group passage')
            DELAYED_START = 0
            STATUS = 1  
        if DEVICE_STATE_MAX in DEVICE_STATE_LEVEL and DELAYED_START == 0:
            if datetime.datetime.now().time() < EVENT_TIME:
                debug.write("[Detector] Scheduling state change, with actual state {}" \
                                      .format(DEVICE_STATE_LEVEL), 0)
                DELAYED_START = 1
                STATUS = 0
        if DEVICE_STATE_MAX in DEVICE_STATE_LEVEL and STATUS == 0 and datetime.datetime.now().time() \
           >= EVENT_TIME:
            debug.write("[Detector] STATE changed to {}, turned on".format(DEVICE_STATE_LEVEL), 0)
            os.system('./playclient.py --on --group passage')
            STATUS = 1
            DELAYED_START = 0
        if all(s == 0 for s in DEVICE_STATE_LEVEL) and STATUS == 0 and DELAYED_START == 1:
            debug.write("[Detector] Aborting light change, with actual state {}" \
                                      .format(DEVICE_STATE_LEVEL), 0)
            DELAYED_START = 0
        time.sleep(int(config['DETECTOR']['PING_FREQ_SEC']))


""" Script executed directly """
if __name__ == "__main__":
    PLAYCONFIG = configparser.ConfigParser()
    PLAYCONFIG.read('play.ini')
    lm = DeviceManager(PLAYCONFIG)

    parser = argparse.ArgumentParser(description='BLE light bulbs manager script', epilog=lm.descriptions(),
                                     formatter_class=RawTextHelpFormatter)
    parser.add_argument('hexvalues', metavar='N', type=str, nargs="*",
                        help='color hex values for the lightbulbs (see list below)')
    parser.add_argument('--playbulb', metavar='P', type=str, nargs="*", help='Change playbulbs colors only')
    parser.add_argument('--milight', metavar='M', type=str, nargs="*", help='Change milights colors only')
    parser.add_argument('--decora', metavar='M', type=str, nargs="*", help='Change decora colors only')
    parser.add_argument('--meross', metavar='M', type=str, nargs="*", help='Change meross states only')
    parser.add_argument('--priority', metavar='prio', type=int, nargs="?", default=1,
                        help='Request priority from 1 to 3')
    parser.add_argument('--preset', metavar='preset', type=str, nargs="?", default=None,
                        help='Apply light actions from specified preset name defined in play.ini')
    parser.add_argument('--group', metavar='group', type=str, nargs="?", default=None,
                        help='Apply light actions on specified light group')
    parser.add_argument('--subgroup', metavar='subgroup', type=str, nargs="?", default=None,
                        help='Apply light actions on specified light subgroup')
    parser.add_argument('--notime', action='store_true', default=False,
                        help='Skip the time check and run the script anyways')
    parser.add_argument('--delay', metavar='delay', type=int, nargs="?", default=None,
                        help='Run the request after a given number of seconds')
    parser.add_argument('--on', action='store_true', default=False, help='Turn everything on')
    parser.add_argument('--off', action='store_true', default=False, help='Turn everything off')
    parser.add_argument('--restart', action='store_true', default=False, help='Restart generics')
    parser.add_argument('--toggle', action='store_true', default=False, help='Toggle all lights on/off')
    parser.add_argument('--server', action='store_true', default=False,
                        help='Start as a socket server daemon')
    parser.add_argument('--ifttt', action='store_true', default=False,
                        help='Start a ifttt websocket receiver along with server')
    parser.add_argument('--detector', action='store_true', default=False,
                        help='Start a ping-based device detector (usually for mobiles)')
    parser.add_argument('--threaded', action='store_true', default=False,
                        help='Starts the server daemon with threaded light change requests')
    parser.add_argument('--stream-dev', metavar='str-dev', type=int, nargs="?", default=None,
                        help='Stream colors directly to device id')
    parser.add_argument('--stream-group', metavar='str-grp', type=str, nargs="?", default=None,
                        help='Stream colors directly to device group')

    args = parser.parse_args()

    if args.server and (args.playbulb or args.milight or args.decora or args.on
                        or args.off or args.toggle or args.stream_dev
                        or args.stream_group or args.preset or args.restart 
                        or args.meross):
        debug.write("You cannot start the daemon and send arguments at the same time. \
                              Quitting.", 2)
        sys.exit()

    if args.stream_dev and args.stream_group:
        debug.write("You cannot stream data to both devices and groups. Quitting.", 2)
        sys.exit()

    if args.server:
        if args.notime:
            lm.skip_time(1)
        if args.threaded:
            lm.start_threaded()
        if args.ifttt:
            Thread(target = runIFTTTServer).start()
        if args.detector:
            Thread(target = runDetectorServer, args = (PLAYCONFIG,lm,)).start()
        Thread(target = runServer).start()

    elif args.stream_dev or args.stream_group:
        colorval = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((PLAYCONFIG['SERVER']['HOST'], int(PLAYCONFIG['SERVER']['PORT'])))
        if args.stream_dev:
            s.sendall("0006".encode('utf-8'))
            s.sendall("stream".encode('utf-8'))
            s.sendall(('%04d' % args.stream_dev).encode('utf-8'))
            s.sendall(str(args.stream_dev).encode('utf-8'))
        else:
            s.sendall("0011".encode('utf-8'))
            s.sendall("streamgroup".encode('utf-8'))
            s.sendall(('%04d' % len(args.stream_group)).encode('utf-8'))
            s.sendall(args.stream_group.encode('utf-8'))
        while colorval != "quit":
            if args.stream_dev:
                colorval = input("Set device {} to colorvalue ('quit' to exit): " \
                                  .format(args.stream_dev))
            else:
                colorval = input("Set group '{}' to colorvalue ('quit' to exit): " \
                                  .format(args.stream_group))
            try:
                if colorval == "quit":
                    s.sendall("0008".encode('utf-8'))
                    s.sendall("nostream".encode('utf-8'))
                    break
                s.sendall(('%04d' % len(colorval)).encode('utf-8'))
                s.sendall(colorval.encode('utf-8'))
            except BrokenPipeError:
                if colorval != "quit":
                    s.close()
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((PLAYCONFIG['SERVER']['HOST'], int(PLAYCONFIG['SERVER']['PORT'])))
                    if args.stream_dev:
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
        s.connect((PLAYCONFIG['SERVER']['HOST'], int(PLAYCONFIG['SERVER']['PORT'])))
        #TODO report connection errors or allow feedback response
        debug.write('Connecting with lightmanager daemon', 0)
        debug.write('Sending request: ' + json.dumps(vars(args)), 0)
        s.sendall("1024".encode('utf-8'))
        s.sendall(json.dumps(vars(args)).encode('utf-8'))
        s.close()

    sys.exit()

#!/usr/bin/env python3
'''
    File name: play.py
    Author: Maxime Bergeron
    Date last modified: 23/08/2019
    Python Version: 3.5

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
import traceback
import json
import queue
from devices.common import *
from argparse import RawTextHelpFormatter, Namespace
from multiprocessing.pool import ThreadPool
from functools import partial
from __main__ import *


class HomeServer(object):
    """ Handles server-side request reception and handling """
    def __init__(self, lm):
        self.config = configparser.ConfigParser()
        self.config.read('play.ini')
        self.host = self.config['SERVER']['HOST']
        self.port = int(self.config['SERVER'].getint('PORT'))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.scheduled_disconnect = None
        self.tcp_start_hour = datetime.datetime.strptime(self.config['SERVER']['TCP_START_HOUR'],'%H:%M').time()
        self.tcp_end_hour = datetime.datetime.strptime(self.config['SERVER']['TCP_END_HOUR'],'%H:%M').time()
        self.conn_sockets = []
        self.state_thread = None

    def listen(self):
        """ Starts the server """
        debug.write('Server started', 0)
        # Cleanup connection to allow new sock.accepts faster as sched is blocking
        self.disconnect_devices()
        try:
            self.sock.listen(5)
            while True:
                client, address = self.sock.accept()
                debug.write("Connected with {}:{}".format(address[0], address[1]), 0)
                client.settimeout(10)
                self.conn_sockets.append(threading.Thread(target=self.listen_client, args=(client, address)).start())
        except (KeyboardInterrupt, SystemExit):
            self.remove_server()

    def listen_client(self, client, address):
        """ Listens for new requests and handle them properly """
        streamingdev = False
        streaminggrp = False
        streaming_id = None
        try:
            while True:
                msize = int(client.recv(4).decode('utf-8'))
                if self.scheduled_disconnect is not None:
                    self.scheduled_disconnect.cancel()
                    self.scheduled_disconnect = None
                #debug.write("Set message size {}".format(msize), 0)
                data = client.recv(msize)
                if data:
                    if data.decode('utf-8') == "getstate":
                        ls_status = {}
                        ls_status["state"] = lm.get_state(async=True)
                        ls_status["mode"] = lm.get_modes()
                        ls_status["type"] = lm.get_types()
                        ls_status["name"] = lm.get_names()
                        ls_status["description"] = lm.get_descriptions(True)
                        ls_status["starttime"] = "{}".format(lm.starttime)
                        ls_status["groups"] = lm.get_all_groups()
                        debug.write('Sending lightserver status', 0)
                        client.send(json.dumps(ls_status).encode('UTF-8'))
                        # Run the non-async state getter after ?
                        if self.state_thread is None or not self.state_thread.is_alive():
                            self.state_thread = threading.Thread(target=lm.get_state)
                            self.state_thread.start()
                        break
                    if data.decode('utf-8') == "getstatepost":
                        ls_status = {}
                        while self.state_thread.is_alive():
                            time.sleep(0.2)
                        ls_status["state"] = lm.get_state(async=True)
                        client.send(json.dumps(ls_status).encode('UTF-8')) 
                        break
                    if data.decode('utf-8') == "setstate":
                        debug.write('Running a single device state change', 0)
                        iddata = int(client.recv(3).decode("UTF-8"))
                        valdata = int(client.recv(8).decode("UTF-8"))
                        skiptime = int(client.recv(1).decode("UTF-8"))
                        _col = ["-1"] * len(lm.devices)
                        _col[iddata] = str(valdata)
                        lm.set_colors(_col)
                        if skiptime == 1:
                            lm.set_skip_time_check()
                        lm.set_mode(False,False)
                        lm.run()
                        client.send("1".encode("UTF-8"))
                        break
                    if data.decode('utf-8') == "setmode":
                        debug.write('Running a single device mode change', 0)
                        iddata = int(client.recv(3).decode("UTF-8"))
                        cmode = int(client.recv(1).decode("UTF-8"))
                        if cmode == 1:
                            lm.set_mode_for_device(True, iddata)
                        else:
                            lm.set_mode_for_device(False, iddata)
                        debug.write('Device modes: {}'.format(lm.get_modes()), 0)
                        client.send("1".encode("UTF-8"))
                        break
                    if data.decode('utf-8') == "setgroup":
                        debug.write('Running a group change of state', 0)
                        group = str(client.recv(64).decode("UTF-8")).strip()
                        valdata = int(client.recv(2).decode("UTF-8"))
                        skiptime = int(client.recv(1).decode("UTF-8"))
                        _col = ["0"] * len(lm.devices)
                        if skiptime == 1:
                            lm.set_skip_time_check()
                        if valdata == 1:
                            _col = ["1"] * len(lm.devices)
                        lm.set_colors(_col)
                        lm.set_mode(False,False)
                        lm.get_group([group.replace("0", "").lower()])
                        lm.run()
                        client.send("1".encode("UTF-8"))
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
                    if data.decode('utf-8')[:3] == "tcp":
                        debug.write('Getting TCP request: {}'.format(data.decode('utf-8')), 0)
                        if self.tcp_start_hour > datetime.datetime.now().time() or \
                           self.tcp_end_hour < datetime.datetime.now().time():
                           debug.write('TCP requests disabled until {}'.format(self.tcp_start_hour), 0)
                           break
                        if data.decode('utf-8')[3:] in self.config["TCP-PRESETS"]:
                            debug.write("Running TCP preset {}".format(data.decode('utf-8')[3:]), 0)
                            if self.config["TCP-PRESETS"].getboolean('AUTOMATIC_MODE'):
                                os.system("./playclient.py --auto-mode " + self.config["TCP-PRESETS"][data.decode('utf-8')[3:]])
                            else:
                                os.system("./playclient.py " + self.config["TCP-PRESETS"][data.decode('utf-8')[3:]])
                        else:
                            debug.write("TCP preset {} is not configured".format(data.decode('utf-8')[3:]), 1)
                        break

                    if data.decode('utf-8') == "sendloc":
                        locationData = json.loads(client.recv(1024).decode("UTF-8"))
                        debug.write('Recording a training location for room: {}'.format(locationData["room"]), 0)
                        with open(self.config['SERVER']['JOURNAL_DIR'] + "/dnn/train.log", "a") as jfile:
                            jfile.write("{},{},{},{},{},{},{}\n".format(locationData["room"], locationData["r1_mean"], \
                                locationData["r1_rssi"],locationData["r2_mean"],locationData["r2_rssi"],locationData["r3_mean"] \
                                ,locationData["r3_rssi"]))
                        break
                    if data.decode('utf-8') == "getloc":
                        ld = json.loads(client.recv(1024).decode("UTF-8"))
                        debug.write('[WIFI-RTT] Evaluating location from:', 0)
                        tf_str = '{},{},{},{},{},{}'.format(ld["r1_mean"], ld["r1_rssi"], ld["r2_mean"], ld["r2_rssi"], ld["r3_mean"], ld["r3_rssi"])
                        debug.write('[WIFI-RTT] {}'.format(tf_str), 0)
                        res = run_tensorflow(TfPredict=True, PredictList=tf_str)
                        debug.write("[WIFI-RTT] Device found to be in room: {}".format(res), 0)
                        client.send(res.encode("UTF-8"))
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
            self.scheduled_disconnect = threading.Timer(60, self.disconnect_devices, ())
            self.scheduled_disconnect.start()

    def disconnect_devices(self):
        """ Disconnects all configured devices """
        self.scheduled_disconnect = None
        debug.write("Server unused. Disconnecting devices.", 0)
        for _dev in lm.devices:
            _dev.disconnect()

    def remove_server(self):
        """ Shuts down server and cleans resources """
        debug.write("Closing down server and lights.", 0)
        lm.stop_delayed_changes()
        lm.set_skip_time_check()
        lm.set_colors([LIGHT_OFF] * len(lm.devices))
        lm.set_mode(False,True)
        #lm.run()
        self.sock.close()
        debug.write("Closing remaining connections", 0)
        for _thr in self.conn_sockets:
            if _thr is not None:
                _thr.join()
        if self.scheduled_disconnect is not None:
            debug.write("Purging scheduled light changes", 0)
            self.scheduled_disconnect.cancel()
        debug.write("Disconnecting devices", 0)
        self.disconnect_devices()
        debug.write("Shutdown completed properly", 0)

    def _validate_and_execute_req(self, args):
        debug.write("Validating arguments", 0)
        if args["reset_location_data"]:
            #TODO eventually add training data cleanup
            os.remove("./dnn/train.log")
            debug.write("Purged location and RTT data", 0)
        if args["hexvalues"] and (args["playbulb"] or args["milight"] or args["decora"]
                                  or args["meross"] or args["tplinkswitch"]):
            debug.write("Got color hexvalues for milights and/or playbulbs \
                                   and/or other devices in the same request, which is not \
                                   supported. Use '{} -h' for help. Quitting".format(sys.argv[0]),
                                 2)
            return     
        if len(args["hexvalues"]) != len(lm.devices) and not any([args["notime"], args["off"], args["on"], 
                                                                  args["playbulb"], args["milight"], 
                                                                  args["toggle"], args["decora"], 
                                                                  args["preset"], args["restart"],
                                                                  args["meross"], args["tplinkswitch"]]):
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
            if args["set_mode_for_devid"] is not None:
                try:
                    debug.write("Received mode change request for devid {}".format(args["set_mode_for_devid"]), 0)
                    lm.set_mode_for_device(args["auto_mode"], args["set_mode_for_devid"])
                except KeyError:
                    debug.write("Devid {} does not exist".format(args["set_mode_for_devid"]), 1)
                return
            if args["playbulb"] is not None:
                debug.write("Received playbulb change request", 0)
                if not lm.set_typed_colors(args["playbulb"], "Playbulb"):
                    return
            if args["milight"] is not None:
                debug.write("Received milight change request", 0)
                if not lm.set_typed_colors(args["milight"], "Milight"):
                    return
            if args["decora"] is not None:
                debug.write("Received decora change request", 0)
                if not lm.set_typed_colors(args["decora"], "DecoraSwitch"):
                    return
            if args["meross"] is not None:
                debug.write("Received meross change request", 0)
                if not lm.set_typed_colors(args["meross"], "MerossSwitch"):
                    return
            if args["tplinkswitch"] is not None:
                debug.write("Received tplinkswitch change request", 0)
                if not lm.set_typed_colors(args["tplinkswitch"], "TP-LinkSwitch"):
                    return
            if args["preset"] is not None:
                debug.write("Received change to preset [{}] request".format(args["preset"]), 0)
                try:
                    lm.set_colors(self.config["PRESETS"][args["preset"]].split(','))
                    args["auto_mode"] = self.config["PRESETS"].getboolean("AUTOMATIC_MODE")
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
                if not lm.set_typed_colors(2, "GenericOnOff"):
                    return
            if args["toggle"]:
                debug.write("Received TOGGLE change request", 0)
                lm.set_colors(lm.get_toggle())
        if args["notime"] or args["off"]:
            lm.set_skip_time_check()
        if args["group"] is not None:
            lm.get_group(args["group"])
        debug.write("Arguments are OK", 0)
        lm.set_mode(args["auto_mode"], args["reset_mode"])
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
        if "tplinkswitch" not in args:
            args["tplinkswitch"] = None
        if "notime" not in args:
            args["notime"] = False
        if "delay" not in args:
            args["delay"] = None
        if "priority" in args and args["priority"] is None:
            args["priority"] = 1
        if "priority" not in args:
            args["priority"] = 1
        if "preset" not in args:
            args["preset"] = None
        if "group" not in args:
            args["group"] = None
        if "manual_mode" not in args:
            args["manual_mode"] = False
        if "reset_mode" not in args:
            args["reset_mode"] = False
        if "set_mode_for_devid" not in args:
            args["set_mode_for_devid"] = None
        if "reset_location_data" not in args:
            args["reset_location_data"] = False
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


class DeviceManager(object):
    """ Methods for instanciating and managing devices """
    def __init__(self, config=None):
        debug.get_set_lock()
        debug.enable_debug()
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
                debug.write('Loaded {} devices'.format(i-1), 0)
                break
            i = i + 1
        self.skip_time = False
        self.serverwide_skip_time = False
        self.lastupdate = None
        self.get_event_time()
        self.queue = queue.Queue()
        self.colors = ["-1"] * len(self.devices)
        self.delays = [0] * len(self.devices)
        self.scheduled_changes = []
        self.states = self.get_state()
        debug.write("Got initial device states {}".format(self.states), 0)
        self.set_lock(0)
        self.lockcount = 0
        self.priority = 0
        self.threaded = False
        self.light_threads = [None] * len(self.devices)
        self.light_pool = None
        self.all_groups = None

    def start_threaded(self):
        """ Enables multithreaded light change requests """
        self.threaded = True
        self.light_pool = ThreadPool(processes=4)

    def set_skip_time_check(self, serverwide=False):
        """ Enables skipping time check """
        if serverwide:
            debug.write("Skipping time check for all requests", 0)
            self.serverwide_skip_time = True
        else:
            debug.write("Skipping time check this time", 0)
            self.skip_time = True
            for _dev in self.devices:
                _dev.skip_time = True

    def set_colors(self, color):
        """ Setter function for color request. Required. """
        self.colors = color

    def set_mode(self, auto_mode, reset_mode):
        for _cnt, device in enumerate(self.devices):
            if self.colors[_cnt] != LIGHT_SKIP:
                self.devices[_cnt].request_auto_mode = auto_mode
                self.devices[_cnt].reset_mode = reset_mode

    def set_mode_for_device(self, auto_mode, devid):
        """ Used by the webserver to switch device modes one by one """
        self.devices[devid].auto_mode = auto_mode

    def get_group(self, group):
        """ Gets devices from a specific group for the light change """
        for _cnt, device in enumerate(self.devices):
            if group is not None and set(group).issubset(device.group):
                continue
            debug.write("Skipping device {} as it does not belong in the {} group(s)" \
                        .format(device.device, group), 0)
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

    def run(self, delay=None, colors=None, skiptime=None):
        """ Validates the request and runs the light change """
        self.clean_delayed_changes()
        if delay is not None:
            debug.write("Delaying request for {} seconds".format(delay), 0)
            _sched = threading.Timer(int(delay), self.run, (None,self.colors,self.skip_time,))
            _sched.start()
            self.scheduled_changes.append(_sched)
            self.skip_time = False
            return
        if self.check_event_time() or skiptime:
            if colors is not None:
                self.colors = colors
            if skiptime:
                self.set_skip_time_check()
            self.queue.put(self.colors)
            #TODO Manage locking out when the run thread hangs
            debug.write("Locked status: {}".format(self.locked), 0)
            if not self.locked or self.lockcount == 2:
                self._set_lights()
            else:
                self.lockcount = self.lockcount + 1

    def get_all_groups(self):
        if self.all_groups is None:
            _groups = []
            for obj in self.devices:
                for group in obj.group:
                    if group not in _groups:
                        _groups.append(group)
            self.all_groups = _groups
        return self.all_groups

    def get_descriptions(self, as_list = False):
        """ Getter for configured devices descriptions """
        desclist = []
        desctext = ""
        i = 1
        for obj in self.devices:
            desctext += str(i) + " - " + obj.descriptions() + "\n"
            if as_list:
                desclist.append(obj.descriptions())
            i += 1
        if as_list:
            return desclist
        return desctext

    def get_types(self):
        typelist = []
        for obj in self.devices:
            typelist.append(obj.__class__.__name__)
        return typelist

    def get_modes(self):
        modelist = []
        for obj in self.devices:
            modelist.append(obj.auto_mode)
        return modelist

    def get_names(self):
        namelist = []
        for obj in self.devices:
            if obj.name is not None:
                namelist.append(obj.name)
            else:
                # Fallback to device then device type
                try:
                    namelist.append(obj.device)
                except NameError:
                    namelist.append(obj.device_type)

        return namelist

    def get_event_time(self):
        if self.lastupdate != datetime.date.today():
            self.lastupdate = datetime.date.today()
            if str(self.config['SERVER']['EVENT_HOUR']) != "auto":
                self.lastupdate = datetime.date.today()
                self.starttime = datetime.datetime.strptime(self.config['SERVER']['EVENT_HOUR'],'%H:%M').time()
            else:
                self.lastupdate = datetime.date.today()
                self.starttime = self._update_sunset_time(self.config['SERVER']['EVENT_LOCALIZATION'])
                if not self.serverwide_skip_time:
                    debug.write("Event time set as sunset time: {}".format(self.starttime), 0)
        return self.starttime

    def check_event_time(self):
        self.get_event_time()
        if self.serverwide_skip_time:
            for _dev in self.devices:
                _dev.set_skip_time()
            return True
        if datetime.time(6, 00) < datetime.datetime.now().time() < self.starttime:
            for _dev in self.devices:
                if _dev.skip_time:
                    debug.write("Not all devices will be changed. Light changes begins at {}"
                                .format(self.starttime), 0)
                    return True
            debug.write("Too soon to change devices. Light changes begins at {}"
                        .format(self.starttime), 0)
            return False
        else:
            for _dev in self.devices:
                _dev.set_skip_time()
        return True

    def set_lock(self, is_locked):
        """ Locks the light change request """
        self.locked = is_locked

    def get_state(self, devid=None, async=False):
        """ Getter for configured devices actual colors """
        states = [None] * len(self.devices)
        for _cnt, dev in enumerate(self.devices):
            if devid is not None and devid != _cnt:
                continue
            if async:
                states[_cnt] = dev.state
            else:
                states[_cnt] = dev.get_state()
        debug.write("Got state status", 0)
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
                        if device.run(_color, 3):
                            break
                        time.sleep(0.3)
                        cnt = cnt + 1
        else:
            cnt = 0
            _color = device.convert(color)
            while True:
                if cnt == 4:
                    break
                if self.devices[devid].run(_color, 3):
                    break
                time.sleep(0.3)
                cnt = cnt + 1
        self.reinit()

    def clean_delayed_changes(self):
        for _sched in self.scheduled_changes:
            if _sched is not None and not _sched.isAlive():
                self.scheduled_changes.remove(_sched)

    def stop_delayed_changes(self):
        self.clean_delayed_changes()
        for _sched in self.scheduled_changes:
            if _sched is not None:
                _sched.cancel()

    def reinit(self):
        """ Resets the Success bool to False """
        i = 0
        while i < len(self.devices):
            self.devices[i].reinit()
            i += 1

    def _decode_colors(self, colors):
        _has_delays = False
        self.delays = [0] * len(self.devices)
        for _cnt, _col in enumerate(colors):
            if re.match("[0-9a-fA-F]+del[0-9]+", _col) is not None:
                """ This is a delayed change (delay then action) """
                _vals = _col.split("del")
                colors[_cnt] = _vals[0]
                self.delays[_cnt] = int(_vals[1])
                _has_delays = True
            if re.match("[0-9a-fA-F]+for[0-9]+", _col) is not None:
                """ This is a for-delay change (action, delay then off)"""
                _vals = _col.split("for")
                colors[_cnt] = _vals[0]
                self.delays[_cnt] = -int(_vals[1])
                _has_delays = True
        if _has_delays:
            _delay_list = []
            for _delay in self.delays:
                if _delay != 0 and _delay not in _delay_list:
                    _delay_list.append(_delay)
                    _delay_colors = [LIGHT_SKIP] * len(self.devices)
                    for _acnt,_adelay in enumerate(self.delays):
                        if _adelay == _delay:
                            #debug.write("COLORS: {} DELAY COLOR: {}".format(colors, _delay_colors), 0)
                            if _adelay < 0:
                                _delay_colors[_acnt] = LIGHT_OFF
                                _delay = -_delay
                            else:
                                _delay_colors[_acnt] = colors[_acnt]
                                colors[_acnt] = LIGHT_SKIP
                            self.delays[_acnt] = 0
                    debug.write("Scheduling light change ({}) after {} seconds".format(_delay_colors, _delay), 0)
                    _sched = threading.Timer(int(_delay), self.run, (None, _delay_colors, self.skip_time,))
                    _sched.start()
                    self.scheduled_changes.append(_sched)
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
                    if all(c == LIGHT_SKIP for c in colors):
                        debug.write("All device requests skipped", 0)
                        return                
                    debug.write("Changing colors to {} from state {}" \
                                .format(colors, self.states), 0)
                    self.set_lock(1)
                    i = 0
                    tries = 0
                    firstran = True

                    while i < len(self.devices):
                        if not self.devices[i].success:
                            _color = self.devices[i].convert(colors[i])

                            if _color != LIGHT_SKIP:
                                self.states[i] = self.get_state(i)
                                if _color != self.states[i]:
                                    debug.write(("DEVICE: {}, REQUESTED COLOR: {} "
                                                  "FROM STATE: {}, PRIORITY: {}, AUTO: {}")
                                                  .format(self.devices[i].device,
                                                          _color, self.states[i],
                                                          self.devices[i].priority,
                                                          self.devices[i].auto_mode),
                                                  0)
                            if self.threaded:
                                if not self.queue.empty():
                                    break

                                self.light_threads[i] = self.light_pool.apply_async(self._set_device,
                                                                                    args=(i, _color, 
                                                                                          self.priority))
                            else:
                                self._set_device(i, _color, self.priority)
                        i += 1

                        if i == len(self.devices):
                            if self.threaded:
                                debug.write("Awaiting results", 0)
                                for _cnt, _thread in enumerate(self.light_threads):
                                    if not self.queue.empty():
                                        continue
                                    if _thread is not None:
                                        try:
                                            if _thread.get(5) is not None:
                                                i = 0
                                        except:
                                            i = 0
                                tries = tries + 1
                                if tries == 5:
                                    break
                            else:
                                for _cnt, _dev in enumerate(self.devices):
                                    if not self.queue.empty():
                                        continue
                                    self.states[_cnt] = self.get_state(_cnt)
                                    if self.devices[_cnt].convert(colors[_cnt]) != self.states[_cnt]:
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
                self.states = self.get_state()

        except Exception as ex:
            debug.write('Unhandled exception of type {}: {}, {}'
                                  .format(type(ex), ex, 
                                          ''.join(traceback.format_tb(ex.__traceback__))), 2)

        finally:
            self.reinit()
            self.set_lock(0)
            self.skip_time = False

        debug.write("Change of lights completed.", 0)

    def _set_device(self, count, color, priority):
        return self.devices[count].run(color, priority)

    def _get_type_index(self, atype):
        # TODO This should not depend on an ordered set of devices
        i = 0
        count = 0
        firstindex = 0
        for obj in self.devices:
            if obj.device_type == atype:
                if count == 0: 
                    firstindex = i
                count += 1
            i += 1
        if count == 0:
            raise Exception('Invalid device type given. Quitting')
        return [count, firstindex]

    def _update_sunset_time(self, localization):
        p1 = subprocess.Popen('./scripts/sunset.sh %s' % str(localization), stdout=subprocess.PIPE, \
                              shell=True)
        (output,_) = p1.communicate()
        p1.wait()
        try:
            _time = datetime.datetime.strptime(output.rstrip().decode('UTF-8'),'%H:%M').time()
        except ValueError:
            debug.write("Connection error to the sunset time server. Falling back to 18:00.", 1)             
            _time = datetime.datetime.strptime("18:00",'%H:%M').time()
        return _time


def runServer():
    HomeServer(lm).listen()

""" Script executed directly """
if __name__ == "__main__":
    PLAYCONFIG = configparser.ConfigParser()
    PLAYCONFIG.read('play.ini')
    lm = DeviceManager(PLAYCONFIG)

    parser = argparse.ArgumentParser(description='BLE light bulbs manager script', epilog=lm.get_descriptions(),
                                     formatter_class=RawTextHelpFormatter)
    parser.add_argument('hexvalues', metavar='N', type=str, nargs="*",
                        help='color hex values for the lightbulbs (see list below)')
    parser.add_argument('--playbulb', metavar='P', type=str, nargs="*", help='Change playbulbs colors only')
    parser.add_argument('--milight', metavar='M', type=str, nargs="*", help='Change milights colors only')
    parser.add_argument('--decora', metavar='D', type=str, nargs="*", help='Change decora colors only')
    parser.add_argument('--meross', metavar='M', type=str, nargs="*", help='Change meross states only')
    parser.add_argument('--tplinkswitch', metavar='T', type=str, nargs="*", help='Change tplinkswitch states only')
    parser.add_argument('--priority', metavar='prio', type=int, nargs="?", default=1,
                        help='Request priority from 1 to 3')
    parser.add_argument('--preset', metavar='preset', type=str, nargs="?", default=None,
                        help='Apply light actions from specified preset name defined in play.ini')
    parser.add_argument('--group', metavar='group', type=str, nargs="+", default=None,
                        help='Apply light actions on specified device group(s)')
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
    parser.add_argument('--webserver', metavar='prio', type=int, nargs="?", default=0,
                        help='Starts a webserver at the given PORT')
    parser.add_argument('--voice', action='store_true', default=False,
                        help='Start a voice-assistant websocket receiver along with server')
    parser.add_argument('--detector', action='store_true', default=False,
                        help='Start a ping-based device detector (usually for mobiles)')
    parser.add_argument('--threaded', action='store_true', default=False,
                        help='Starts the server daemon with threaded light change requests')
    parser.add_argument('--stream-dev', metavar='str-dev', type=int, nargs="?", default=None,
                        help='Stream colors directly to device id')
    parser.add_argument('--stream-group', metavar='str-grp', type=str, nargs="?", default=None,
                        help='Stream colors directly to device group')
    parser.add_argument('--reset-mode', action='store_true', default=False,
                        help='Force light change (whatever the actual mode) and set back devices to AUTO mode')
    parser.add_argument('--reset-location-data', action='store_true', default=False,
                        help='Purge all RTT, locations and location training data (default: false)')
    parser.add_argument('--auto-mode', action='store_true', default=False,
                        help='(internal) Run requests for non-LIGHT_SKIP devices as AUTO mode (default: false)')
    parser.add_argument('--set-mode-for-devid', metavar='devid', type=int, nargs="?", default=None,
                        help='(internal) Force device# to change mode (as set by auto-mode)')

    args = parser.parse_args()

    if args.server and (args.playbulb or args.milight or args.decora or args.on
                        or args.off or args.toggle or args.stream_dev
                        or args.stream_group or args.preset or args.restart 
                        or args.meross or args.tplinkswitch):
        debug.write("You cannot start the daemon and send arguments at the same time. \
                              Quitting.", 2)
        sys.exit()

    voice_server = None
    if args.voice:
        voice_server = PLAYCONFIG['SERVER']['VOICE_SERVER_TYPE']
        if voice_server not in ['none', 'dialogflow', 'ifttt']:
            debug.write("Invalid voice assistant server type. Choose between none, dialogflow or ifttt. Quitting.", 2)
            sys.exit()
        if voice_server == 'none':
            voice_server = None

    if args.stream_dev and args.stream_group:
        debug.write("You cannot stream data to both devices and groups. Quitting.", 2)
        sys.exit()

    if args.reset_mode and args.auto_mode:
        debug.write("You should not set the mode to AUTO then reset it back to AUTO. Quitting.", 2)
        sys.exit()

    if args.server:
        if PLAYCONFIG['SERVER'].getboolean('ENABLE_WIFI_RTT'):
            from dnn.dnn import run_tensorflow
        if args.webserver is None:
            debug.write("You need to define a port for the webserver, using --webserver PORT. Quitting.", 2)
            sys.exit()
        if args.notime:
            lm.set_skip_time_check(True)
        if args.threaded:
            lm.start_threaded()
        if voice_server is not None:
            if voice_server == 'ifttt':
                from modules.ifttt import runIFTTTServer
                ti = runIFTTTServer(PLAYCONFIG['SERVER'].getint('VOICE_SERVER_PORT'))
                ti.start()
            elif voice_server == 'dialogflow':
                from modules.dialogflow import runDFServer
                ti = runDFServer(PLAYCONFIG)
                ti.start()
        if args.detector:
            from modules.detector import runDetectorServer
            td = runDetectorServer(PLAYCONFIG, lm)
            td.start()
        if args.webserver != 0:
            from modules.webserver import runWebServer
            tw = runWebServer(args.webserver,PLAYCONFIG)
            tw.start()
        runServer()
        if voice_server is not None:
            ti.stop()
            ti.join()
        if args.webserver != 0:
            tw.stop()
            tw.join()
        if args.detector:
            td.stop()
            td.join()
        debug.write("Threaded modules stopped.", 0)


    elif args.stream_dev or args.stream_group:
        colorval = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((PLAYCONFIG['SERVER']['HOST'], int(PLAYCONFIG['SERVER'].getint('PORT'))))
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
                    s.connect((PLAYCONFIG['SERVER']['HOST'], int(PLAYCONFIG['SERVER'].getint('PORT'))))
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
        s.connect((PLAYCONFIG['SERVER']['HOST'], int(PLAYCONFIG['SERVER'].getint('PORT'))))
        #TODO report connection errors or allow feedback response
        debug.write('Connecting with lightmanager daemon', 0)
        debug.write('Sending request: ' + json.dumps(vars(args)), 0)
        s.sendall("1024".encode('utf-8'))
        s.sendall(json.dumps(vars(args)).encode('utf-8'))
        s.close()

    quit()

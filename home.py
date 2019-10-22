#!/usr/bin/env python3
'''
    File name: home.py
    Author: Maxime Bergeron
    Date last modified: 11/10/2019
    Python Version: 3.5

    A python home control server
'''
import argparse
import configparser
import datetime
import json
import os
import pickle
import socket
import sys
import threading
import time
import traceback
from core.common import *
from core.devicemanager import DeviceManager, StateRequestObject
from argparse import RawTextHelpFormatter
from shutil import copyfile
from __main__ import *


class HomeServer(object):
    """ Handles server-side request reception and handling """

    def __init__(self, dm):
        self.config = configparser.ConfigParser()
        self.config.read('home.ini')
        self.host = self.config['SERVER']['HOST']
        self.port = int(self.config['SERVER'].getint('PORT'))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.scheduled_disconnect = None
        self.tcp_start_hour = datetime.datetime.strptime(
            self.config['SERVER']['TCP_START_HOUR'], '%H:%M').time()
        self.tcp_end_hour = datetime.datetime.strptime(
            self.config['SERVER']['TCP_END_HOUR'], '%H:%M').time()
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
                debug.write("Connected with {}:{}".format(
                    address[0], address[1]), 0)
                client.settimeout(10)
                self.conn_sockets.append(threading.Thread(
                    target=self.listen_client, args=(client, address)).start())
        except (KeyboardInterrupt, SystemExit):
            self.remove_server()

    def listen_client(self, client, address):
        """ Listens for new requests and handle them properly """
        try:
            while True:
                msize = int(client.recv(4).decode('utf-8'))
                if self.scheduled_disconnect is not None:
                    self.scheduled_disconnect.cancel()
                    self.scheduled_disconnect = None
                data = client.recv(msize)
                if data:
                    # TODO use the recv length to determine pickled vs non-pickled requests ?
                    if msize != 2048:
                        req = StateRequestObject()
                        if self.check_for_function_request(data.decode('utf-8'), req, client):
                            break
                    try:
                        req = pickle.loads(data)
                    except:
                        debug.write(
                            "Error - improperly formatted pickle. Got: {}".format(data), 2)
                        break
                    debug.write('Change of lights requested with request: {}'.format(
                        req.get_request_string()), 0)
                    if not req.validate_request(dm, self.config):
                        debug.write(
                            "Some errors in the request prevent a proper state change", 1)
                    break

        except socket.timeout:
            pass

        except Exception as ex:
            debug.write('Unhandled exception of type {}: {}, {}'
                        .format(type(ex), ex,
                                ''.join(traceback.format_tb(
                                    ex.__traceback__))
                                ), 2)

        finally:
            debug.write('Closing connection.', 0)
            dm.set_lock(0)
            dm.reinit()
            client.close()
            self.scheduled_disconnect = threading.Timer(
                60, self.disconnect_devices, ())
            self.scheduled_disconnect.start()

    def check_for_function_request(self, data, req, client):
        streamingdev = False
        streaminggrp = False
        streaming_id = None

        if data == "getstate":
            ls_status = {}
            ls_status["state"] = dm.get_state(
                async=True, webcolors=True)
            ls_status["intensity"] = dm.get_state(
                async=True, intensity=True)
            ls_status["mode"] = dm.get_modes()
            ls_status["type"] = dm.get_types()
            ls_status["name"] = dm.get_names()
            for op in ["skiptime", "forceoff", "ignoremode", "actiondelay"]:
                ls_status["op_" + op] = dm.get_option(op)
            ls_status["icon"] = dm.get_icons()
            ls_status["description"] = dm.get_descriptions(
                True)
            ls_status["starttime"] = "{}".format(dm.starttime)
            ls_status["groups"] = dm.get_all_groups()
            ls_status["colortype"] = dm.get_colortypes()
            ls_status["moduleweb"] = dm.get_module_web()
            ls_status["locked"] = dm.get_lock_status()
            ls_status["roomgroups"] = ""
            if self.config.has_option("WEBSERVER", "ROOM_GROUPS"):
                ls_status["roomgroups"] = self.config["WEBSERVER"]["ROOM_GROUPS"]
            ls_status["deviceroom"] = dm.get_room_for_devices()
            debug.write('Sending lightserver status', 0)
            client.send(json.dumps(ls_status).encode('UTF-8'))
            # Run the non-async state getter after ?
            if self.state_thread is None or not self.state_thread.is_alive():
                self.state_thread = threading.Thread(
                    target=dm.get_state)
                self.state_thread.start()
            return True

        # TODO how to deprecate this ? This requires another connection to allow new async requests from the webserver
        if data == "getstatepost":
            ls_status = {}
            while self.state_thread.is_alive():
                time.sleep(0.2)
            ls_status["state"] = dm.get_state(
                async=True, webcolors=True)
            ls_status["intensity"] = dm.get_state(
                async=True, intensity=True)
            ls_status["mode"] = dm.get_modes()
            client.send(json.dumps(ls_status).encode('UTF-8'))
            return True

        if data == "setstate":
            debug.write(
                'Running a single device state change', 0)
            iddata = int(client.recv(3).decode("UTF-8"))
            valdata = client.recv(8).decode("UTF-8")
            isintensity = client.recv(1).decode("UTF-8")
            skiptime = int(client.recv(1).decode("UTF-8"))
            _col = ["-1"] * len(dm.devices)
            try:
                valdata = int(valdata)
                if isintensity == "1" and dm.devices[iddata].color_type == "255":
                    valdata = (None, valdata)
            except ValueError:
                # Must be hexadecimal
                valdata = valdata[2:9]
            _col[iddata] = valdata
            req.set_colors(_col, len(dm.devices))
            if skiptime == 1:
                req.set(skip_time=True)
            dm.run(req)
            client.send("1".encode("UTF-8"))
            return True

        if data == "setmode":
            debug.write(
                'Running a single device mode change', 0)
            iddata = int(client.recv(3).decode("UTF-8"))
            cmode = int(client.recv(1).decode("UTF-8"))
            req.set_mode_for_devid = iddata
            if cmode == 1:
                req.set(auto_mode=True)
            dm.run(req)
            debug.write('Device modes: {}'.format(
                dm.get_modes()), 0)
            client.send("1".encode("UTF-8"))
            return True

        if data == "setallmode":
            debug.write(
                'Running an all-devices mode change', 0)
            req.set(force_auto_mode=True)
            dm.run(req)
            debug.write('Device modes: {}'.format(
                dm.get_modes()), 0)
            client.send("1".encode("UTF-8"))
            return True

        if data == "setgroup":
            debug.write('Running a group change of state', 0)
            group = str(client.recv(
                64).decode("UTF-8")).strip()
            valdata = int(client.recv(2).decode("UTF-8"))
            skiptime = int(client.recv(1).decode("UTF-8"))
            _col = ["0"] * len(dm.devices)
            if skiptime == 1:
                req.set(skip_time=True)
            if valdata == 1:
                _col = ["1"] * len(dm.devices)
            req.set_colors(_col, len(dm.devices))
            req.set(group=[group.replace("0", "").lower()])
            dm.run(req)
            client.send("1".encode("UTF-8"))
            return True

        # TODO Create some protocol to link webserver to modules directly ?
        if data == "getmodule":
            module = str(client.recv(64).decode(
                "UTF-8")).replace("0", "")
            debug.write(
                'Getting module "{}" web content'.format(module), 0)
            content = None
            for _mod in dm.modules:
                if _mod.__class__.__name__ == module:
                    content = _mod.get_web()
            if content is None:
                debug.write('Cannot find module', 1)
                client.send("0".encode("UTF-8"))
            else:
                client.send(content.encode("UTF-8"))
            return True

        if data == "dobackup":
            clientid = int(client.recv(4).decode("UTF-8"))
            debug.write('Scheduling backup', 0)
            for _mod in dm.modules:
                if _mod.__class__.__name__ == "backup":
                    content = _mod.backup_queue.put(clientid)
            client.send("1".encode("UTF-8"))
            return True

        if data == "setlock":
            iddata = int(client.recv(3).decode("UTF-8"))
            lock_req = client.recv(1).decode("UTF-8")
            dm.devices[int(iddata)].lock_unlock_requests(
                int(lock_req))
            client.send("1".encode("UTF-8"))
            return True

        if data == "getconfig":
            _conf_dict = {s: dict(self.config.items(s))
                          for s in self.config.sections()}
            client.send(json.dumps(_conf_dict).encode('UTF-8'))
            return True

        if data == "setconfig":
            msglen = int(client.recv(4).decode("UTF-8"))
            section = str(client.recv(msglen).decode("UTF-8"))
            configdata = json.loads(client.recv(8182).decode("UTF-8"))
            has_changes = False
            for entry in configdata:
                if self.config[str(section).upper()][entry] != configdata[entry]:
                    debug.write("Changing configuration entry {} to {}".format(
                        entry.upper(), configdata[entry]), 0)
                    self.config.set(str(section).upper(),
                                    entry.upper(), configdata[entry])
                    has_changes = True
            if has_changes:
                debug.write(
                    "Changing local config file and creating backup 'home.old'", 0)
                with open('home.ini', 'w') as configfile:
                    copyfile('home.ini', 'home.old')
                    self.config.write(configfile)
                dm.reload_configs()
            return True

        if data == "stream":
            debug.write('Starting streaming mode', 0)
            streamingdev = True

        if data == "streamgroup":
            debug.write('Starting group streaming mode', 0)
            streaminggrp = True

        if data == "nostream":
            debug.write('Ending streaming mode', 0)
            streamingdev = False
            streaminggrp = False
            streaming_id = None
            return True

        if data[:3] == "tcp":
            debug.write('Getting TCP request: {}'.format(
                data), 0)
            if self.tcp_start_hour > datetime.datetime.now().time() or \
               self.tcp_end_hour < datetime.datetime.now().time():
                debug.write('TCP requests disabled until {}'.format(
                    self.tcp_start_hour), 0)
                return True
            if data[3:] in self.config["TCP-PRESETS"]:
                debug.write("Running TCP preset {}".format(
                    data[3:]), 0)
                if self.config["TCP-PRESETS"].getboolean('AUTOMATIC_MODE'):
                    StateRequestObject(auto_mode=True, hexvalues=self.config["TCP-PRESETS"][data[3:]]).run(self.lm)
                else:
                    StateRequestObject(hexvalues=self.config["TCP-PRESETS"][data[3:]]).run(self.lm)
            else:
                debug.write("TCP preset {} is not configured".format(
                    data[3:]), 1)
            return True

        if data == "sendloc":
            locationData = json.loads(
                client.recv(1024).decode("UTF-8"))
            debug.write('Recording a training location for room: {}'.format(
                locationData["room"]), 0)
            with open(self.config['SERVER']['JOURNAL_DIR'] + "/dnn/train.log", "a") as jfile:
                jfile.write("{},{},{},{},{},{},{}\n".format(locationData["room"], locationData["r1_mean"],
                                                            locationData["r1_rssi"], locationData["r2_mean"], locationData["r2_rssi"], locationData["r3_mean"], locationData["r3_rssi"]))
            return True

        if data == "getloc":
            ld = json.loads(client.recv(1024).decode("UTF-8"))
            debug.write(
                '[WIFI-RTT] Evaluating location from:', 0)
            tf_str = '{},{},{},{},{},{}'.format(
                ld["r1_mean"], ld["r1_rssi"], ld["r2_mean"], ld["r2_rssi"], ld["r3_mean"], ld["r3_rssi"])
            debug.write('[WIFI-RTT] {}'.format(tf_str), 0)
            res = run_tensorflow(
                TfPredict=True, PredictList=tf_str)
            debug.write(
                "[WIFI-RTT] Device found to be in room: {}".format(res), 0)
            client.send(res.encode("UTF-8"))
            return True

        if streamingdev:
            if streaming_id is None:
                streaming_id = int(data)
                debug.write('Set streaming devid to {}'
                            .format(streaming_id), 0)
            else:
                debug.write("Sending request to devid {} for color: {}"
                            .format(streaming_id, data), 0)
                dm.set_light_stream(
                    streaming_id, data, False)

        if streaminggrp:
            if streaming_id is None:
                streaming_id = data
                debug.write('Set streaming group to {}'
                            .format(streaming_id), 0)
            else:
                debug.write("Sending request to group '{}' for color: {}"
                            .format(streaming_id, data), 0)
                dm.set_light_stream(
                    streaming_id, data, True)
        return False

    def disconnect_devices(self):
        """ Disconnects all configured devices """
        self.scheduled_disconnect = None
        debug.write("Server unused. Disconnecting devices.", 0)
        for _dev in dm.devices:
            _dev.disconnect()

    def remove_server(self):
        """ Shuts down server and cleans resources """
        debug.write("Closing down server and lights.", 0)
        dm.stop_delayed_changes()
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


def runServer():
    HomeServer(dm).listen()


""" Script executed directly """
if __name__ == "__main__":
    HOMECONFIG = configparser.ConfigParser()
    HOMECONFIG.read('home.ini')
    dm = DeviceManager(HOMECONFIG)
    req = StateRequestObject()

    parser = argparse.ArgumentParser(description='Home server manager script', epilog=dm.get_descriptions(),
                                     formatter_class=RawTextHelpFormatter)
    parser.add_argument('hexvalues', metavar='N', type=str, nargs="*",
                        help='state values for the devices (see list below)')

    for _dev in getDevices(True):
        parser.add_argument('--' + _dev, type=str, nargs="*",
                            help='Change {} states only'.format(_dev))

    parser.add_argument('--preset', metavar='preset', type=str, nargs="?", default=None,
                        help='Apply state change actions from specified preset name defined in home.ini')
    parser.add_argument('--group', metavar='group', type=str, nargs="+", default=None,
                        help='Apply state change on specified device group(s)')
    parser.add_argument('--notime', action='store_true', default=False,
                        help='Skip the time check and run the script anyways')
    parser.add_argument('--delay', metavar='delay', type=int, nargs="?", default=0,
                        help='Run the request after a given number of seconds')
    parser.add_argument('--on', action='store_true',
                        default=False, help='Turn everything on')
    parser.add_argument('--off', action='store_true',
                        default=False, help='Turn everything off')
    parser.add_argument('--restart', action='store_true',
                        default=False, help='Restart generics')
    parser.add_argument('--toggle', action='store_true',
                        default=False, help='Toggle all devices on/off')
    parser.add_argument('--server', action='store_true', default=False,
                        help='Start as a socket server daemon')
    parser.add_argument('--threaded', action='store_true', default=False,
                        help='Starts the server daemon with threaded light change requests')
    parser.add_argument('--stream-dev', metavar='str-dev', type=int, nargs="?", default=None,
                        help='Stream colors directly to device id')
    parser.add_argument('--stream-group', metavar='str-grp', type=str, nargs="?", default=None,
                        help='Stream colors directly to device group')
    parser.add_argument('--reset-mode', action='store_true', default=False,
                        help='Force device state change (whatever the actual mode) and set back devices to AUTO mode')
    parser.add_argument('--reset-location-data', action='store_true', default=False,
                        help='Purge all RTT, locations and location training data (default: false)')
    parser.add_argument('--auto-mode', action='store_true', default=False,
                        help='(internal) Run requests for non-DEVICE_SKIP devices as AUTO mode (default: false)')
    parser.add_argument('--set-mode-for-devid', metavar='devid', type=int, nargs="?", default=None,
                        help='(internal) Force device# to change mode (as set by auto-mode)')

    args = parser.parse_args()

    # TODO add back device state change  request validation or just ignore?
    if args.server and (args.on or args.off or args.toggle or args.stream_dev
                        or args.stream_group or args.preset or args.restart):
        debug.write("You cannot start the daemon and send arguments at the same time. \
                              Quitting.", 2)
        sys.exit()

    if args.stream_dev and args.stream_group:
        debug.write(
            "You cannot stream data to both devices and groups. Quitting.", 2)
        sys.exit()

    if args.reset_mode and args.auto_mode:
        debug.write(
            "You should not set the mode to AUTO then reset it back to AUTO. Quitting.", 2)
        sys.exit()

    if args.server:
        loaded_modules = HOMECONFIG['SERVER']['MODULES'].split(",")
        # TODO put that check in some module?
        if all(x in loaded_modules for x in ['ifttt', 'dialogflow']):
            debug.write(
                "You cannot load ifttt and dialogflow at the same time. Quitting.", 2)
            sys.exit()

        for _cnt, _mod in enumerate(loaded_modules):
            if _mod in getModules():
                _module = __import__("modules." + _mod)
                # TODO Needed twice ? looks unpythonic
                _class = getattr(_module, _mod)
                _class = getattr(_class, _mod)
                dm.modules.append(_class(HOMECONFIG, dm))
                dm.modules[_cnt].start()
            else:
                debug.write('Unsupported module {}'
                            .format(_mod), 1)

        if HOMECONFIG['SERVER'].getboolean('ENABLE_WIFI_RTT'):
            from dnn.dnn import run_tensorflow
        if args.notime:
            dm.set_serverwide_skiptime()
        if args.threaded:
            dm.start_threaded()

        runServer()

        for _mod in dm.modules:
            try:
                _mod.stop()
            except AttributeError:
                pass
            _mod.join()

        debug.write("Threaded modules stopped.", 0)

    elif args.stream_dev or args.stream_group:
        colorval = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOMECONFIG['SERVER']['HOST'], int(
            HOMECONFIG['SERVER'].getint('PORT'))))
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
                colorval = input("Set device {} to state value ('quit' to exit): "
                                 .format(args.stream_dev))
            else:
                colorval = input("Set group '{}' to state value ('quit' to exit): "
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
                    s.connect((HOMECONFIG['SERVER']['HOST'], int(
                        HOMECONFIG['SERVER'].getint('PORT'))))
                    if args.stream_dev:
                        s.sendall("0006".encode('utf-8'))
                        s.sendall("stream".encode('utf-8'))
                        s.sendall(('%04d' % args.stream_dev).encode('utf-8'))
                        s.sendall(str(args.stream_dev).encode('utf-8'))
                    else:
                        s.sendall("0011".encode('utf-8'))
                        s.sendall("streamgroup".encode('utf-8'))
                        s.sendall(
                            ('%04d' % len(args.stream_group)).encode('utf-8'))
                        s.sendall(args.stream_group.encode('utf-8'))
                    s.sendall(('%04d' % len(colorval)).encode('utf-8'))
                    s.sendall(colorval.encode('utf-8'))
                    continue
        s.close()

    else:
        req.parse_args(args)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOMECONFIG['SERVER']['HOST'], int(
            HOMECONFIG['SERVER'].getint('PORT'))))
        # TODO report connection errors or allow feedback response
        debug.write('Connecting with homeserver daemon', 0)
        debug.write('Sending request: {}'.format(
            req.get_request_string()), 0, "CLIENT")
        s.sendall("2048".encode('utf-8'))
        s.sendall(pickle.dumps(req))
        s.close()

    quit()

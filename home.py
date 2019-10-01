#!/usr/bin/env python3
'''
    File name: home.py
    Author: Maxime Bergeron
    Date last modified: 01/10/2019
    Python Version: 3.5

    A python home control server
'''
import argparse
import configparser
import datetime
import json
import os
import queue
import sys
import socket
import threading
import time
import traceback
from core.common import *
from core.devicemanager import DeviceManager
from argparse import RawTextHelpFormatter, Namespace
from __main__ import *

class HomeServer(object):
    """ Handles server-side request reception and handling """
    def __init__(self, lm):
        self.config = configparser.ConfigParser()
        self.config.read('home.ini')
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
                        ls_status["state"] = lm.get_state(async=True, webcolors=True)
                        ls_status["mode"] = lm.get_modes()
                        ls_status["type"] = lm.get_types()
                        ls_status["name"] = lm.get_names()
                        for op in ["skiptime", "forceoff", "ignoremode", "actiondelay"]:
                            ls_status["op_" + op] = lm.get_option(op)
                        ls_status["icon"] = lm.get_icons()
                        ls_status["description"] = lm.get_descriptions(True)
                        ls_status["starttime"] = "{}".format(lm.starttime)
                        ls_status["groups"] = lm.get_all_groups()
                        ls_status["colortype"] = lm.get_colortypes()
                        ls_status["moduleweb"] = lm.get_module_web()
                        debug.write('Sending lightserver status', 0)
                        client.send(json.dumps(ls_status).encode('UTF-8'))
                        # Run the non-async state getter after ?
                        if self.state_thread is None or not self.state_thread.is_alive():
                            self.state_thread = threading.Thread(target=lm.get_state)
                            self.state_thread.start()
                        break
                    #TODO how to deprecate this ? This requires another connection to allow new async requests from the webserver
                    if data.decode('utf-8') == "getstatepost":
                        ls_status = {}
                        while self.state_thread.is_alive():
                            time.sleep(0.2)
                        ls_status["state"] = lm.get_state(async=True, webcolors=True)
                        client.send(json.dumps(ls_status).encode('UTF-8')) 
                        break
                    if data.decode('utf-8') == "setstate":
                        debug.write('Running a single device state change', 0)
                        iddata = int(client.recv(3).decode("UTF-8"))
                        valdata = client.recv(8).decode("UTF-8")
                        try:
                            valdata = int(valdata)
                        except ValueError:
                            # Must be hexadecimal
                            valdata = valdata[2:9]
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
                    if data.decode('utf-8') == "setallmode":
                        debug.write('Running an all-devices mode change', 0)
                        lm.set_mode(False,False,True)
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
                    #TODO Create some protocol to link webserver to modules directly ?
                    if data.decode('utf-8') == "getmodule":
                        module = str(client.recv(64).decode("UTF-8")).replace("0", "")
                        debug.write('Getting module "{}" web content'.format(module), 0)
                        content = None
                        for _mod in lm.modules:
                            if _mod.__class__.__name__ == module:
                                content = _mod.webcontent
                        if content is None:
                            debug.write('Cannot find module', 1)
                            client.send("0".encode("UTF-8"))
                        else:
                            client.send(content.encode("UTF-8"))
                        break
                    if data.decode('utf-8') == "dobackup":
                        clientid = int(client.recv(4).decode("UTF-8"))
                        debug.write('Scheduling backup', 0)
                        for _mod in lm.modules:
                            if _mod.__class__.__name__ == "backup":
                                content = _mod.backup_queue.put(clientid)
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
                                os.system("./homeclient.py --auto-mode " + self.config["TCP-PRESETS"][data.decode('utf-8')[3:]])
                            else:
                                os.system("./homeclient.py " + self.config["TCP-PRESETS"][data.decode('utf-8')[3:]])
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
        lm.set_colors([DEVICE_OFF] * len(lm.devices))
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

        has_device_requests = False
        for _dev in getDevices(True):
            if args[_dev]:
                has_device_requests = True

        if args["hexvalues"] and has_device_requests:            
            debug.write("Got color hexvalues for multiple devices in the same request, which is not \
                        supported. Use '{} -h' for help. Quitting".format(sys.argv[0]),
                        2)
            return

        if len(args["hexvalues"]) != len(lm.devices) and not any([args["notime"], args["off"], args["on"],
                                                                  args["toggle"], args["preset"], args["restart"],
                                                                  has_device_requests]):
            debug.write("Got {} color hexvalues, {} expected. Use '{} -h' for help. Quitting" \
                                  .format(len(args["hexvalues"]), len(lm.devices), sys.argv[0]), 2)
            return
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

            for _dev in getDevices(True):
                if args[_dev] is not None:
                    debug.write("Received {} change request".format(_dev), 0)
                    if not lm.set_typed_colors(args[_dev], _dev):
                        return

            if args["preset"] is not None:
                debug.write("Received change to preset [{}] request".format(args["preset"]), 0)
                try:
                    preset_colors = self.config["PRESETS"][args["preset"]].split(',')
                    if len(preset_colors) != len(lm.devices):
                        debug.write("Preset '{}' does not have the adequate number of states, {} expected.".format(args["preset"],len(lm.devices)),1)
                        return
                    lm.set_colors(self.config["PRESETS"][args["preset"]].split(','))
                    args["auto_mode"] = self.config["PRESETS"].getboolean("AUTOMATIC_MODE")
                except:
                    debug.write("Preset '{}' not found in home.ini. Quitting.".format(args["preset"]), 3)
                    return                       
            if args["off"]:
                debug.write("Received OFF change request", 0)
                lm.set_colors([DEVICE_OFF] * len(lm.devices))
            if args["on"]:
                debug.write("Received ON change request", 0)
                lm.set_colors([DEVICE_ON] * len(lm.devices))
            if args["restart"]:
                debug.write("Received RESTART change request", 0)
                if not lm.set_typed_colors(["2"], "GenericOnOff"):
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
        for _dev in getDevices(True):
            if _dev not in args:
                args[_dev] = None
            if type(args[_dev]).__name__ == "str":
                debug.write('Converting values to lists for {}'.format(_dev), 0)
                args[_dev] = args[_dev].replace("'", "").split(',')
        if "notime" not in args:
            args["notime"] = False
        if "delay" not in args:
            args["delay"] = None
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
        return args


def runServer():
    HomeServer(lm).listen()

""" Script executed directly """
if __name__ == "__main__":
    HOMECONFIG = configparser.ConfigParser()
    HOMECONFIG.read('home.ini')
    lm = DeviceManager(HOMECONFIG)

    parser = argparse.ArgumentParser(description='Home server manager script', epilog=lm.get_descriptions(),
                                     formatter_class=RawTextHelpFormatter)
    parser.add_argument('hexvalues', metavar='N', type=str, nargs="*",
                        help='state values for the devices (see list below)')

    for _dev in getDevices(True):
        parser.add_argument('--' + _dev, type=str, nargs="*", help='Change {} states only'.format(_dev))

    parser.add_argument('--preset', metavar='preset', type=str, nargs="?", default=None,
                        help='Apply state change actions from specified preset name defined in home.ini')
    parser.add_argument('--group', metavar='group', type=str, nargs="+", default=None,
                        help='Apply state change on specified device group(s)')
    parser.add_argument('--notime', action='store_true', default=False,
                        help='Skip the time check and run the script anyways')
    parser.add_argument('--delay', metavar='delay', type=int, nargs="?", default=None,
                        help='Run the request after a given number of seconds')
    parser.add_argument('--on', action='store_true', default=False, help='Turn everything on')
    parser.add_argument('--off', action='store_true', default=False, help='Turn everything off')
    parser.add_argument('--restart', action='store_true', default=False, help='Restart generics')
    parser.add_argument('--toggle', action='store_true', default=False, help='Toggle all devices on/off')
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

    #TODO add back device state change  request validation or just ignore?
    if args.server and (args.on or args.off or args.toggle or args.stream_dev
                        or args.stream_group or args.preset or args.restart):
        debug.write("You cannot start the daemon and send arguments at the same time. \
                              Quitting.", 2)
        sys.exit()

    if args.stream_dev and args.stream_group:
        debug.write("You cannot stream data to both devices and groups. Quitting.", 2)
        sys.exit()

    if args.reset_mode and args.auto_mode:
        debug.write("You should not set the mode to AUTO then reset it back to AUTO. Quitting.", 2)
        sys.exit()

    if args.server:
        loaded_modules = HOMECONFIG['SERVER']['MODULES'].split(",")
        #TODO put that check in some module?
        if all(x in loaded_modules for x in ['ifttt', 'dialogflow']):
            debug.write("You cannot load ifttt and dialogflow at the same time. Quitting.", 2)
            sys.exit()

        for _cnt,_mod in enumerate(loaded_modules):
            if _mod in getModules():
                _module = __import__("modules." + _mod)
                #TODO Needed twice ? looks unpythonic
                _class = getattr(_module,_mod)
                _class = getattr(_class,_mod)
                lm.modules.append(_class(HOMECONFIG, lm))
                lm.modules[_cnt].start()
            else:
                debug.write('Unsupported module {}' \
                                      .format(_mod), 1)

        if HOMECONFIG['SERVER'].getboolean('ENABLE_WIFI_RTT'):
            from dnn.dnn import run_tensorflow
        if args.notime:
            lm.set_skip_time_check(True)
        if args.threaded:
            lm.start_threaded()

        runServer()

        for _mod in lm.modules:
            try:
                _mod.stop()
            except AttributeError:
                pass
            _mod.join()

        debug.write("Threaded modules stopped.", 0)


    elif args.stream_dev or args.stream_group:
        colorval = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOMECONFIG['SERVER']['HOST'], int(HOMECONFIG['SERVER'].getint('PORT'))))
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
                colorval = input("Set device {} to state value ('quit' to exit): " \
                                  .format(args.stream_dev))
            else:
                colorval = input("Set group '{}' to state value ('quit' to exit): " \
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
                    s.connect((HOMECONFIG['SERVER']['HOST'], int(HOMECONFIG['SERVER'].getint('PORT'))))
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
        s.connect((HOMECONFIG['SERVER']['HOST'], int(HOMECONFIG['SERVER'].getint('PORT'))))
        #TODO report connection errors or allow feedback response
        debug.write('Connecting with homeserver daemon', 0)
        debug.write('Sending request: ' + json.dumps(vars(args)), 0)
        s.sendall("1024".encode('utf-8'))
        s.sendall(json.dumps(vars(args)).encode('utf-8'))
        s.close()

    quit()

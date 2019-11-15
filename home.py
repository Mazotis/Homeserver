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
import pickle
import socket
import sys
import threading
import traceback
from core.common import *
from core.devicemanager import DeviceManager, StateRequestObject
from argparse import RawTextHelpFormatter
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
                        req), 0)
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
            debug.write('Sending lightserver status', 0)
            client.send(json.dumps(dm()).encode('UTF-8'))
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
                    StateRequestObject(
                        auto_mode=True, hexvalues=self.config["TCP-PRESETS"][data[3:]]).run(self.lm)
                else:
                    StateRequestObject(
                        hexvalues=self.config["TCP-PRESETS"][data[3:]]).run(self.lm)
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
        for _dev in dm:
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
        dm.threaded = args.threaded

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
            req), 0, "CLIENT")
        s.sendall("2048".encode('utf-8'))
        s.sendall(pickle.dumps(req))
        s.close()

    quit()

#!/usr/bin/env python3
'''
    File name: home.py
    Author: Maxime Bergeron
    Date last modified: 18/11/2019
    Python Version: 3.5

    A python home control server/client
'''
import argparse
import configparser
import datetime
import json
import pickle
import socket
import sys
import threading
import time
import traceback
from core.common import *
from core.devicemanager import DeviceManager, StateRequestObject, RequestExecutor
from core.server import HomeServer
from argparse import RawTextHelpFormatter
from __main__ import *


""" Script executed directly """
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Home server manager script', formatter_class=RawTextHelpFormatter)
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
        dm = DeviceManager()

        dm.get_modules_list()

        if HOMECONFIG['SERVER'].getboolean('ENABLE_WIFI_RTT'):
            from dnn.dnn import run_tensorflow
        if args.notime:
            dm.set_serverwide_skiptime()
        dm.threaded = args.threaded

        hs = HomeServer(dm)
        hs.start()
        RequestExecutor().run(dm)
        hs.stop()

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
        req = StateRequestObject()
        req.parse_args(args)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOMECONFIG['SERVER']['HOST'], int(
            HOMECONFIG['SERVER'].getint('PORT'))))
        # TODO report connection errors or allow feedback response
        debug.write('Connecting with homeserver daemon', 0)
        debug.write('Sending request: {}'.format(
            req), 0, "CLIENT")
        s.sendall("4096".encode('utf-8'))
        s.sendall(pickle.dumps(req))
        s.close()

    quit()

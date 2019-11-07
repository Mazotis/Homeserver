#!/usr/bin/env python3
'''
    File name: homeclient.py
    Author: Maxime Bergeron
    Date last modified: 23/09/2019
    Python Version: 3.5

    The stripped-down version of home.py.
'''
import argparse
import sys
import socket
import pickle
import os
import configparser
from argparse import RawTextHelpFormatter
from core.common import *
from core.devicemanager import StateRequestObject
from __main__ import *

if __name__ == "__main__":
    # TODO make this script portable ?
    debug.enable_debug()
    HOMECONFIG = configparser.ConfigParser()
    HOMECONFIG.readfp(open(os.path.dirname(
        os.path.realpath(__file__)) + '/home.ini'))
    req = StateRequestObject()

    parser = argparse.ArgumentParser(description='Home server client script',
                                     formatter_class=RawTextHelpFormatter)
    parser.add_argument('hexvalues', metavar='N', type=str, nargs="*", default=None,
                        help='state values for the devuces (see list below)')
    for _dev in getDevices(True):
        parser.add_argument('--' + _dev, type=str, nargs="*",
                            help='Change {} states only'.format(_dev))
    parser.add_argument('--preset', metavar='preset', type=str, nargs="?", default=None,
                        help='Apply state change actions from specified preset name defined in home.ini')
    parser.add_argument('--group', metavar='group', type=str, nargs="+", default=None,
                        help='Apply state change actions on specified device group(s)')
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
    parser.add_argument('--stream-dev', metavar='str-dev', type=int, nargs="?", default=None,
                        help='Stream states directly to device id')
    parser.add_argument('--stream-group', metavar='str-grp', type=str, nargs="?", default=None,
                        help='Stream states directly to device group')
    parser.add_argument('--reset-mode', action='store_true', default=False,
                        help='Force state change (whatever the actual mode) and set back devices to AUTO mode')
    parser.add_argument('--reset-location-data', action='store_true', default=False,
                        help='Purge all RTT, locations and location training data (default: false)')
    parser.add_argument('--auto-mode', action='store_true', default=False,
                        help='(internal) Run requests for non-DEVICE_SKIP devices as AUTO mode (default: false)')
    parser.add_argument('--set-mode-for-devid', metavar='devid', type=int, nargs="?", default=None,
                        help='(internal) Force device# to change mode (as set by auto-mode)')

    args = parser.parse_args()

    if args.stream_dev and args.stream_group:
        debug.write(
            "You cannot stream data to both devices and groups. Quitting.", 2, "CLIENT")
        sys.exit()

    if args.reset_mode and args.auto_mode:
        debug.write(
            "You should not set the mode to AUTO then reset it back to AUTO. Quitting.", 2, "CLIENT")
        sys.exit()

    elif args.stream_dev or args.stream_group:
        colorval = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOMECONFIG['SERVER']['HOST'],
                   int(HOMECONFIG['SERVER']['PORT'])))
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
                colorval = input("Set device {} to colorvalue ('quit' to exit): "
                                 .format(args.stream_dev))
            else:
                colorval = input("Set group '{}' to colorvalue ('quit' to exit): "
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
                        HOMECONFIG['SERVER']['PORT'])))
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
        s.connect((HOMECONFIG['SERVER']['HOST'],
                   int(HOMECONFIG['SERVER']['PORT'])))
        # todo report connection errors or allow feedback response
        debug.write('Connecting with homeserver daemon', 0, "CLIENT")
        debug.write('Sending request: {}'.format(
            req), 0, "CLIENT")
        s.sendall("2048".encode('utf-8'))
        s.sendall(pickle.dumps(req))
        s.close()

    sys.exit()

#!/usr/bin/env python3
'''
    File name: home.py
    Author: Maxime Bergeron
    Date last modified: 18/11/2019
    Python Version: 3.5

    A python home control server/client
'''
import pickle
import socket
import sys
import time
from core.common import *
from core.devicemanager import DeviceManager, StateRequestObject, RequestExecutor
from core.server import HomeServer
from __main__ import *


""" Script executed directly """
if __name__ == "__main__":
    args = HOMECONFIG.get_arguments()

    # TODO add back device state change  request validation or just ignore?
    if args.server and (args.on or args.off or args.toggle or args.stream_dev
                        or args.stream_group or args.preset or args.restart):
        debug.write(
            "You cannot start the daemon and send arguments at the same time. Quitting.", 2)
        sys.exit()

    if args.stream_dev and args.stream_group:
        debug.write(
            "You cannot stream data to both devices and groups. Quitting.", 2)
        sys.exit()

    if args.reset_mode and args.auto_mode:
        debug.write(
            "You should not set the mode to AUTO then reset it back to AUTO. Quitting.", 2)
        sys.exit()

    if args.configure:
        debug.config.configure_prompt()
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
        req = StateRequestObject(client=True)
        req.parse_args(args)
        _tries = 0
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(20)
        debug.write('Sending request: {}'.format(req), 0, "CLIENT")
        while True:
            try:
                debug.write('Connecting with homeserver daemon', 0, "CLIENT")
                s.connect((HOMECONFIG['SERVER']['HOST'], int(
                    HOMECONFIG['SERVER'].getint('PORT'))))
                break
            except (ConnectionRefusedError, ConnectionAbortedError):
                debug.write('Connection to homeserver failed. Retrying', 1, "CLIENT")
                time.sleep(2)
                _tries = _tries + 1
                if _tries == 5:
                    debug.write('Cannot connect to homeserver. Check that it is running and properly configured.', 2, "CLIENT")
                    quit()
        s.sendall("4096".encode('utf-8'))
        s.sendall(pickle.dumps(req))
        if not args.nowait:
            debug.write('Connected, waiting for results...', 0, "CLIENT")
            time.sleep(2)
            s.sendall("1".encode("UTF-8"))
            data = pickle.loads(s.recv(1024))
            if data != "":
                debug.write("States changed to: {}".format(data),0, "CLIENT")
            else:
                debug.write("Command failure or timeout", 1, "CLIENT")
        else:
            time.sleep(2)
            s.sendall("0".encode("UTF-8"))
        s.close()

    quit()

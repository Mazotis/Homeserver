#!/usr/bin/env python3
'''
    File name: home.py
    Author: Maxime Bergeron
    Date last modified: 19/06/2020
    Python Version: 3.5

    A python home control server/client
'''
import json
import os
import pprint
import socket
import sys
import time
from core.common import *
from core.devicemanager import DeviceManager, StateRequestObject, RequestExecutor
from core.server import HomeServer
from __main__ import *
#from hanging_threads import start_monitoring
#monitoring_thread = start_monitoring()


""" Script executed directly """
if __name__ == "__main__":
    args = HOMECONFIG.get_arguments()

    # TODO add back device state change  request validation or just ignore?
    if args.server and (args.on or args.off or args.toggle or args.stream_dev
                        or args.stream_group or args.preset or args.restart):
        print("You cannot start the daemon and send arguments at the same time. Quitting.")
        sys.exit()

    if args.stream_dev and args.stream_group:
        print("You cannot stream data to both devices and groups. Quitting.")
        sys.exit()

    if args.reset_mode and args.auto_mode:
        print("You should not set the mode to AUTO then reset it back to AUTO. Quitting.")
        sys.exit()

    if args.configure:
        debug.config.configure_prompt()
        sys.exit()

    if args.update:
        from modules.updater import check_for_updates, run_upgrade
        if check_for_updates(with_pip=HOMECONFIG['UPDATER'].getboolean('UPDATE_PYTHON_PACKAGES')):
            run_upgrade(None)

    if args.status:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOMECONFIG['SERVER']['HOST'], int(
                HOMECONFIG['SERVER'].getint('PORT'))))
            send_msg(s, "getstate".encode('utf-8'))
            status_data = recv_msg(s)
            if json.dumps(status_data) == "null":
                print("Failed to fetch server status")
                s.close()
                sys.exit()
            pprint.pprint(json.loads(status_data))
        except socket.timeout:
            print("Server failed to answer request. Quitting.")
        except ConnectionRefusedError:
            print("Server is unavailable. Quitting.")
        except Exception as ex:
            print("Unhandled exception: {}".format(ex))
        finally:
            s.close()
            sys.exit()

    if args.server:
        if os.name == "nt":
            debug.write("The Homeserver cannot run on Windows. Quitting.", 2)
            quit()
        dm = DeviceManager(threaded=args.threaded)
        dm.get_modules_list()

        if HOMECONFIG['SERVER'].getboolean('ENABLE_WIFI_RTT'):
            from dnn.dnn import run_tensorflow
        if args.notime:
            if dm.has_module("timesched"):
                dm.get_module("timesched").set_serverwide_skiptime()

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
        # TODO Extensive testing - this might not work anymore
        colorval = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOMECONFIG['SERVER']['HOST'], int(
            HOMECONFIG['SERVER'].getint('PORT'))))
        if args.stream_dev:
            send_msg(s, "stream".encode('utf-8'))
            send_msg(s, ('%04d' % args.stream_dev).encode('utf-8'))
            send_msg(s, str(args.stream_dev).encode('utf-8'))
        else:
            send_msg(s, "streamgroup".encode('utf-8'))
            send_msg(s, ('%04d' % len(args.stream_group)).encode('utf-8'))
            send_msg(s, args.stream_group.encode('utf-8'))
        while colorval != "quit":
            if args.stream_dev:
                colorval = input("Set device {} to state value ('quit' to exit): "
                                 .format(args.stream_dev))
            else:
                colorval = input("Set group '{}' to state value ('quit' to exit): "
                                 .format(args.stream_group))
            try:
                if colorval == "quit":
                    send_msg(s, "nostream".encode('utf-8'))
                    break
                send_msg(s, ('%04d' % len(colorval)).encode('utf-8'))
                send_msg(s, colorval.encode('utf-8'))
            except BrokenPipeError:
                if colorval != "quit":
                    s.close()
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((HOMECONFIG['SERVER']['HOST'], int(
                        HOMECONFIG['SERVER'].getint('PORT'))))
                    if args.stream_dev:
                        send_msg(s, "stream".encode('utf-8'))
                        send_msg(s, ('%04d' % args.stream_dev).encode('utf-8'))
                        send_msg(s, str(args.stream_dev).encode('utf-8'))
                    else:
                        send_msg(s, "streamgroup".encode('utf-8'))
                        send_msg(
                            s, ('%04d' % len(args.stream_group)).encode('utf-8'))
                        send_msg(s, args.stream_group.encode('utf-8'))
                    send_msg(s, ('%04d' % len(colorval)).encode('utf-8'))
                    send_msg(s, colorval.encode('utf-8'))
                    continue
        s.close()

    else:
        req = StateRequestObject(client=True)
        req.parse_args(args)
        req.set(history_origin="CLI")
        _tries = 0
        if req.has_requested_changes():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(20)
            debug.write('Sending request: {}'.format(req), 0, "CLIENT")
            while True:
                try:
                    debug.write(
                        'Connecting with homeserver daemon', 0, "CLIENT")
                    s.connect((HOMECONFIG['SERVER']['HOST'], int(
                        HOMECONFIG['SERVER'].getint('PORT'))))
                    break
                except (ConnectionRefusedError, ConnectionAbortedError):
                    debug.write(
                        'Connection to homeserver failed. Retrying', 1, "CLIENT")
                    time.sleep(2)
                    _tries = _tries + 1
                    if _tries == 5:
                        debug.write(
                            'Cannot connect to homeserver. Check that it is running and properly configured.', 2, "CLIENT")
                        quit()
            send_msg(s, req)
            if not args.nowait:
                debug.write('Connected, waiting for results...', 0, "CLIENT")
                time.sleep(2)
                s.sendall("1".encode("UTF-8"))
                data = recv_msg(s)
                if data != "":
                    debug.write("States changed to: {}".format(
                        data), 0, "CLIENT")
                else:
                    debug.write("Command failure or timeout", 1, "CLIENT")
            else:
                time.sleep(2)
                s.sendall("0".encode("UTF-8"))
            s.close()
        else:
            debug.write("Nothing requested of the homeserver", 0)

    quit()

#!/usr/bin/env python3
'''
    File name: server.py
    Author: Maxime Bergeron
    Date last modified: 20/05/2020
    Python Version: 3.7

    The homeserver request server
'''
import json
import socket
import sys
import time
import traceback
from core.common import *
from core.devicemanager import StateRequestObject, ExecutionState
from threading import Thread, Event


class HomeServer(Thread):
    """ Handles server-side request reception and handling """
    closing = False

    def __init__(self, dm):
        Thread.__init__(self)
        self.dm = dm
        self.base_config = getConfigHandler()
        self.config = self.base_config.set_section("SERVER")
        self.host = self.config['HOST']
        self.port = self.config.get_value('PORT', int)
        self.conn_sockets = []
        self.stopevent = Event()
        if not HomeServer.closing:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind((self.host, self.port))
            except OSError:
                print(
                    "Server address/port ({}:{}) already in use or closed. Quitting.".format(self.host, self.port))
                HomeServer.closing = True
                self.stop()
                sys.exit()
            self.tcp_start_hour = self.config.get_value(
                'TCP_START_HOUR', "hours")
            self.tcp_end_hour = self.config.get_value('TCP_END_HOUR', "hours")

    def run(self):
        """ Starts the server """
        debug.write('Server started', 0, "SERVER")
        # Cleanup connection to allow new sock.accepts faster as sched is blocking
        self.dm.disconnect_devices()
        self.sock.listen(5)
        while not self.stopevent.is_set():
            client, address = self.sock.accept()
            if self.stopevent.is_set():
                break
            debug.write("Connected with {}:{}".format(
                address[0], address[1]), 0, "SERVER")
            client.settimeout(10)
            self.conn_sockets.append(Thread(
                target=self.listen_client, args=(client, address)).start())
        debug.write("Stopped", 0, "SERVER")

    def listen_client(self, client, address):
        """ Listens for new requests and handle them properly """
        try:
            while True:
                data = recv_msg(client)
                if data:
                    if not isinstance(data, StateRequestObject):
                        req = StateRequestObject()
                        req.initialize_dm(self.dm)
                        self.check_for_function_request(
                            data.decode("utf-8"), req, client)
                        break
                    try:
                        data.initialize_dm(self.dm)
                    except Exception:
                        debug.write(
                            "Error - improperly formatted StateRequestObject. Got: {}".format(data.decode('utf-8')), 2, "SERVER")
                        break
                    debug.write('Change of states requested with request: {}'.format(
                        data), 0, "SERVER")
                    data()
                    break

        except socket.timeout:
            debug.write("Timeout error", 1)
            pass

        except ValueError as ex:
            debug.write("Got incorrect value or timing error. Traceback: {}".format(traceback.format_tb(
                ex.__traceback__)), 2, "SERVER")

        except Exception as ex:
            debug.write('Unhandled exception of type {}: {}, {}'
                        .format(type(ex), ex,
                                ''.join(traceback.format_tb(
                                    ex.__traceback__))
                                ), 2, "SERVER")

        finally:
            try:
                data = client.recv(1)
                if (data.decode("UTF-8") == "1"):
                    while ExecutionState.get():
                        time.sleep(0.5)
                    send_msg(client, self.dm.get_state(is_async=True))
            except Exception as ex:
                debug.write("Got exception: {}".format(ex), 1)
            debug.write('Closing connection.', 0, "SERVER")
            client.close()

    def check_for_function_request(self, data, req, client):
        streamingdev = False
        streaminggrp = False
        streaming_id = None

        if data == "getstate":
            debug.write('Sending lightserver status', 0, "SERVER")
            send_msg(client, json.dumps(self.dm()))
            return True

        if data == "getconfig":
            debug.write("Sending config file to client", 0, "SERVER")
            send_msg(client, self.base_config)
            return True

        if data == "stream":
            debug.write('Starting streaming mode', 0, "SERVER")
            streamingdev = True

        if data == "streamgroup":
            debug.write('Starting group streaming mode', 0, "SERVER")
            streaminggrp = True

        if data == "nostream":
            debug.write('Ending streaming mode', 0, "SERVER")
            streamingdev = False
            streaminggrp = False
            streaming_id = None
            return True

        if data[:3] == "tcp":
            debug.write('Getting TCP request: {}'.format(
                data), 0, "SERVER")
            if self.tcp_start_hour > datetime.datetime.now().time() or \
               self.tcp_end_hour < datetime.datetime.now().time():
                debug.write('TCP requests disabled until {}'.format(
                    self.tcp_start_hour), 0, "SERVER")
                return True
            if data[3:] in self.config.get_value(None, parent="TCP-PRESETS"):
                debug.write("Running TCP preset {}".format(
                    data[3:]), 0, "SERVER")
                req = StateRequestObject()
                req.initialize_dm(self.dm)
                req.set(history_origin="Server (TCP)")
                if self.config.get_value("AUTOMATIC_MODE", bool, parent="TCP-PRESETS"):
                    req.set(auto_mode=True)
                if req.from_string(self.config.get_value(data[3:], str, parent="TCP-PRESETS")):
                    req.run()
            else:
                debug.write("TCP preset {} is not configured".format(
                    data[3:]), 1, "SERVER")
            return True

        if data == "sendloc":
            locationData = json.loads(
                client.recv(1024).decode("UTF-8"))
            debug.write('Recording a training location for room: {}'.format(
                locationData["room"]), 0, "SERVER")
            with open(self.config['JOURNAL_DIR'] + "/dnn/train.log", "a") as jfile:
                jfile.write("{},{},{},{},{},{},{}\n".format(locationData["room"], locationData["r1_mean"],
                                                            locationData["r1_rssi"], locationData["r2_mean"], locationData["r2_rssi"], locationData["r3_mean"], locationData["r3_rssi"]))
            return True

        if data == "getloc":
            ld = json.loads(client.recv(1024).decode("UTF-8"))
            debug.write(
                '[WIFI-RTT] Evaluating location from:', 0, "SERVER")
            tf_str = '{},{},{},{},{},{}'.format(
                ld["r1_mean"], ld["r1_rssi"], ld["r2_mean"], ld["r2_rssi"], ld["r3_mean"], ld["r3_rssi"])
            debug.write('[WIFI-RTT] {}'.format(tf_str), 0, "SERVER")
            res = run_tensorflow(
                TfPredict=True, PredictList=tf_str)
            debug.write(
                "[WIFI-RTT] Device found to be in room: {}".format(res), 0, "SERVER")
            client.send(res.encode("UTF-8"))
            return True

        if streamingdev:
            if streaming_id is None:
                streaming_id = int(data)
                debug.write('Set streaming devid to {}'
                            .format(streaming_id), 0, "SERVER")
            else:
                debug.write("Sending request to devid {} for color: {}"
                            .format(streaming_id, data), 0, "SERVER")
                self.dm.set_light_stream(
                    streaming_id, data, False)

        if streaminggrp:
            if streaming_id is None:
                streaming_id = data
                debug.write('Set streaming group to {}'
                            .format(streaming_id), 0)
            else:
                debug.write("Sending request to group '{}' for color: {}"
                            .format(streaming_id, data), 0, "SERVER")
                self.dm.set_light_stream(
                    streaming_id, data, True)
        return False

    def stop(self):
        """ Shuts down server and cleans resources """
        debug.write("Closing down server and lights.", 0, "SERVER")
        self.dm.stop_delayed_changes()
        debug.write("Closing remaining connections", 0, "SERVER")
        for _thr in self.conn_sockets:
            if _thr is not None:
                _thr.join()
        if self.dm.scheduled_disconnect is not None:
            debug.write("Purging scheduled light changes", 0, "SERVER")
            self.dm.scheduled_disconnect.cancel()
        debug.write("Disconnecting devices", 0, "SERVER")
        self.dm.disconnect_devices()
        debug.write("Shutdown completed properly", 0, "SERVER")
        self.stopevent.set()
        socket.socket(socket.AF_INET,
                      socket.SOCK_STREAM).connect((self.host, self.port))
        self.sock.close()
        return

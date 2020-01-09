#!/usr/bin/env python3
'''
    File name: server.py
    Author: Maxime Bergeron
    Date last modified: 18/11/2019
    Python Version: 3.5

    The homeserver request server
'''
import pickle
import socket
import traceback
from core.common import *
from threading import Thread, Timer, Event


class HomeServer(Thread):
    """ Handles server-side request reception and handling """

    def __init__(self, dm):
        Thread.__init__(self)
        self.dm = dm
        self.config = getConfigHandler().set_section("SERVER")
        self.host = self.config['HOST']
        self.port = self.config.get_value('PORT', int)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.tcp_start_hour = self.config.get_value('TCP_START_HOUR', "hours")
        self.tcp_end_hour = self.config.get_value('TCP_END_HOUR', "hours")
        self.conn_sockets = []
        self.stopevent = Event()

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
                msize = int(client.recv(4).decode('utf-8'))
                data = client.recv(msize)
                if data:
                    # TODO use the recv length to determine pickled vs non-pickled requests ?
                    if msize != 4096:
                        req = StateRequestObject()
                        if self.check_for_function_request(data.decode('utf-8'), req, client):
                            break
                    try:
                        req = pickle.loads(data)
                    except:
                        debug.write(
                            "Error - improperly formatted pickle. Got: {}".format(data.decode('utf-8')), 2, "SERVER")
                        break
                    debug.write('Change of lights requested with request: {}'.format(
                        req), 0, "SERVER")
                    req()
                    break

        except socket.timeout:
            pass

        except Exception as ex:
            debug.write('Unhandled exception of type {}: {}, {}'
                        .format(type(ex), ex,
                                ''.join(traceback.format_tb(
                                    ex.__traceback__))
                                ), 2, "SERVER")

        finally:
            debug.write('Closing connection.', 0, "SERVER")
            self.dm.reinit()
            client.close()

    def check_for_function_request(self, data, req, client):
        streamingdev = False
        streaminggrp = False
        streaming_id = None

        if data == "getstate":
            debug.write('Sending lightserver status', 0, "SERVER")
            client.send(json.dumps(self.dm()).encode('UTF-8'))
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

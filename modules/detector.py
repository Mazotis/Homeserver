#!/usr/bin/env python3
'''
    File name: detector.py
    Author: Maxime Bergeron
    Date last modified: 15/11/2019
    Python Version: 3.5

    The device-pinging detector module for the homeserver
'''

import datetime
import os
from core.common import *
from core.devicemanager import StateRequestObject
from threading import Thread, Event


class detector(Thread):
    def __init__(self, config, dm):
        Thread.__init__(self)
        self.config = config
        self.detector_config = self.config['DETECTOR']
        self.stopevent = Event()
        self.TRACKED_IPS = self.detector_config['TRACKED_IPS'].split(",")
        self.device_state_level = [
            0] * len(self.detector_config['TRACKED_IPS'].split(","))
        self.DEVICE_STATE_MAX = self.detector_config.getint(
            'MAX_STATE_LEVEL')
        self.device_status = [
            0] * len(self.TRACKED_IPS)
        self.DETECTOR_START_HOUR = datetime.datetime.strptime(
            self.detector_config['START_HOUR'], '%H:%M').time()
        self.DETECTOR_END_HOUR = datetime.datetime.strptime(
            self.detector_config['END_HOUR'], '%H:%M').time()
        # This represents an active state (a device is connected) + event time is reached
        self.status = True
        self.delayed_start = False
        self.dm = dm
        if config.has_option("DETECTOR", "TRACKED_PICTURES"):
            if len(self.detector_config["TRACKED_PICTURES"].split(',')) == len(self.detector_config["TRACKED_IPS"].split(',')):
                self.web = "detector.html"
            else:
                debug.write(
                    "You must provide enough TRACKED_PICTURES to match the TRACKED_IPS.", 1, "DETECTOR")

    def run(self):
        _is_running = False
        self.first_detect()
        while not self.stopevent.is_set():
            if self.DETECTOR_START_HOUR > datetime.datetime.now().time() or \
                    self.DETECTOR_END_HOUR < datetime.datetime.now().time():
                _is_running = False
                self.stopevent.wait(30)
                continue
            if not _is_running and self.detector_config.getboolean('FALLBACK_AUTO_ON_NEW_DAY'):
                debug.write(
                    "Setting back all devices to AUTO mode for new day", 0, "DETECTOR")
                req = StateRequestObject(force_auto_mode=True,
                                         notime=True)
                req(self.dm)
                _is_running = True
            self.detect_devices()
            self.stopevent.wait(int(self.detector_config['PING_FREQ_SEC']))
        debug.write("Stopped.", 0, "DETECTOR")
        return

    def stop(self):
        debug.write("Stopping.", 0, "DETECTOR")
        self.stopevent.set()

    def first_detect(self):
        debug.write("Starting ping-based device detector", 0, "DETECTOR")
        for _cnt, device in enumerate(self.TRACKED_IPS):
            if device != "_" and int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
                self.device_state_level[_cnt] = self.DEVICE_STATE_MAX
                self.device_status[_cnt] = 1
            else:
                self.device_state_level[_cnt] = 0
                self.device_status[_cnt] = 0
        debug.write("Got initial states {} and status {}".format(
            self.device_state_level, self.status), 0, "DETECTOR")

        if self.DETECTOR_START_HOUR > datetime.datetime.now().time() or \
           self.DETECTOR_END_HOUR < datetime.datetime.now().time():
            debug.write("Standby. Running between {} and {}".format(self.DETECTOR_START_HOUR,
                                                                    self.DETECTOR_END_HOUR), 0, "DETECTOR")

    def detect_devices(self):
        EVENT_TIME = self.dm.update_event_time()
        ACTUAL_TIME = datetime.datetime.now().time()

        if self.status and all(s == 0 for s in self.device_state_level):
            debug.write(
                "All devices are disconnected, running ON_DISCONNECT.", 0, "DETECTOR")
            req = StateRequestObject()
            if self.detector_config.getboolean('FALLBACK_AUTO_ON_DISCONNECT'):
                self.run_state_request(
                    "ON_ALL_DISCONNECT_EVENT", reset_mode=True)
            else:
                self.run_state_request("ON_ALL_DISCONNECT_EVENT")
            self.status = False
            self.delayed_start = False

        if ACTUAL_TIME == EVENT_TIME and self.delayed_start:
            debug.write(
                "Event time reached and devices are connected.", 0, "DETECTOR")
            self.run_state_request("ON_EVENT_HOUR_EVENT")
            self.delayed_start = False
            self.status = True

        if self.DEVICE_STATE_MAX in self.device_state_level and not self.delayed_start:
            if datetime.datetime.now().time() < EVENT_TIME:
                debug.write("Scheduling ON_EVENT_HOUR state change at {}".format(
                    EVENT_TIME), 0, "DETECTOR")
                self.delayed_start = True
                self.status = False

        if self.DEVICE_STATE_MAX in self.device_state_level and not self.status and ACTUAL_TIME >= EVENT_TIME:
            debug.write(
                "Devices connected between event time and detector off-time.", 0, "DETECTOR")
            self.run_state_request("ON_EVENT_HOUR_EVENT")
            self.status = True
            self.delayed_start = False

        if all(s == 0 for s in self.device_state_level) and not self.status and self.delayed_start:
            debug.write(
                "Devices disconnected. Aborting scheduled event.", 0, "DETECTOR")
            self.delayed_start = False

        for _cnt, device in enumerate(self.TRACKED_IPS):
            if device == "_":
                continue

            if int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
                if self.device_status[_cnt] == 0:
                    debug.write("Device {} CONnected".format(
                        device), 0, "DETECTOR")
                    self.device_status[_cnt] = 1
                    self.device_state_level[_cnt] = self.DEVICE_STATE_MAX
                    if ACTUAL_TIME >= EVENT_TIME:
                        self.run_state_request(
                            "ON_EVENT_HOUR_DEVICE_CONNECT_EVENT")
                    else:
                        self.run_state_request("ON_DEVICE_CONNECT_EVENT")
            else:
                if self.device_state_level[_cnt] == 0 and self.device_status[_cnt] == 1:
                    debug.write("DEVICE {} DISconnected".format(
                        device), 0, "DETECTOR")
                    self.device_status[_cnt] = 0
                    if ACTUAL_TIME >= EVENT_TIME:
                        self.run_state_request(
                            "ON_EVENT_HOUR_DEVICE_DISCONNECT_EVENT")
                    else:
                        self.run_state_request("ON_DEVICE_DISCONNECT_EVENT")
                elif self.device_state_level[_cnt] != 0:
                    self.device_state_level[_cnt] -= 1

    def run_state_request(self, request, reset_mode=False):
        if self.config.has_option("DETECTOR", request) and self.detector_config[request] not in [None, ""]:
            debug.write("Running event: {}".format(request), 0, "DETECTOR")
            req = StateRequestObject()
            if reset_mode:
                req.set(reset_mode=True)
            else:
                req.set(auto_mode=True)
            if req.from_string(self.detector_config[request]):
                req(self.dm)

    def get_web(self):
        web = ""
        pictures = self.detector_config["TRACKED_PICTURES"].split(',')
        for _cnt, pic in enumerate(pictures):
            if _cnt == 5:
                debug.write(
                    "Max amount of pictures for detector web module is 5. Hiding the rest.", 1, "DETECTOR")
                break
            if self.device_state_level[_cnt] != self.DEVICE_STATE_MAX and self.TRACKED_IPS[_cnt] != "_":
                web += '<img src={} class="mx-auto d-block border-danger" style="width:85px; height:85px; border-radius:50%; margin-right:3px !important; border:5px solid; -webkit-filter: grayscale(100%); filter: grayscale(100%);">'.format(
                    "/images/" + pic)
            else:
                web += '<img src={} class="mx-auto d-block border-success" style="width:85px; height:85px; border-radius:50%; margin-right:3px !important; border:5px solid;">'.format(
                    "/images/" + pic)
        return web

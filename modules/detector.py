#!/usr/bin/env python3
'''
    File name: detector.py
    Author: Maxime Bergeron
    Date last modified: 22/10/2019
    Python Version: 3.5

    The device-pinging detector module for the homeserver
'''

import datetime
import os
import requests
from core.common import *
from core.devicemanager import StateRequestObject
from threading import Thread, Event


class detector(Thread):
    def __init__(self, config, dm):
        Thread.__init__(self)
        self.detector_config = config['DETECTOR']
        self.find3_config = config['FIND3-PRESETS']
        self.stopevent = Event()
        self.TRACKED_IPS = self.detector_config['TRACKED_IPS'].split(",")
        self.device_state_level = [
            0] * len(self.detector_config['TRACKED_IPS'].split(","))
        self.DEVICE_STATE_MAX = self.detector_config.getint(
            'MAX_STATE_LEVEL')
        self.device_status = [
            0] * len(self.TRACKED_IPS)
        self.FIND3_SERVER = self.detector_config.getboolean(
            'FIND3_SERVER_ENABLE')
        self.DETECTOR_START_HOUR = datetime.datetime.strptime(
            self.detector_config['START_HOUR'], '%H:%M').time()
        self.DETECTOR_END_HOUR = datetime.datetime.strptime(
            self.detector_config['END_HOUR'], '%H:%M').time()
        self.status = 0
        self.delayed_start = 0
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

        if self.FIND3_SERVER:
            debug.write("Starting FIND3 localization server", 0, "DETECTOR")
            self.tracked_find3_devs = self.detector_config['FIND3_TRACKED_DEVICES'].split(
                ",")
            self.tracked_find3_times = [0] * len(self.tracked_find3_devs)
            self.tracked_find3_local = [""] * len(self.tracked_find3_devs)
            for _cnt, _dev in enumerate(self.tracked_find3_devs):
                # Get last update times
                if _dev != "_":
                    try:
                        _r = requests.get("http://{}/api/v1/location/{}/{}".format(self.detector_config['FIND3_SERVER_URL'],
                                                                                   self.detector_config['FIND3_FAMILY_NAME'],
                                                                                   _dev))
                    except requests.exceptions.ConnectionError:
                        debug.write(
                            "Cannot connect to FIND3 server using provided config. Disabling", 1, "DETECTOR")
                        self.FIND3_SERVER = False
                        break

                    self.tracked_find3_times[_cnt] = _r.json()['sensors']['t']

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
        for _cnt, device in enumerate(self.TRACKED_IPS):
            # TODO Maintain the two pings requirement for status change ?
            if device != "_" and int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
                if self.device_state_level[_cnt] == self.DEVICE_STATE_MAX and self.device_status[_cnt] == 0:
                    debug.write("Device {} CONnected".format(
                        device), 0, "DETECTOR")
                    self.device_status[_cnt] = 1
                elif self.device_state_level[_cnt] != self.DEVICE_STATE_MAX:
                    self.device_state_level[_cnt] = self.device_state_level[_cnt] + 1
                if self.FIND3_SERVER and self.tracked_find3_devs[_cnt] != "_":
                    self.tracked_find3_local = [
                        ""] * len(self.tracked_find3_devs)
                    _r = requests.get("http://{}/api/v1/location/{}/{}".format(self.detector_config['FIND3_SERVER_URL'],
                                                                               self.detector_config['FIND3_FAMILY_NAME'],
                                                                               self.tracked_find3_devs[_cnt]))
                    if self.tracked_find3_times[_cnt] != _r.json()['sensors']['t'] and \
                       self.tracked_find3_local[_cnt] != _r.json()['analysis']['guesses'][0]['location']:
                        if _r.json()['analysis']['guesses'][0]['location'] in self.find3_config:
                            if self.find3_config.getboolean('AUTOMATIC_MODE'):
                                req = StateRequestObject(auto_mode=True, hexvalues=self.find3_config[_r.json()[
                                    'analysis']['guesses'][0]['location']])
                            else:
                                req = StateRequestObject(hexvalues=self.find3_config[_r.json()[
                                    'analysis']['guesses'][0]['location']])
                            req(self.dm)
                            debug.write("Device {} found in '{}'. Running change of lights."
                                        .format(self.tracked_find3_devs[_cnt],
                                                _r.json()['analysis']['guesses'][0]['location']), 0, "DETECTOR")

                        else:
                            debug.write("Device {} found in '{}' but preset is not self.configured."
                                        .format(self.tracked_find3_devs[_cnt],
                                                _r.json()['analysis']['guesses'][0]['location']), 0, "DETECTOR")
                        if self.tracked_find3_local[_cnt] + "-off" in self.find3_config:
                            if self.find3_config.getboolean('AUTOMATIC_MODE'):
                                req = StateRequestObject(
                                    auto_mode=True, hexvalues=self.find3_config[self.tracked_find3_local][_cnt] + "-off")
                            else:
                                req = StateRequestObject(
                                    hexvalues=self.find3_config[self.tracked_find3_local][_cnt] + "-off")
                            req(self.dm)
                            debug.write("Device {} left '{}'. Running change of lights."
                                        .format(self.tracked_find3_devs[_cnt],
                                                self.tracked_find3_local[_cnt]), 0, "DETECTOR")
                        self.tracked_find3_times[_cnt] = _r.json()[
                            'sensors']['t']
                        self.tracked_find3_local[_cnt] = _r.json(
                        )['analysis']['guesses'][0]['location']
            elif device != "_":
                if self.device_state_level[_cnt] == 0 and self.device_status[_cnt] == 1:
                    debug.write("DEVICE {} DISconnected".format(
                        device), 0, "DETECTOR")
                    self.device_status[_cnt] = 0
                elif self.device_state_level[_cnt] != 0:
                    # Decrease state level down to zero (OFF)
                    self.device_state_level[_cnt] = self.device_state_level[_cnt] - 1

        if self.status == 1 and all(s == 0 for s in self.device_state_level):
            debug.write("STATE changed to {} and DELAYED_START {}, turned off"
                        .format(self.device_state_level, self.delayed_start), 0, "DETECTOR")
            if self.detector_config.getboolean('FALLBACK_AUTO_ON_DISCONNECT'):
                req = StateRequestObject(reset_mode=True, off=True,
                                         notime=True)
            else:
                req = StateRequestObject(auto_mode=True, off=True,
                                         notime=True)
            req(self.dm)
            self.status = 0
            self.delayed_start = 0
        if datetime.datetime.now().time() == EVENT_TIME and self.delayed_start == 1:
            debug.write("DELAYED STATE with actual state {}, turned on".format(self.device_state_level),
                        0, "DETECTOR")
            req = StateRequestObject(
                auto_mode=True, on=True, group=self.detector_config['AUTO_ON_GROUP'])
            req(self.dm)
            self.delayed_start = 0
            self.status = 1
        if self.DEVICE_STATE_MAX in self.device_state_level and self.delayed_start == 0:
            if datetime.datetime.now().time() < EVENT_TIME:
                debug.write("Scheduling state change, with actual state {}"
                            .format(self.device_state_level), 0, "DETECTOR")
                self.delayed_start = 1
                self.status = 0
        if self.DEVICE_STATE_MAX in self.device_state_level and self.status == 0 and datetime.datetime.now().time() \
           >= EVENT_TIME:
            debug.write("STATE changed to {}, turned on".format(
                self.device_state_level), 0, "DETECTOR")
            req = StateRequestObject(
                auto_mode=True, on=True, group=self.detector_config['AUTO_ON_GROUP'])
            req(self.dm)
            self.status = 1
            self.delayed_start = 0
        if all(s == 0 for s in self.device_state_level) and self.status == 0 and self.delayed_start == 1:
            debug.write("Aborting light change, with actual state {}"
                        .format(self.device_state_level), 0, "DETECTOR")
            self.delayed_start = 0

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

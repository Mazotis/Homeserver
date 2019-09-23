#!/usr/bin/env python3
'''
    File name: detector.py
    Author: Maxime Bergeron
    Date last modified: 22/08/2019
    Python Version: 3.5

    The device-pinging detector module for the homeserver
'''

import datetime
import os
import requests
from devices.common import *
from threading import Thread, Event

class detector(Thread):
    def __init__ (self, config, lightmanager):
        Thread.__init__(self)
        self.config = config
        self.stopevent = Event()
        self.DEVICE_STATE_LEVEL = [0]*len(config['DETECTOR']['TRACKED_IPS'].split(","))
        self.DEVICE_STATE_MAX = self.config['DETECTOR'].getint('MAX_STATE_LEVEL')
        self.DEVICE_STATUS = [0]*len(self.config['DETECTOR']['TRACKED_IPS'].split(","))
        self.FIND3_SERVER= self.config['DETECTOR'].getboolean('FIND3_SERVER_ENABLE')
        self.DETECTOR_START_HOUR = datetime.datetime.strptime(self.config['DETECTOR']['START_HOUR'],'%H:%M').time()
        self.DETECTOR_END_HOUR = datetime.datetime.strptime(self.config['DETECTOR']['END_HOUR'],'%H:%M').time()
        self.status = 0
        self.delayed_start = 0
        self.lm = lightmanager

    def run(self):
        self.first_detect()
        while not self.stopevent.is_set():
            if self.DETECTOR_START_HOUR > datetime.datetime.now().time() or \
                self.DETECTOR_END_HOUR < datetime.datetime.now().time():
                self.stopevent.wait(30)
                continue 
            self.detect_devices()
            self.stopevent.wait(int(self.config['DETECTOR']['PING_FREQ_SEC']))
        debug.write("Stopped.", 0, "DETECTOR")
        return

    def stop(self):
        debug.write("Stopping.", 0, "DETECTOR")
        self.stopevent.set()

    def first_detect(self):
        debug.write("Starting ping-based device detector", 0, "DETECTOR")

        if self.FIND3_SERVER:
            debug.write("Starting FIND3 localization server", 0, "DETECTOR")
            TRACKED_FIND3_DEVS = self.config['DETECTOR']['FIND3_TRACKED_DEVICES'].split(",")
            TRACKED_FIND3_TIMES = [0]*len(TRACKED_FIND3_DEVS)
            TRACKED_FIND3_LOCAL = [""]*len(TRACKED_FIND3_DEVS)
            for _cnt, _dev in enumerate(TRACKED_FIND3_DEVS):
                # Get last update times
                if _dev != "_":
                    _r = requests.get("http://{}/api/v1/location/{}/{}".format(self.config['DETECTOR']['FIND3_SERVER_URL'],
                                                                               self.config['DETECTOR']['FIND3_FAMILY_NAME'],
                                                                               _dev))
                    TRACKED_FIND3_TIMES[_cnt] = _r.json()['sensors']['t']

        for _cnt, device in enumerate(self.config['DETECTOR']['TRACKED_IPS'].split(",")):
            if int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
                self.DEVICE_STATE_LEVEL[_cnt] = self.DEVICE_STATE_MAX
                self.DEVICE_STATUS[_cnt] = 1
            else:
                self.DEVICE_STATE_LEVEL[_cnt] = 0
                self.DEVICE_STATUS[_cnt] = 0
        debug.write("Got initial states {} and status {}".format(self.DEVICE_STATE_LEVEL, self.status), 0, "DETECTOR")

        if self.DETECTOR_START_HOUR > datetime.datetime.now().time() or \
           self.DETECTOR_END_HOUR < datetime.datetime.now().time():
               debug.write("Standby. Running between {} and {}".format(self.DETECTOR_START_HOUR, 
                                                                       self.DETECTOR_END_HOUR), 0, "DETECTOR")

    def detect_devices(self):
        EVENT_TIME = self.lm.get_event_time()
        for _cnt, device in enumerate(self.config['DETECTOR']['TRACKED_IPS'].split(",")):
            #TODO Maintain the two pings requirement for status change ?
            if int(os.system("ping -c 1 -W 1 {} >/dev/null".format(device))) == 0:
                if self.DEVICE_STATE_LEVEL[_cnt] == self.DEVICE_STATE_MAX and self.DEVICE_STATUS[_cnt] == 0:
                    debug.write("Device {} CONnected".format(device), 0, "DETECTOR")
                    self.DEVICE_STATUS[_cnt] = 1
                elif self.DEVICE_STATE_LEVEL[_cnt] != self.DEVICE_STATE_MAX:
                    self.DEVICE_STATE_LEVEL[_cnt] = self.DEVICE_STATE_LEVEL[_cnt] + 1
                if self.FIND3_SERVER and TRACKED_FIND3_DEVS[_cnt] != "_":
                    _r = requests.get("http://{}/api/v1/location/{}/{}".format(self.config['DETECTOR']['FIND3_SERVER_URL'],
                                                                               self.config['DETECTOR']['FIND3_FAMILY_NAME'],
                                                                               TRACKED_FIND3_DEVS[_cnt]))
                    if TRACKED_FIND3_TIMES[_cnt] != _r.json()['sensors']['t'] and \
                       TRACKED_FIND3_LOCAL[_cnt] != _r.json()['analysis']['guesses'][0]['location']:
                        if _r.json()['analysis']['guesses'][0]['location'] in self.config['FIND3-PRESETS']:
                            if self.config['FIND3-PRESETS'].getboolean('AUTOMATIC_MODE'):
                                os.system("./homeclient.py --auto-mode " + self.config['FIND3-PRESETS'][_r.json()['analysis']['guesses'][0]['location']])
                            else:
                                os.system("./homeclient.py " + self.config['FIND3-PRESETS'][_r.json()['analysis']['guesses'][0]['location']])
                            debug.write("Device {} found in '{}'. Running change of lights."
                                        .format(TRACKED_FIND3_DEVS[_cnt], 
                                                _r.json()['analysis']['guesses'][0]['location']), 0, "DETECTOR")

                        else:
                            debug.write("Device {} found in '{}' but preset is not self.configured."
                                        .format(TRACKED_FIND3_DEVS[_cnt], 
                                                _r.json()['analysis']['guesses'][0]['location']), 0, "DETECTOR")
                        if TRACKED_FIND3_LOCAL[_cnt]+"-off" in self.config['FIND3-PRESETS']:
                            if self.config['FIND3-PRESETS'].getboolean('AUTOMATIC_MODE'):
                                os.system("./homeclient.py --auto-mode " + self.config['FIND3-PRESETS'][TRACKED_FIND3_LOCAL[_cnt]+"-off"])
                            else:
                                os.system("./homeclient.py " + self.config['FIND3-PRESETS'][TRACKED_FIND3_LOCAL[_cnt]+"-off"])
                            debug.write("Device {} left '{}'. Running change of lights."
                                        .format(TRACKED_FIND3_DEVS[_cnt], 
                                                TRACKED_FIND3_LOCAL[_cnt]), 0, "DETECTOR")
                        TRACKED_FIND3_TIMES[_cnt] = _r.json()['sensors']['t']
                        TRACKED_FIND3_LOCAL[_cnt] = _r.json()['analysis']['guesses'][0]['location']
            else:
                if self.DEVICE_STATE_LEVEL[_cnt] == 0 and self.DEVICE_STATUS[_cnt] == 1:
                    debug.write("DEVICE {} DISconnected".format(device), 0, "DETECTOR")
                    self.DEVICE_STATUS[_cnt] = 0
                elif self.DEVICE_STATE_LEVEL[_cnt] != 0:
                    # Decrease state level down to zero (OFF)
                    self.DEVICE_STATE_LEVEL[_cnt] = self.DEVICE_STATE_LEVEL[_cnt] - 1

        if self.status == 1 and all(s == 0 for s in self.DEVICE_STATE_LEVEL):
            debug.write("STATE changed to {} and DELAYED_START {}, turned off" \
                                  .format(self.DEVICE_STATE_LEVEL, self.delayed_start), 0, "DETECTOR")
            if self.config['DETECTOR'].getboolean('FALLBACK_AUTO_ON_DISCONNECT'):
                os.system('./homeclient.py --reset-mode --off --notime --priority 3')
            else:
                os.system('./homeclient.py --auto-mode --off --notime --priority 3')
            self.status = 0
            self.delayed_start = 0
        if datetime.datetime.now().time() == EVENT_TIME and self.delayed_start == 1:
            debug.write("DELAYED STATE with actual state {}, turned on".format(self.DEVICE_STATE_LEVEL), 
                                                                               0, "DETECTOR")
            os.system('./homeclient.py --auto-mode --on --group passage')
            self.delayed_start = 0
            self.status = 1  
        if self.DEVICE_STATE_MAX in self.DEVICE_STATE_LEVEL and self.delayed_start == 0:
            if datetime.datetime.now().time() < EVENT_TIME:
                debug.write("Scheduling state change, with actual state {}" \
                                      .format(self.DEVICE_STATE_LEVEL), 0, "DETECTOR")
                self.delayed_start = 1
                self.status = 0
        if self.DEVICE_STATE_MAX in self.DEVICE_STATE_LEVEL and self.status == 0 and datetime.datetime.now().time() \
           >= EVENT_TIME:
            debug.write("STATE changed to {}, turned on".format(self.DEVICE_STATE_LEVEL), 0, "DETECTOR")
            os.system('./homeclient.py --auto-mode --on --group passage')
            self.status = 1
            self.delayed_start = 0
        if all(s == 0 for s in self.DEVICE_STATE_LEVEL) and self.status == 0 and self.delayed_start == 1:
            debug.write("Aborting light change, with actual state {}" \
                                      .format(self.DEVICE_STATE_LEVEL), 0, "DETECTOR")
            self.delayed_start = 0
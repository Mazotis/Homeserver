#!/usr/bin/env python3
'''
    File name: device.py
    Author: Maxime Bergeron
    Date last modified: 13/03/2019
    Python Version: 3.7

    Main wrapper object for all Homeserver devices. Not a device per-se.
'''

import time
import datetime
from devices.common import *
from modules.convert import convert_color

class device(object):
    def __init__(self, devid, config):
        self.devid = devid
        self.description = config["DEVICE"+str(devid)]["DESCRIPTION"]
        self.success = False
        self._connection = None
        self.group = []
        if config.has_option("DEVICE"+str(devid),"GROUP"):
            self.group = config["DEVICE"+str(devid)]["GROUP"].split(',')
        if config.has_option("DEVICE"+str(devid),"DEFAULT_INTENSITY"):
            self.intensity = config["DEVICE"+str(devid)]["DEFAULT_INTENSITY"]
        self.state = 0
        self.device_type = None
        self.request_auto_mode = True
        self.auto_mode = True
        self.reset_mode = False
        self.name = None
        self.color_type = None
        self.start_event_time = None
        if config.has_option("DEVICE"+str(devid),"COLOR_TYPE"):
            self.color_type = config["DEVICE"+str(devid)]["COLOR_TYPE"]
        self.color_brightness = None
        self.default_skip_time = False
        if config.has_option("DEVICE"+str(devid),"SKIPTIME"):
            self.default_skip_time = config["DEVICE"+str(devid)].getboolean("SKIPTIME")
        self.skip_time = self.default_skip_time
        self.forceoff = True
        if config.has_option("DEVICE"+str(devid),"FORCEOFF"):
            self.forceoff = config["DEVICE"+str(devid)].getboolean("FORCEOFF")
        self.ignoremode = False
        if config.has_option("DEVICE"+str(devid),"IGNOREMODE"):
            self.ignoremode = config["DEVICE"+str(devid)].getboolean("IGNOREMODE")
        if config.has_option("DEVICE"+str(devid),"NAME"):
            self.name = config["DEVICE"+str(devid)]["NAME"]
        self.icon = None
        if config.has_option("DEVICE"+str(devid),"ICON"):
            self.icon = config["DEVICE"+str(devid)]["ICON"]
        self.action_delay = 0
        self.last_action_timestamp = 0
        if config.has_option("DEVICE"+str(devid),"ACTION_DELAY"):
            self.action_delay = int(config["DEVICE"+str(devid)]["ACTION_DELAY"])
        self.has_pseudodevice = None

    def pre_run(self, color):
        if self.success:
            return True
        if self.color_type == "noop":
            debug.write("Device ({}) {} does not handle requests."
                        .format(self.device_type, self.device), 0)
            self.success = True
            return True
        if self.action_delay != 0 and self.last_action_timestamp + self.action_delay > int(time.time()):
            debug.write("Device ({}) {} is still executing previous request."
                        .format(self.device_type, self.device), 0)
            self.state = DEVICE_STANDBY
            return True
        if color == DEVICE_SKIP:
            self.success = True
            return True
        if not self.get_time_check():
            return True
        if not self.ignoremode:
            if not self.auto_mode and self.request_auto_mode and not self.reset_mode:
                # AUTO mode request on MANUAL device
                debug.write("{} device {} is set in MANUAL mode, skipping."
                            .format(self.device_type, self.device), 0)
                self.success = True
                return True
            if self.auto_mode and not self.request_auto_mode and not self.reset_mode:
                debug.write("{} device {} set to MANUAL mode."
                            .format(self.device_type, self.device), 0)
                self.auto_mode = False
            if self.reset_mode:
                if not self.auto_mode:
                    debug.write("{} device {} set back to AUTO mode."
                                .format(self.device_type, self.device), 0)
                self.auto_mode = True
                self.reset_mode = False
        else:
            debug.write("Skipping mode evaluation for {} device {}."
                        .format(self.device_type, self.device), 0)
        if self.state == color and color != self.convert(DEVICE_OFF):
            self.success = True
            debug.write("Device ({}) {} is already of the requested state, skipping."
                        .format(self.device_type, self.device), 0)
            return True
        if self.state == color and color == self.convert(DEVICE_OFF) and not self.forceoff:
            self.success = True
            debug.write("Device ({}) {} is already off and forcing-off disabled, skipping."
                        .format(self.device_type, self.device), 0)
            return True

        if self.action_delay != 0:
            self.last_action_timestamp = time.time()
        return self.run(color)

    def convert(self, color):
        if self.color_type is None:
            debug.write("Device {} must declare a state type. Quitting.",2)
            quit()
        return convert_color(color, self.color_type)

    def post_run(self):
        """ Prepares the device for a future request """
        self.success = False
        self.skip_time = self.default_skip_time
        return

    def get_state(self):
        """ Getter for the actual color """
        return self.state

    def get_time_check(self, now_time=None):
        if now_time is None:
            now_time = datetime.datetime.now().time()
        if self.start_event_time is not None and not self.skip_time and datetime.time(6, 00) < now_time < self.start_event_time:
            self.success = True
            debug.write("Device ({}) {} skipped due to actual time."
                        .format(self.device_type, self.device), 0)
            return False
        return True

    def set_event_time(self, event_time, skip_time = False):
        self.start_event_time = event_time
        self.skip_time = skip_time
        return

    def descriptions(self):
        """ Getter for the device description """
        return self.description

    def disconnect(self):
        """ Disconnects the device """
        pass

    def create_pseudodevice(self):
        """ Used to create shared pseudo-devices (non-state devices), for example linkers/connectors for a wide range of devices """
        pass

    def get_pseudodevice(self, pseudodevice):
        """ Used to receive the shared pseudo-devices class from the devicemanager """
        pass
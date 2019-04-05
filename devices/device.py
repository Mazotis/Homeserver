#!/usr/bin/env python3
'''
    File name: device.py
    Author: Maxime Bergeron
    Date last modified: 13/03/2019
    Python Version: 3.7

    Main wrapper object for all Lightserver devices. Not a device per-se.
'''

from devices.common import *

class device(object):
    def __init__(self, devid, config):
        self.devid = devid
        self.description = config["DEVICE"+str(devid)]["DESCRIPTION"]
        self.success = False
        self._connection = None
        self.group = config["DEVICE"+str(devid)]["GROUP"].split(',')
        self.priority = 0
        self.state = 0
        self.device_type = None
        self.default_skip_time = False
        if config.has_option("DEVICE"+str(devid),"SKIPTIME"):
            self.default_skip_time = config["DEVICE"+str(devid)].getboolean("SKIPTIME")
        self.skip_time = self.default_skip_time
        self.forceoff = True
        if config.has_option("DEVICE"+str(devid),"FORCEOFF"):
            self.forceoff = config["DEVICE"+str(devid)].getboolean("FORCEOFF")

    def run(self, color, priority):
        if self.success:
            return True
        if not self.skip_time:
            self.success = True
            debug.write("Device ({}) {} skipped due to actual time."
                        .format(self.device_type, self.device), 0)
            return True
        if color == LIGHT_SKIP:
            self.success = True
            return True
        if self.priority > priority:
            debug.write("{} device {} is set with higher priority ({}), skipping."
                                  .format(self.device_type, self.device, self.priority), 0)
            self.success = True
            return True
        if priority == 3:
            self.priority = 1
        else:
            self.priority = priority
        if self.state == color and color != self.convert(LIGHT_OFF):
            self.success = True
            debug.write("Device ({}) {} is already of the requested state, skipping."
                        .format(self.device_type, self.device), 0)
            return True
        if self.state == color and color == self.convert(LIGHT_OFF) and not self.forceoff:
            self.success = True
            debug.write("Device ({}) {} is already off and forcing-off disabled, skipping."
                        .format(self.device_type, self.device), 0)
            return True
        return self.color(color, priority)

    def convert(self, color):
        """ Conversion to a color code acceptable by the device """
        return color

    def reinit(self):
        """ Prepares the device for a future request """
        self.success = False
        self.skip_time = self.default_skip_time
        return

    def get_state(self):
        """ Getter for the actual color """
        return self.state

    def set_skip_time(self):
        self.skip_time = True
        return

    def descriptions(self):
        """ Getter for the device description """
        return "[{}] - {}".format(self.device_type, self.description)

    def disconnect(self):
        """ Disconnects the device """
        pass
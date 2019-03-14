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
        self.state = None
        self.device_type = None

    def run(self, color, priority):
        if self.success:
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
        if self.state == color:
            self.success = True
            debug.write("Device ({}) {} is already of the requested state, skipping."
                        .format(self.device_type, self.device), 0)
            return True
        return self.color(color, priority)

    def convert(self, color):
        """ Conversion to a color code acceptable by the device """
        return color

    def reinit(self):
        """ Prepares the device for a future request """
        self.success = False

    def get_state(self):
        """ Getter for the actual color """
        return self.state

    def descriptions(self):
        """ Getter for the device description """
        return "[{}] - {}".format(self.device_type, self.description)

    def disconnect(self):
        """ Disconnects the device """
        pass
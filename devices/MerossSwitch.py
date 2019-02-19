#!/usr/bin/env python3
'''
    File name: MerossSwitch.py
    Author: Maxime Bergeron
    Date last modified: 19/02/2019
    Python Version: 3.7

    The MerossSwitch for Meross Switches handler class
'''

from devices.common import *
from devices.Meross import Meross

class MerossSwitch(object):
    """ Methods for driving a Decora wifi switch """
    def __init__(self, devid, config):
        if meross is None:
            self.meross = Meross(devid, config)
        else:
            self.meross = meross
        self.devid = devid
        self.device = config["DEVICE"+str(devid)]["ADDRESS"]
        self.description = config["DEVICE"+str(devid)]["DESCRIPTION"]
        self.group = config["DEVICE"+str(devid)]["GROUP"]
        self.subgroup = config["DEVICE"+str(devid)]["SUBGROUP"]
        self.device_type = "MerossSwitch"
        self.state = "0"
        self.priority = 0
        self.success = False
        debug.write("Created device MerossSwitch with MAC {}.".format(self.device), 0)

    def convert(self, color):
        """ Conversion to a color code acceptable by the device """
        #TODO rrggbb to ...this format...
        return color

    def color(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        if len(color) > 2:
            debug.write("Unhandled color format {}".format(color), 1)
            return True
        if self.success:
            return True
        if color == LIGHT_SKIP:
            self.success = True
            return True
        if self.priority > priority:
            debug.write("Meross switch {} is set with higher priority ({}), skipping."
                                  .format(self.device, self.priority), 0)
            self.success = True
            return True
        if priority == 3:
            self.priority = 1
        else:
            self.priority = priority
        if color == LIGHT_OFF:
            self.meross.request(self.device, False)
            self.state = "0"
            self.success = True
            return True
        elif self.state == color:
            self.success = True
            debug.write("Device (meross) {} is already of the requested color, skipping."
                                  .format(self.device), 0)
            return True
        elif color == LIGHT_ON:
            self.meross.request(self.device, True)
            self.state = "1"
            self.success = True
            return True
        else:
            debug.write("Unknown state {} for device {}, falling back to OFF."
                        .format(color, self.device), 0)
            self.meross.request(self.device, False)
            self.state = "0"
            self.success = True
            return True

    def reinit(self):
        """ Prepares the device for a future request """
        self.success = False

    def get_state(self):
        """ Getter for the actual color """
        return self.state

    def descriptions(self):
        """ Getter for the device description """
        desctext = "[Meross account email: " + self.meross.email + "] " + self.description
        return desctext

    def disconnect(self):
        self.meross.disconnect()
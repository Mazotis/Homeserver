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
from devices.device import device

class MerossSwitch(device):
    """ Methods for driving a Decora wifi switch """
    def __init__(self, devid, config):
        super().__init__(devid, config)
        if meross is None:
            self.meross = Meross(devid, config)
        else:
            self.meross = meross
        self.device = config["DEVICE"+str(devid)]["ADDRESS"]
        self.device_type = "MerossSwitch"
        self.state = "0"
        debug.write("Created device MerossSwitch with MAC {}.".format(self.device), 0)

    def color(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        if len(color) > 2:
            debug.write("Unhandled color format {}".format(color), 1)
            return True
        if color == LIGHT_OFF:
            self.meross.request(self.device, False)
            self.state = "0"
            self.success = True
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

    def disconnect(self):
        self.meross.disconnect()
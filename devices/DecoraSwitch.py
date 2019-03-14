#!/usr/bin/env python3
'''
    File name: DecoraSwitch.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    The DecoraSwitch for Leviton Decora Switches handler class
'''
from devices.common import *
from devices.device import device
from devices.Decora import Decora

class DecoraSwitch(device):
    """ Methods for driving a Decora wifi switch """
    def __init__(self, devid, config):
        super().__init__(devid, config)
        if decora is None:
            self.decora = Decora(devid, config)
        else:
            self.decora = decora
        self.device = config["DEVICE"+str(devid)]["NAME"]
        self.intensity = config["DEVICE"+str(devid)]["DEFAULT_INTENSITY"]
        self.device_type = "DecoraSwitch"
        self.state = "0"
        debug.write("Created device DecoraSwitch named {}.".format(self.device), 0)

    def color(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        if len(color) > 3:
            debug.write("Unhandled color format {}".format(color), 1)
            return True
        if self.success:
            return True
        if color == LIGHT_SKIP:
            self.success = True
            return True
        if self.priority > priority:
            debug.write("Decora bulb {} is set with higher priority ({}), skipping."
                                  .format(self.device, self.priority), 0)
            self.success = True
            return True
        if priority == 3:
            self.priority = 1
        else:
            self.priority = priority
        _att = {}
        if color == LIGHT_OFF:
            _att['power'] = 'OFF'
            self.decora.request(self.device, _att)
            self.state = "0"
            self.success = True
            return True
        elif self.state == color:
            self.success = True
            debug.write("Device (decora) {} is already of the requested color, skipping."
                                  .format(self.device), 0)
            return True
        elif color == LIGHT_ON:
            _att['power'] = 'ON'
            _att['brightness'] = int(self.intensity)
            self.decora.request(self.device, _att)
            self.state = "1"
            self.success = True
            return True
        else:
            _att['brightness'] = int(color)
            self.decora.request(self.device, _att)
            self.state = color
            self.success = True
            return True

    def disconnect(self):
        self.decora.disconnect()
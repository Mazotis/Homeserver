#!/usr/bin/env python3
'''
    File name: DecoraSwitch.py
    Author: Maxime Bergeron
    Date last modified: 14/03/2019
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
        self.device = config["DEVICE"+str(devid)]["DEVICE"]
        self.intensity = config["DEVICE"+str(devid)]["DEFAULT_INTENSITY"]
        self.device_type = "DecoraSwitch"
        self.state = "0"
        self.color_type = "100"
        debug.write("Created device DecoraSwitch named {}.".format(self.device), 0, self.device_type)

    def run(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        if not (self.decora.disabled):
            _att = {}
            if color == DEVICE_OFF:
                _att['power'] = 'OFF'
                self.decora.request(self.device, _att)
                self.state = "0"
                self.success = True
                return True
            elif color == DEVICE_ON:
                _att['power'] = 'ON'
                _att['brightness'] = int(self.intensity)
                self.decora.request(self.device, _att)
                self.state = self.intensity
                self.success = True
                return True
            else:
                _att['brightness'] = int(color)
                self.decora.request(self.device, _att)
                self.state = color
                self.success = True
                return True
        else:
            debug.write("Skipping device {} - handler connection failed.".format(self.device), 0, self.device_type)
            return True

    def disconnect(self):
        if not (self.decora.disabled):
            self.decora.disconnect()
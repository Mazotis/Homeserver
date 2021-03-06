#!/usr/bin/env python3
'''
    File name: DecoraSwitch.py
    Author: Maxime Bergeron
    Date last modified: 08/12/2020
    Python Version: 3.7

    The DecoraSwitch for Leviton Decora Switches handler class
'''
from core.common import *
from core.device import device
from core.decora import Decora


class DecoraSwitch(device):
    """ Methods for driving a Decora wifi switch """

    def __init__(self, devid):
        super().__init__(devid)
        self.device_id = devid
        self.has_pseudodevice = 'Decora'
        self.device = self.config["DEVICE"]
        self.device_type = "DecoraSwitch"
        self.state = DEVICE_OFF
        if self.color_type is None:
            self.color_type = "100"
        debug.write("Created device DecoraSwitch named {}.".format(
            self.device), 0, self.device_type)

    def run(self, color):
        """ Checks the request and trigger a light change if needed """
        if not (self.decora.disabled):
            _att = {}
            if color == DEVICE_OFF:
                _att['power'] = 'OFF'
                self.interruptible(lambda: self.decora.request(self.device, _att))
                self.state = DEVICE_OFF
            elif color == DEVICE_ON:
                _att['power'] = 'ON'
                _att['brightness'] = int(self.intensity)
                self.interruptible(lambda: self.decora.request(self.device, _att))
                self.state = self.intensity
            else:
                _att['brightness'] = int(color)
                self.interruptible(lambda: self.decora.request(self.device, _att))
                self.state = color
            debug.write("Device {} color changed to {}.".format(self.device, self.state), 0, self.device_type)
            self.success = True
            return True
        else:
            debug.write(
                "Skipping device {} - handler connection failed.".format(self.device), 0, self.device_type)
            self.state = DEVICE_DISABLED
            return True

    def get_state(self):
        if self.state != DEVICE_DISABLED:
            switchState = self.decora.get_switch(self.device)
            self.state = DEVICE_OFF
            if switchState.power == "ON":
                self.state = switchState.brightness
        return self.state

    def create_pseudodevice(self):
        return Decora(self.device_id)

    def get_pseudodevice(self, decora):
        debug.write("Linking Decora {} to pseudodevice {}.".format(
            self.device, decora.email), 0, self.device_type)
        self.decora = decora

    def disconnect(self):
        if not (self.decora.disabled):
            self.decora.disconnect()

    def reconnect(self):
        debug.write("Attempting reconnection of device '{}'. Decora_disabled: {}.".format(
            self.name, self.decora.disabled), 0, self.device_type)
        self.decora.connect()
        self.state = DEVICE_OFF
        self.get_state()

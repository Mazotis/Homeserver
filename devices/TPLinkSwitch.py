#!/usr/bin/env python3
'''
    File name: TP-LinkSwitch.py
    Author: Maxime Bergeron
    Date last modified: 30/07/2019
    Python Version: 3.7

    The TP-Link smartswitch device handler. Allows connections to HS200-210-220 devices.
'''

from pyHS100 import SmartPlug
from pyHS100.smartdevice import SmartDeviceException
from core.common import *
from core.device import device


class TPLinkSwitch(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        # TODO Support multiple TP-Link KASA cloud accounts at the same time ?
        self.config = config["DEVICE" + str(devid)]
        self.ip = self.config["IP"]
        self.device_type = "TP-LinkSwitch"
        self.device = self.config["DEVICE"]
        self.plug = None
        self.dimmable = False
        if config.has_option("DEVICE" + str(devid), "DIMMABLE"):
            self.dimmable = self.config.getboolean("DIMMABLE")
            if self.dimmable and self.color_type is None:
                self.color_type = "100"
        elif self.color_type is None:
            self.color_type = "io"
        self.connect()
        debug.write("Created device with IP {} and name {}.".format(
            self.ip, self.device), 0, self.device_type)

    def run(self, color):
        if not self.disabled:
            if color == DEVICE_ON:
                if self.dimmable:
                    self.plug.brightness = self.convert(self.intensity)
                else:
                    self.plug.turn_on()
                self.state = DEVICE_ON
            elif color == DEVICE_OFF:
                self.plug.turn_off()
                self.state = DEVICE_OFF
            elif self.dimmable:
                self.plug.brightness = int(color)
                self.state = color
            else:
                debug.write("Unknown color code for device {}".format(
                    self.device), 1, self.device_type)
        self.success = True
        return True

    def get_state(self):
        if not self.disabled:
            try:
                if self.plug.state == "OFF":
                    self.state = DEVICE_OFF
                else:
                    if self.dimmable:
                        self.state = self.plug.brightness
                    else:
                        self.state = DEVICE_ON
                return self.state
            except SmartDeviceException as ex:
                debug.write("Connection failed for device {}, disabling.".format(
                    self.name), 1, "TP-LinkSwitch")
                self.disabled = True
                self.state = DEVICE_DISABLED
                self.plug = None
                pass
        return self.state

    def connect(self):
        self.plug = SmartPlug(self.ip)

    def reconnect(self):
        debug.write("Attempting reconnection of device {}.".format(
                    self.name), 0, "TP-LinkSwitch")
        self.connect()
        self.disabled = False
        self.get_state()

    def disconnect(self):
        # TODO - Check if disconnection is required
        pass

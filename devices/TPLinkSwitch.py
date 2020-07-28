#!/usr/bin/env python3
'''
    File name: TPLinkSwitch.py
    Author: Maxime Bergeron
    Date last modified: 16/06/2020
    Python Version: 3.7

    The TPLink smartswitch device handler. Allows connections to HS200-210-220 devices.
'''

import asyncio
from kasa import SmartPlug
from kasa.smartdevice import SmartDeviceException
from core.common import *
from core.device import device


class TPLinkSwitch(device):
    def __init__(self, devid):
        super().__init__(devid)
        # TODO Support multiple TP-Link KASA cloud accounts at the same time ?
        self.ip = self.config["IP_ADDRESS"]
        self.device_type = "TPLinkSwitch"
        self.device = self.config["DEVICE"]
        self.plug = None
        self.dimmable = False
        if self.config.dev_has_option("DIMMABLE"):
            self.dimmable = self.config.get_value("DIMMABLE", bool)
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
                    self.interruptible(lambda: asyncio.run(self.plug.set_brightness(self.convert(self.intensity))))
                else:
                    self.interruptible(lambda: asyncio.run(self.plug.turn_on()))
                self.state = DEVICE_ON
            elif color == DEVICE_OFF:
                self.interruptible(lambda: asyncio.run(self.plug.turn_off()))
                self.state = DEVICE_OFF
            elif self.dimmable:
                self.interruptible(lambda: asyncio.run(self.plug.set_brightness(int(color))))
                self.state = color
            else:
                debug.write("Unknown color code for device {}".format(
                    self.device), 1, self.device_type)
        self.success = True
        return True

    def get_state(self):
        if not self.disabled:
            try:
                asyncio.run(self.plug.update())
                if not self.plug.is_on:
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
            except KeyError:
                debug.write("Device {} is not yet supported. Disabling...".format(self.name), 1, "TP-LinkSwitch")
                self.disabled = True
                self.state = DEVICE_DISABLED
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
        pass

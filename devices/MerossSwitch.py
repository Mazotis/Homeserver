#!/usr/bin/env python3
'''
    File name: MerossSwitch.py
    Author: Maxime Bergeron
    Date last modified: 02/02/2020
    Python Version: 3.7

    The MerossSwitch for Meross Switches handler class
'''

from core.common import *
from core.meross import Meross
from core.device import device
from meross_iot.cloud.exceptions.CommandTimeoutException import CommandTimeoutException
from meross_iot.cloud.exceptions.OfflineDeviceException import OfflineDeviceException


class MerossSwitch(device):
    """ Methods for driving a Meross wifi switch """

    def __init__(self, devid):
        super().__init__(devid)
        self.device_id = devid
        self.has_pseudodevice = 'Meross'
        self.device = self.config["ADDRESS"]
        self.device_type = "MerossSwitch"
        if self.color_type is None:
            self.color_type = "io"
        debug.write("Created device MerossSwitch with MAC {}.".format(
            self.device), 0, self.device_type)

    def run(self, color):
        """ Checks the request and trigger a light change if needed """
        if not self.meross.disabled and self.state != DEVICE_DISABLED:
            if color == DEVICE_OFF:
                debug.write(
                    "Turning Meross device {} OFF.".format(self.device), 0)
                self.meross_dev.turn_off()
                self.state = DEVICE_OFF
                self.success = True
                return True
            elif color == DEVICE_ON:
                debug.write(
                    "Turning Meross device {} ON.".format(self.device), 0)
                self.meross_dev.turn_on()
                self.state = DEVICE_ON
                self.success = True
                return True
            debug.write("Unknown state {} for device {}, falling back to OFF."
                        .format(color, self.device), 0, self.device_type)
            self.meross_dev.turn_off()
            self.state = DEVICE_OFF
        self.success = True
        return True

    def get_state(self):
        # TODO Is this the proper limit for ON/OFF ?
        if not self.meross.disabled:
            try:
                if self.meross_dev.supports_electricity_reading():
                    if int(self.meross_dev.get_electricity()['current']) > 100:
                        self.state = DEVICE_ON
                    else:
                        self.state = DEVICE_OFF
            except OfflineDeviceException:
                debug.write(
                    "Device {} is offline. Set as disabled.".format(self.device), 1)
                self.state = DEVICE_DISABLED
                return self.state
            except CommandTimeoutException:
                debug.write(
                    "Failed to obtain current state for device {}. Fallback to server-side reported state.".format(self.device), 1)
                return self.state
            except AttributeError:
                debug.write(
                    "Device {} is offline. Set as disabled.".format(self.device), 1)
                self.state = DEVICE_DISABLED
                return self.state

        else:
            self.state = DEVICE_DISABLED
        return self.state

    def create_pseudodevice(self):
        return Meross(self.device_id)

    def get_pseudodevice(self, meross):
        debug.write("Linking Meross {} to pseudodevice {}.".format(
            self.device, meross.email), 0, self.device_type)
        self.meross = meross
        self.meross_dev = meross.get_meross_device(self.device)
        if not self.meross_dev:
            self.state = DEVICE_DISABLED

    def disconnect(self):
        pass
        # self.meross.disconnect()

    def reconnect(self):
        debug.write("Attempting reconnection of device {}.".format(
            self.name), 0, "MerossSwitch")
        if self.meross.disabled:
            self.meross.connect()
        self.get_state()

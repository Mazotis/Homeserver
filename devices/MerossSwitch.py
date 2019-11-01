#!/usr/bin/env python3
'''
    File name: MerossSwitch.py
    Author: Maxime Bergeron
    Date last modified: 17/10/2019
    Python Version: 3.7

    The MerossSwitch for Meross Switches handler class
'''

from core.common import *
from core.meross import Meross
from core.device import device


class MerossSwitch(device):
    """ Methods for driving a Meross wifi switch """

    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.device_id = devid
        self.config = config
        self.has_pseudodevice = 'Meross'
        self.device = config["DEVICE" + str(devid)]["ADDRESS"]
        self.device_type = "MerossSwitch"
        self.state = "0"
        if self.color_type is None:
            self.color_type = "io"
        debug.write("Created device MerossSwitch with MAC {}.".format(
            self.device), 0, self.device_type)

    def run(self, color):
        """ Checks the request and trigger a light change if needed """
        if not self.meross.disabled:
            if color == DEVICE_OFF:
                debug.write(
                    "Turning Meross device {} OFF.".format(self.device), 0)
                self.meross_dev.turn_off()
                self.state = "0"
                self.success = True
                return True
            elif color == DEVICE_ON:
                debug.write(
                    "Turning Meross device {} ON.".format(self.device), 0)
                self.meross_dev.turn_on()
                self.state = "1"
                self.success = True
                return True
            else:
                debug.write("Unknown state {} for device {}, falling back to OFF."
                            .format(color, self.device), 0, self.device_type)
                self.meross_dev.turn_off()
                self.state = "0"
                self.success = True
                return True

    def get_state(self):
        # TODO Is this the proper limit for ON/OFF ?
        if not self.meross.disabled:
            try:
                if self.meross_dev.supports_electricity_reading():
                    if int(self.meross_dev.get_electricity()['current']) > 100:
                        self.state = "1"
                    else:
                        self.state = "0"
            except self.meross.meross_iot.cloud.exceptions.OfflineDeviceException.OfflineDeviceException:
                debug.write(
                    "Device {} is offline. Set as disabled.".format(self.device), 1)
                self.state = DEVICE_DISABLED
                return self.state
            except self.meross.meross_iot.cloud.exceptions.CommandTimeoutException.CommandTimeoutException:
                debug.write(
                    "Failed to obtain current state for device {}. Fallback to server-side reported state.".format(self.device), 1)
                return self.state
        else:
            self.state = DEVICE_DISABLED
        return self.state

    def create_pseudodevice(self):
        return Meross(self.device_id, self.config)

    def get_pseudodevice(self, meross):
        debug.write("Linking Meross {} to pseudodevice {}.".format(
            self.device, meross.email), 0, self.device_type)
        self.meross = meross
        self.meross_dev = self.meross.get_meross_device(self.device)

    def disconnect(self):
        pass
        # self.meross.disconnect()

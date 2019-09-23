#!/usr/bin/env python3
'''
    File name: Meross.py
    Author: Maxime Bergeron
    Date last modified: 19/02/2019
    Python Version: 3.7

    The Meross device handler. Allows connections to Meross Cloud. Not a device per-se.
'''

from meross_iot.api import MerossHttpClient
from devices.common import *

class Meross(object):
    def __init__(self, devid, config):
        #TODO Support multiple Meross cloud accounts at the same time ?
        self.email = config["DEVICE"+str(devid)]["EMAIL"]
        self.password = config["DEVICE"+str(devid)]["PASSWORD"]
        meross = self
        debug.write("Created pseudo-device Meross with account {}.".format(self.email), 0)

    def request(self, address, state):
        self.connect()
        for _dev in self.meross_devices:
            _device = _dev.get_sys_data()
            if str(_device['all']['system']['hardware']['macAddress']) == address.lower():
                if state:
                    debug.write("Turning Meross device {} ON.".format(address), 0)
                    _dev.turn_on()
                    return
                else:
                    debug.write("Turning Meross device {} OFF.".format(address), 0)
                    _dev.turn_off()
                    return
        debug.write("MerossSwitch device {} not found in cloud.".format(address), 1)

    def connect(self):
        httpHandler = MerossHttpClient(email=self.email, password=self.password)
        self.meross_devices = httpHandler.list_supported_devices()

    def disconnect(self):
        #TODO - Check if disconnection is required
        pass

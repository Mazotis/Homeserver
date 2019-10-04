#!/usr/bin/env python3
'''
    File name: Meross.py
    Author: Maxime Bergeron
    Date last modified: 19/02/2019
    Python Version: 3.5

    The Meross device handler. Allows connections to Meross Cloud. Not a device per-se.
'''

from meross_iot.manager import MerossManager
from core.common import *


class Meross(object):
    def __init__(self, devid, config):
        # TODO Support multiple Meross cloud accounts at the same time ?
        self.email = config["DEVICE" + str(devid)]["EMAIL"]
        self.password = config["DEVICE" + str(devid)]["PASSWORD"]
        self.manager = False
        self.meross_devices = None
        self.meross_data = []
        debug.write(
            "Created pseudo-device Meross with account {}.".format(self.email), 0)

    def get_meross_device(self, address):
        self.connect()
        for _cnt, _dev in enumerate(self.meross_devices):
            if str(self.meross_data[_cnt]['all']['system']['hardware']['macAddress']) == address.lower():
                return _dev
        debug.write(
            "MerossSwitch device {} not found in cloud.".format(address), 1)

    def connect(self):
        self.manager = MerossManager(
            meross_email=self.email, meross_password=self.password)
        self.manager.start()
        # TODO Dynamic loading of these devices while the server is running?
        if self.meross_devices is None:
            self.meross_devices = self.manager.get_supported_devices()
            for _dev in self.meross_devices:
                self.meross_data.append(_dev.get_sys_data())

    def disconnect(self):
        # For some reason, does not play well with disconnects
        pass
        # if self.manager is not False:
        #    self.manager.stop()
        #    self.manager = False

#!/usr/bin/env python3
'''
    File name: Meross.py
    Author: Maxime Bergeron
    Date last modified: 25/05/2020
    Python Version: 3.7

    The Meross device handler. Allows connections to Meross Cloud. Not a device per-se.
'''

from core.common import *
from meross_iot.manager import MerossManager
from meross_iot.api import UnauthorizedException
from meross_iot.api import TooManyTokensException
from meross_iot.cloud.exceptions.OfflineDeviceException import OfflineDeviceException
from meross_iot.cloud.exceptions.CommandTimeoutException import CommandTimeoutException
from threading import Lock


class Meross(object):
    meross_lock = Lock()

    def __init__(self, devid):
        # TODO Support multiple Meross cloud accounts at the same time ?
        self.email = getConfigHandler().get_device(devid, "EMAIL")
        self.password = getConfigHandler().get_device(devid, "PASSWORD")
        self.manager = False
        self.disabled = False
        self.connected = False
        debug.write(
            "Created pseudo-device Meross with account {}.".format(self.email), 0)

    def get_meross_device(self, address):
        if not self.connected:
            self.connect()
        if not self.disabled and self.connected:
            meross_devices = self.manager.get_supported_devices()
            for _dev in meross_devices:
                try:
                    if str(_dev.get_sys_data()['all']['system']['hardware']['macAddress']) == address.lower():
                        return _dev
                except OfflineDeviceException:
                    continue
                except CommandTimeoutException:
                    continue
            debug.write(
                "MerossSwitch device {} not found in cloud or offline.".format(address), 1)
        return False

    def connect(self, release_lock=False):
        with Meross.meross_lock:
            if self.connected:
                self.manager.stop()
            try:
                self.disabled = False
                self.manager = MerossManager.from_email_and_password(
                    meross_email=self.email, meross_password=self.password)
                self.manager.start()
                self.connected = True
                return
            except UnauthorizedException:
                self.disabled = True
                debug.write("Connection failed for meross email {}, disabling devices.".format(
                    self.email), 1)
                pass
            except TooManyTokensException:
                self.disabled = True
                debug.write("Too many requests for meross email {}, disabling devices.".format(
                    self.email), 1)
                pass

    def disconnect(self):
        # Still does not play well with disconnects. Use only on server shutdown
        with Meross.meross_lock:
            self.manager.stop()
            self.manager = False
            self.connected = False

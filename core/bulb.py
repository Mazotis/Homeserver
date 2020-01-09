#!/usr/bin/env python3
'''
    File name: Bulb.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    The Bulb common class to simplify bluepy-controlled BLE bulbs. Not a device per-se.
'''

import bluepy.btle as ble
import functools
import time
from core.common import *
from core.device import device


def connect_ble(_f):
    """ Wrapper for functions which requires an active BLE connection using bluepy """
    @functools.wraps(_f)
    def _conn_wrap(self, *args):
        tries = 0
        while self._connection is None:
            try:
                debug.write("CONnecting to device ({})...".format(
                    self.description), 0, self.device_type)
                self._connection = ble.Peripheral(self.device)
            except Exception as ex:
                debug.write("Device ({}) connection failed. Exception: {}"
                            .format(self.description, ex), 1, self.device_type)
                self._connection = None
            if self._connection is None:
                debug.write("Attempting reconnection to device ({})...".format(
                    self.description), 0, self.device_type)
            tries = tries + 1
            if tries == 6:
                debug.write("Device ({}) connection failed."
                            .format(self.description), 1, self.device_type)
                self._connection = None
        return _f(self, *args)
    return _conn_wrap


class Bulb(device):
    """ Global bulb functions and variables """

    def __init__(self, devid):
        super().__init__(devid)
        self.device = self.config["ADDRESS"]

    def disconnect(self):
        """ Disconnects the device """
        try:
            if self._connection is not None:
                debug.write(
                    "DISconnecting from device {}".format(self.device), 0, self.device_type)
                self._connection.disconnect()
        except ble.BTLEException:
            debug.write("Device {} disconnection failed. Already disconnected?"
                        .format(self.device), 1, self.device_type)
            pass
        except Exception as ex:
            debug.write("Unhandled exception for device {}: {}"
                        .format(self.device, ex), 1, self.device_type)
            pass

        self._connection = None

#!/usr/bin/env python3
'''
    File name: Bulb.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    The Bulb common class to simplify bluepy-controlled BLE bulbs. Not a device per-se.
'''

import bluepy.btle as ble
from devices.common import *
from devices.device import device

class Bulb(device):
    """ Global bulb functions and variables """
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.device = config["DEVICE"+str(devid)]["ADDRESS"]
        debug.write("Created device Bulb: {}.".format(self.description), 0)

    def disconnect(self):
        """ Disconnects the device """
        try:
            if self._connection is not None:
                debug.write("DISconnecting from device {}".format(self.device), 0)
                self._connection.disconnect()
        except ble.BTLEException:
            debug.write("Device ({}) {} disconnection failed. Already disconnected?"
                                  .format(self.device_type, self.device), 1)
            pass
        except:
            pass

        self._connection = None
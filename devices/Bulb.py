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

class Bulb(object):
    """ Global bulb functions and variables """
    def __init__(self, devid, config):
        self.devid = devid
        self.device = config["DEVICE"+str(devid)]["ADDRESS"]
        self.description = config["DEVICE"+str(devid)]["DESCRIPTION"]
        self.success = False
        self._connection = None
        self.group = config["DEVICE"+str(devid)]["GROUP"]
        self.subgroup = config["DEVICE"+str(devid)]["SUBGROUP"]
        self.priority = 0
        self.state = None
        self.device_type = None
        debug.write("Created device Bulb: {}.".format(self.description), 0)

    def reinit(self):
        """ Prepares the device for a future request """
        self.success = False

    def get_state(self):
        """ Getter for the actual color """
        return self.state

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
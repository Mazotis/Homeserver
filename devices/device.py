#!/usr/bin/env python3
'''
    File name: device.py
    Author: Maxime Bergeron
    Date last modified: 13/03/2019
    Python Version: 3.7

    Main wrapper object for all Lightserver devices. Not a device per-se.
'''

from devices.common import *

class device(object):
    def __init__(self, devid, config):
        self.devid = devid
        self.description = config["DEVICE"+str(devid)]["DESCRIPTION"]
        self.success = False
        self._connection = None
        self.group = config["DEVICE"+str(devid)]["GROUP"].split(',')
        self.priority = 0
        self.state = None
        self.device_type = None

    def convert(self, color):
        """ Conversion to a color code acceptable by the device """
        return color

    def reinit(self):
        """ Prepares the device for a future request """
        self.success = False

    def get_state(self):
        """ Getter for the actual color """
        return self.state

    def descriptions(self):
        """ Getter for the device description """
        return "[{}] - {}".format(self.device_type, self.description)

    def disconnect(self):
        """ Disconnects the device """
        pass
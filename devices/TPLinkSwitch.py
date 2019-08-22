#!/usr/bin/env python3
'''
    File name: TP-LinkSwitch.py
    Author: Maxime Bergeron
    Date last modified: 30/07/2019
    Python Version: 3.7

    The TP-Link smartswitch device handler. Allows connections to HS200-210-220 devices.
'''

from pyHS100 import SmartPlug
from devices.common import *
from devices.device import device

class TPLinkSwitch(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        #TODO Support multiple TP-Link KASA cloud accounts at the same time ?
        self.config = config["DEVICE"+str(devid)]
        self.ip = self.config["IP"]
        self.device_type = "TP-LinkSwitch"
        self.device = self.config["NAME"]
        self.plug = None
        debug.write("Created device TP-LinkSwitch with IP {} and name {}.".format(self.ip, self.device), 0)

    def color(self, color, priority):
        self.connect()
        if color == "1":
            self.plug.turn_on()
        elif color == "0":
            self.plug.turn_off()
        else:
            debug.write("Unknown color code for device ".format(self.device), 1)
        self.success = True
        return True

    def connect(self):
        self.plug = SmartPlug(self.ip)

    def disconnect(self):
        #TODO - Check if disconnection is required
        pass

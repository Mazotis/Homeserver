#!/usr/bin/env python3
'''
    File name: Milight.py
    Author: Maxime Bergeron
    Date last modified: 14/03/2019
    Python Version: 3.7

    A generic bash function On/Off device handler class 
'''

import subprocess
from devices.common import *
from devices.device import device

class GenericOnOff(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.config = config["DEVICE"+str(devid)]
        self.device = self.config["NAME"]
        self.device_type = "GenericOnOff"
        self.state = 0 # Gets updated from the DeviceManager
        debug.write("Created generic On/Off device named: {}".format(self.device), 0)

    def get_state(self):
        if self.config["STATE"] and not self.success:
            try:
                _stdout = subprocess.check_output(self.config["STATE"], 
                                                  shell=True).decode('UTF-8')
            except subprocess.CalledProcessError:
                self.state = 0
                return 0
            if self.config["STATE_ON_EXPECT"] in _stdout:
                self.state = 1
                return 1
            self.state = 0
            return 0
        return self.state

    def convert(self, color):
        # TODO: Only accept int values of 1, 2 and LIGHT_SKIP?
        if int(color) == 1:
            return 1
        if int(color) == 2:
            return 2
        if color == LIGHT_SKIP:
            return LIGHT_SKIP
        return 0
        
    def color(self, color, priority):
        if color == 0 and self.config["OFF"]:
            debug.write("Turning device {} OFF".format(self.device), 0)
            os.system(self.config["OFF"])
            self.success = True
            self.state = 0
            return True
        elif color == 1 and self.config["ON"]:
            debug.write("Turning device {} ON".format(self.device), 0)
            os.system(self.config["ON"])
            self.success = True
            self.state = 1
            return True
        elif color == 2 and self.config["RESTART"]:
            debug.write("Restarting device {}".format(self.device), 0)
            os.system(self.config["RESTART"])
            self.success = True
            self.state = 1
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(color, self.device), 1)
        self.success = True
        return True        
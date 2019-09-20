#!/usr/bin/env python3
'''
    File name: Milight.py
    Author: Maxime Bergeron
    Date last modified: 30/07/2019
    Python Version: 3.7

    A generic bash function On/Off device handler class 
'''

import subprocess
import time
from devices.common import *
from devices.device import device

class GenericOnOff(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.config = config["DEVICE"+str(devid)]
        self.device = self.config["DEVICE"]
        self.device_type = "GenericOnOff"
        self.color_type = "io-ops"
        debug.write("Created generic On/Off device named: {}".format(self.device), 0, self.device_type)

    def get_state(self):
        if self.action_delay != 0 and self.last_action_timestamp + self.action_delay > int(time.time()):
            self.state = LIGHT_STANDBY
            return self.state
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
        
    def color(self, color, priority):
        if color == LIGHT_OFF and self.config["OFF"]:
            debug.write("Turning device {} OFF".format(self.device), 0, self.device_type)
            os.system(self.config["OFF"])
            self.success = True
            self.state = 0
            return True
        elif color == LIGHT_ON and self.config["ON"]:
            debug.write("Turning device {} ON".format(self.device), 0, self.device_type)
            os.system(self.config["ON"])
            self.success = True
            self.state = 1
            return True
        elif color == "2" and self.config["RESTART"]:
            debug.write("Restarting device {}".format(self.device), 0, self.device_type)
            os.system(self.config["RESTART"])
            self.success = True
            self.state = 1
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(color, self.device), 1, self.device_type)
        self.success = True
        return True        
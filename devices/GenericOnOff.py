#!/usr/bin/env python3
'''
    File name: Milight.py
    Author: Maxime Bergeron
    Date last modified: 15/10/2019
    Python Version: 3.7

    A generic bash function On/Off device handler class
'''

import subprocess
import time
from core.common import *
from core.device import device


class GenericOnOff(device):
    def __init__(self, devid):
        super().__init__(devid)
        self.state_check = None
        if self.config.dev_has_option("STATE") and self.config["STATE"] != "":
            self.state_check = self.config["STATE"]
            self.state_expect = self.config["STATE_ON_EXPECT"]
        self.device = self.config["DEVICE"]
        self.device_type = "GenericOnOff"
        if self.color_type is None:
            self.color_type = "io-ops"
        debug.write(
            "Created generic On/Off device named: {}".format(self.device), 0, self.device_type)

    def get_state(self):
        if self.action_delay != 0 and self.last_action_timestamp + self.action_delay > int(time.time()):
            self.state = DEVICE_STANDBY
            return self.state
        if self.state_check is not None and not self.success:
            try:
                _stdout = subprocess.check_output(self.state_check,
                                                  shell=True).decode('UTF-8')
            except subprocess.CalledProcessError:
                self.state = DEVICE_OFF
                return DEVICE_OFF
            if self.state_expect in _stdout:
                self.state = DEVICE_ON
                return DEVICE_ON
            self.state = DEVICE_OFF
            return DEVICE_OFF
        return self.state

    def run(self, color):
        if color == DEVICE_OFF and self.config["OFF"]:
            debug.write("Turning device {} OFF".format(
                self.device), 0, self.device_type)
            os.system(self.config["OFF"])
            self.success = True
            self.state = DEVICE_OFF
            return True
        elif color == DEVICE_ON and self.config["ON"]:
            debug.write("Turning device {} ON".format(
                self.device), 0, self.device_type)
            os.system(self.config["ON"])
            self.success = True
            self.state = DEVICE_ON
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(
            color, self.device), 1, self.device_type)
        self.success = True
        return True

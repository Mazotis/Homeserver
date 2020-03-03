#!/usr/bin/env python3
'''
    File name: HDMITv.py
    Author: Maxime Bergeron
    Date last modified: 28/02/2019
    Python Version: 3.7

    A specialized GenericOnOff for HDMI-connected TV with CEC capabilities
'''

import os
import subprocess
from core.common import *
from core.device import device


class HDMITv(device):
    def __init__(self, devid):
        super().__init__(devid)
        self.device_type = "HDMITv"
        if self.color_type is None:
            self.color_type = "io"
        debug.write("Created HDMITv device named: {}".format(
            self.name), 0, self.device_type)

    def get_state(self):
        if not self.success:
            try:
                _stdout = subprocess.check_output(
                    "echo 'pow 0' | cec-client -s | grep \"power status:\"", shell=True).decode('UTF-8')
            except subprocess.CalledProcessError:
                self.state = DEVICE_OFF
            if "power status: on" in _stdout:
                self.state = DEVICE_ON
        return self.state

    def run(self, color):
        if color == DEVICE_OFF:
            debug.write("Turning device {} OFF".format(
                self.name), 0, self.device_type)
            os.system("echo 'standby 0' | cec-client -s &> /dev/null")
            self.success = True
            self.state = DEVICE_OFF
            return True
        elif color == DEVICE_ON:
            debug.write("Turning device {} ON".format(
                self.name), 0, self.device_type)
            os.system("echo 'on 0' | cec-client -s &> /dev/null")
            self.success = True
            self.state = DEVICE_ON
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(
            color, self.name), 1, self.device_type)
        self.success = True
        return True

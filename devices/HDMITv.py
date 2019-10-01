#!/usr/bin/env python3
'''
    File name: HDMITv.py
    Author: Maxime Bergeron
    Date last modified: 23/09/2019
    Python Version: 3.5

    A specialized GenericOnOff for HDMI-connected TV with CEC capabilities
'''

import subprocess
from devices.common import *
from devices.device import device

class HDMITv(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.config = config["DEVICE"+str(devid)]
        self.device = self.config["DEVICE"]
        self.device_type = "HDMITv"
        if self.color_type is None:
            self.color_type = "io"
        debug.write("Created HDMITv device named: {}".format(self.device), 0, self.device_type)

    def get_state(self):
        if not self.success:
            try:
                _stdout = subprocess.check_output("echo 'pow 0' | cec-client -s", 
                                                  shell=True).decode('UTF-8')
            except subprocess.CalledProcessError:
                self.state = 0
                return 0
            if "power status: on" in _stdout:
                self.state = 1
                return 1
            self.state = 0
            return 0
        return self.state
        
    def run(self, color):
        if color == DEVICE_OFF:
            debug.write("Turning device {} OFF".format(self.device), 0, self.device_type)
            os.system("echo 'standby 0' | cec-client -s")
            self.success = True
            self.state = 0
            return True
        elif color == DEVICE_ON:
            debug.write("Turning device {} ON".format(self.device), 0, self.device_type)
            os.system("echo 'on 0' | cec-client -s")
            self.success = True
            self.state = 1
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(color, self.device), 1, self.device_type)
        self.success = True
        return True   
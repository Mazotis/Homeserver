#!/usr/bin/env python3
'''
    File name: Computer.py
    Author: Maxime Bergeron
    Date last modified: 23/09/2019
    Python Version: 3.5

    A specialized GenericOnOff for linux computer devices.
'''

import subprocess
from devices.common import *
from devices.device import device

class Computer(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.config = config["DEVICE"+str(devid)]
        self.device = self.config["DEVICE"]
        self.device_type = "Computer"
        if self.color_type is None:
            self.color_type = "io-ops"
        self.ip = self.config["IP_ADDRESS"]
        self.mac = self.config["MAC_ADDRESS"]
        self.user = self.config["SSH_USER"]
        self.device_type = "Computer"
        debug.write("Created computer device named: {}".format(self.device), 0, self.device_type)

    def get_state(self):
        if self.action_delay != 0 and self.last_action_timestamp + self.action_delay > int(time.time()):
            self.state = DEVICE_STANDBY
            return self.state
        if not self.success:
            try:
                _stdout = subprocess.check_output("ping {} -c 1 -W 1".format(self.ip), 
                                                  shell=True).decode('UTF-8')
            except subprocess.CalledProcessError:
                self.state = 0
                return 0
            if "1 received" in _stdout:
                self.state = 1
                return 1
            self.state = 0
            return 0
        return self.state
        
    def run(self, color, priority):
    	#TODO support windows ?
        if color == DEVICE_OFF:
            debug.write("Turning device {} OFF".format(self.device), 0, self.device_type)
            os.system("ssh {}@{} 'sudo shutdown now'".format(self.user, self.ip))
            self.success = True
            self.state = 0
            return True
        elif color == DEVICE_ON:
            debug.write("Turning device {} ON".format(self.device), 0, self.device_type)
            os.system("/usr/bin/wakeonlan {}".format(self.mac))
            self.success = True
            self.state = 1
            return True
        elif color == "2":
            debug.write("Restarting device {}".format(self.device), 0, self.device_type)
            os.system("ssh {}@{} 'sudo reboot'".format(self.user, self.ip))
            self.success = True
            self.state = 1
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(color, self.device), 1, self.device_type)
        self.success = True
        return True   
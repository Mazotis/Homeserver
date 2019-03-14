#!/usr/bin/env python3
'''
    File name: Milight.py
    Author: Maxime Bergeron
    Date last modified: 11/02/2019
    Python Version: 3.7

    A generic bash function On/Off device handler class 
'''
from devices.common import *
from devices.device import device

class GenericOnOff(device):
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.config = config
        self.device = self.config["DEVICE"+str(devid)]["NAME"]
        self.device_type = "GenericOnOff"
        debug.write("Created generic On/Off device named: {}".format(self.device), 0)

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
        if self.success:
            return True
        if color == LIGHT_SKIP:
            self.success = True
            return True
        if self.priority > priority:
            debug.write("GenericOnOff {} is set with higher priority ({}), skipping."
                                  .format(self.device, self.priority), 0)
            self.success = True
            return True
        if priority == 3:
            self.priority = 1
        else:
            self.priority = priority
        if color == 0 and self.config["DEVICE"+str(self.devid)]["OFF"] is not None:
            debug.write("Turning device {} OFF".format(self.device), 0)
            os.system(self.config["DEVICE"+str(self.devid)]["OFF"])
            self.success = True
            self.state = 0
            return True
        elif self.state == color:
            self.success = True
            debug.write("Device (GenericOnOff) {} is already of the requested state, skipping."
                                  .format(self.device), 0)
            return True
        elif color == 1 and self.config["DEVICE"+str(self.devid)]["ON"] is not None:
            debug.write("Turning device {} ON".format(self.device), 0)
            os.system(self.config["DEVICE"+str(self.devid)]["ON"])
            self.success = True
            self.state = 1
            return True
        elif color == 2 and self.config["DEVICE"+str(self.devid)]["RESTART"] != "None":
            debug.write("Restarting device {}".format(self.device), 0)
            os.system(self.config["DEVICE"+str(self.devid)]["RESTART"])
            self.success = True
            self.state = 1 # Returns to 1 after restart
            return True
        debug.write("Request for state {} cannot be handled for device {}".format(color, self.device), 1)
        self.success = True
        return True        
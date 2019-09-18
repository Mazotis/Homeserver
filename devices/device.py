#!/usr/bin/env python3
'''
    File name: device.py
    Author: Maxime Bergeron
    Date last modified: 13/03/2019
    Python Version: 3.7

    Main wrapper object for all Lightserver devices. Not a device per-se.
'''

from devices.common import *
from modules.convert import convert_color

class device(object):
    def __init__(self, devid, config):
        self.devid = devid
        self.description = config["DEVICE"+str(devid)]["DESCRIPTION"]
        self.success = False
        self._connection = None
        self.group = config["DEVICE"+str(devid)]["GROUP"].split(',')
        self.priority = 0
        self.state = 0
        self.device_type = None
        self.request_auto_mode = True
        self.auto_mode = True
        self.reset_mode = False
        self.default_skip_time = False
        self.name = None
        self.color_type = None
        self.color_brightness = None
        if config.has_option("DEVICE"+str(devid),"SKIPTIME"):
            self.default_skip_time = config["DEVICE"+str(devid)].getboolean("SKIPTIME")
        self.skip_time = self.default_skip_time
        self.forceoff = True
        if config.has_option("DEVICE"+str(devid),"FORCEOFF"):
            self.forceoff = config["DEVICE"+str(devid)].getboolean("FORCEOFF")
        self.ignoremode = False
        if config.has_option("DEVICE"+str(devid),"IGNOREMODE"):
            self.ignoremode = config["DEVICE"+str(devid)].getboolean("IGNOREMODE")
        if config.has_option("DEVICE"+str(devid),"NAME"):
            self.name = config["DEVICE"+str(devid)]["NAME"]
        self.icon = None
        if config.has_option("DEVICE"+str(devid),"ICON"):
            self.icon = config["DEVICE"+str(devid)]["ICON"]

    def run(self, color, priority):
        if self.success:
            return True
        if not self.skip_time:
            self.success = True
            debug.write("Device ({}) {} skipped due to actual time."
                        .format(self.device_type, self.device), 0)
            return True
        if color == LIGHT_SKIP:
            self.success = True
            return True
        if not self.ignoremode:
            if not self.auto_mode and self.request_auto_mode and not self.reset_mode:
                # AUTO mode request on MANUAL device
                debug.write("{} device {} is set in MANUAL mode, skipping."
                            .format(self.device_type, self.device), 0)
                self.success = True
                return True
            if self.auto_mode and not self.request_auto_mode and not self.reset_mode:
                debug.write("{} device {} set to MANUAL mode."
                            .format(self.device_type, self.device), 0)
                self.auto_mode = False
            if self.reset_mode:
                if not self.auto_mode:
                    debug.write("{} device {} set back to AUTO mode."
                                .format(self.device_type, self.device), 0)
                self.auto_mode = True
                self.reset_mode = False
        else:
            debug.write("Skipping mode evaluation for {} device {}."
                        .format(self.device_type, self.device), 0)
        if self.priority > priority:
            debug.write("{} device {} is set with higher priority ({}), skipping."
                                  .format(self.device_type, self.device, self.priority), 0)
            self.success = True
            return True
        if priority == 3:
            self.priority = 1
        else:
            self.priority = priority
        if self.state == color and color != self.convert(LIGHT_OFF):
            self.success = True
            debug.write("Device ({}) {} is already of the requested state, skipping."
                        .format(self.device_type, self.device), 0)
            return True
        if self.state == color and color == self.convert(LIGHT_OFF) and not self.forceoff:
            self.success = True
            debug.write("Device ({}) {} is already off and forcing-off disabled, skipping."
                        .format(self.device_type, self.device), 0)
            return True
        return self.color(color, priority)

    def convert(self, color):
        if self.color_type is None:
            debug.write("Device {} must declare a color type. Quitting.",2)
            quit()
        return convert_color(color, self.color_type)

    def reinit(self):
        """ Prepares the device for a future request """
        self.success = False
        self.skip_time = self.default_skip_time
        return

    def get_state(self):
        """ Getter for the actual color """
        return self.state

    def set_skip_time(self):
        self.skip_time = True
        return

    def descriptions(self):
        """ Getter for the device description """
        return self.description

    def disconnect(self):
        """ Disconnects the device """
        pass
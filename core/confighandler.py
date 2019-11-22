#!/usr/bin/env python3
'''
    File name: confighandler.py
    Author: Maxime Bergeron
    Date last modified: 19/11/2019
    Python Version: 3.5

    The configuration file handler. Adds functions that do not 
    exist yet in configparser
'''

import datetime
from configparser import ConfigParser
from core.common import *


class ConfigHandler(ConfigParser):
    def __init__(self, subsection=None, *args, **kwargs):
        self.subsection = subsection
        super().__init__(*args, **kwargs)
        self.load_config()

    def __getitem__(self, element):
        if self.subsection is not None:
            return super().__getitem__(self.subsection).__getitem__(element)
        return super().__getitem__(element)

    @classmethod
    def set_section(cls, subsection=None, device=None):
        """ Returns another instance of class that points directly to the subsection subsection """
        if device is not None:
            subsection = "DEVICE" + str(device)
        return cls(subsection)

    def get_value(self, element, a_type=str, parent=None):
        """ Gets a a_type type value from the config for element value. Parent allows going back to another section (reverses the set_section() function) """
        if element is None:
            return self
        if a_type == str:
            return self[element]
        elif a_type == int:
            if parent is not None:
                return self.getint(parent, element)
            else:
                return int(self.get(section=self.subsection, option=element))
        elif a_type == bool:
            if parent is not None:
                return self.getboolean(parent, element)
            else:
                return self.get(section=self.subsection, option=element) in [True, "True", "true"]
        elif a_type == "hours":
            return datetime.datetime.strptime(self.get(section=self.subsection, option=element), '%H:%M').time()

    def dev_has_option(self, element):
        return self.has_option(self.subsection, element)

    def get_device(self, devid, element):
        return self["DEVICE" + str(devid)][element]

    def load_config(self):
        self.read('home.ini')

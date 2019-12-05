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
import os
import xml.etree.ElementTree as ET
from argparse import ArgumentParser, RawTextHelpFormatter
from configparser import ConfigParser

CORE_DIR = os.path.dirname(os.path.abspath(__file__))


class ConfigHandler(ConfigParser):
    def __init__(self, subsection=None, *args, **kwargs):
        self.subsection = subsection
        self.configurables = None
        try:
            super().__init__(*args, **kwargs)
        except TypeError:
            super(ConfigHandler, self).__init__(*args, **kwargs)
        self.load_config()

    def __getitem__(self, element):
        if self.subsection is not None:
            try:
                return super().__getitem__(self.subsection).__getitem__(element)
            except TypeError:
                return super(ConfigHandler, self).__getitem__(self.subsection).__getitem__(element)
        try:
            return super().__getitem__(element)
        except TypeError:
            return super(ConfigHandler, self).__getitem__(element)

    @classmethod
    def set_section(cls, subsection=None, device=None):
        """ Returns another instance of class """
        """ that points directly to the subsection subsection """
        if device is not None:
            subsection = "DEVICE" + str(device)
        return cls(subsection)

    def get_value(self, element, a_type=str, parent=None):
        """ Gets a a_type type value from the config for element value. """
        """ Parent allows going back to another section (reverses the set """
        """ _section() function) """
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
        self.read(os.path.join(CORE_DIR, '../home.ini'))
        self.configurables = ET.parse(os.path.join(
            CORE_DIR, 'configurables.xml')).getroot()

    def get_arguments(self):
        parser = ArgumentParser(description='Home server manager script',
                                formatter_class=RawTextHelpFormatter)

        for arg in self.configurables.iter('argument'):
            _name = arg.attrib["name"]
            if arg.attrib["name"] != "hexvalues":
                _name = "--" + _name
            _help = arg.find("description").text
            if _help is None:
                _help = arg.find("description").find("tl").text
            if arg.find("type").text == "str":
                parser.add_argument(_name,
                                    metavar=arg.find("metavar").text,
                                    type=str,
                                    default=arg.find("default").text or None,
                                    nargs=arg.find("nargs").text,
                                    help=_help)
            elif arg.find("type").text == "bool":
                parser.add_argument(_name,
                                    default=arg.find("default").text in [
                                        "True", "true"],
                                    action=arg.find("action").text,
                                    help=_help)
            elif arg.find("type").text == "int":
                parser.add_argument(_name,
                                    metavar=arg.find("metavar").text,
                                    type=int,
                                    default=arg.find("default").text or None,
                                    nargs=arg.find("nargs").text,
                                    help=_help)

        from core.common import getDevices
        for _dev in getDevices(True):
            parser.add_argument('--' + _dev, type=str, nargs="*",
                                help='Change {} states only'.format(_dev))

        return parser.parse_args()

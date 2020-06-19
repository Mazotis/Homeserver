#!/usr/bin/env python3
'''
    File name: confighandler.py
    Author: Maxime Bergeron
    Date last modified: 20/05/2020
    Python Version: 3.7

    The configuration file handler. Adds functions that do not
    exist yet in configparser
'''

import core.common as common
import datetime
import os
import re
import socket
import sys
import xml.etree.ElementTree as ET
from argparse import ArgumentParser, RawTextHelpFormatter
from configparser import ConfigParser, NoSectionError, MissingSectionHeaderError

CORE_DIR = os.path.dirname(os.path.abspath(__file__))


class ConfigHandler(ConfigParser):
    has_imported_config = False

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
            except KeyError:
                return self.get_configure_prompt(section=self.subsection, element=element)
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
        try:
            if element is None:
                return self
            if a_type == str:
                if parent is not None:
                    return self.get(section=parent, option=element)
                else:
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
        except NoSectionError as ex:
            return self.get_configure_prompt(exception=ex)

    def dev_has_option(self, element):
        return self.has_option(self.subsection, element)

    def get_device(self, devid, element):
        return self["DEVICE" + str(devid)][element]

    def load_config(self):
        # TODO Is there a more elegant way to handle this arg sooner, before any
        # call to the config files?
        self.configurables = ET.parse(os.path.join(
                CORE_DIR, 'configurables.xml')).getroot()
        if "--init-from" in sys.argv and not ConfigHandler.has_imported_config:
            self.import_config_from_server()
        try:
            ds = self.read(os.path.join(CORE_DIR, '../home.ini'))
        except MissingSectionHeaderError as ex:
            return self.get_configure_prompt(exception=ex)
        if len(ds) != 1:
            self.configure_prompt()
            return

    def import_config_from_server(self):
        has_faulty_config = False
        args = self.get_arguments(_ignore_devices=True)

        print("Fetching configuration file from server daemon.")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((args.init_from.split(":")[0], int(
                       args.init_from.split(":")[1])))
            common.send_msg(s, "getconfig".encode('utf-8'))
            config_data = common.recv_msg(s)
            if config_data:
                if os.path.isfile(CORE_DIR + "/../home.old"):
                    os.remove(CORE_DIR + "/../home.old")
                if os.path.isfile(CORE_DIR + "/../home.ini"):
                    os.rename(CORE_DIR + "/../home.ini",
                              CORE_DIR + "/../home.old")
                with open(CORE_DIR + '/../home.ini', 'w') as _f:
                    config_data.write(_f)
                    print("Configuration file updated from server")
        except socket.timeout:
            print("Server failed to answer request. Quitting.")
            has_faulty_config = True
        except ConnectionRefusedError:
            print("Server is unavailable. Quitting.")
            has_faulty_config = True
        except Exception as ex:
            print("Unhandled exception: {}".format(ex))
            has_faulty_config = True
        finally:
            s.close()
            ConfigHandler.has_imported_config = True
            if has_faulty_config:
                sys.exit()

    def get_arguments(self, _ignore_devices=False):
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

        if not _ignore_devices:
            from core.common import getDevices
            for _dev in getDevices(True):
                parser.add_argument('--' + _dev, type=str, nargs="*",
                                    help='Change {} states only'.format(_dev))

        return parser.parse_args()

    def get_configure_prompt(self, section=None, element=None, exception=None):
        print("* Config file has invalid sections. Running configuration tool...")
        if exception is not None:
            print("* Got exception: {}".format(exception))
        if section is not None and element is not None:
            print("* Missing section '{}' and/or element '{}".format(section, element))
        self.configure_prompt()
        return

    def configure_prompt(self):
        _for_devices = False
        print("************************")
        print("Homeserver configuration")
        print("************************")
        # HOME.INI CREATION
        # TODO Work on navigation around config options
        if os.path.exists(CORE_DIR + '/../home.ini'):
            if input("home.ini already exists. Do you wish to overwrite it? <N/y> ") == "y":
                with open(CORE_DIR + '/../home.ini', 'w+'):
                    pass
                print("* Created blank home.ini file.")
            else:
                self.read(os.path.join(CORE_DIR, '/../home.ini'))
                if input("Do you wish to skip to device configuration? <N/y>") == "y":
                    _for_devices = True

        else:
            with open(CORE_DIR + '/../home.ini', 'w+'):
                pass
            try:
                self.read(os.path.join(CORE_DIR, '/../home.ini'))
            except MissingSectionHeaderError:
                return self.get_configure_prompt()

        module_list = []
        if not _for_devices:
            import fcntl
            import socket
            import struct
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                ds = socket.inet_ntoa(fcntl.ioctl(
                    s.fileno(),
                    0x8915,  # SIOCGIFADDR
                    struct.pack('256s', bytes("wlan0", 'utf-8'))
                )[20:24])
            except OSError:
                ds = None
            s.close()

            # SERVER
            self.set_config_entry("SERVER", "HOST", expected_value=ds)
            self.module_config_prompt("SERVER")

            print("\n*******")
            print("Modules")
            print("*******")
            print("* Modules bring new functions to Homeserver. They can be disabled without affecting the Homeserver main functions.")
            for _mod in self.configurables.find("modules").findall("module"):
                print("\n* {}".format(_mod.attrib["name"]))
                print("* {}".format(_mod.find("description").text))
                if _mod.find("default").text == "enabled":
                    if input("Enable the {} module? <Y/n>".format(_mod.attrib["name"])) != "n":
                        module_list.append(_mod.attrib["name"])
                else:
                    if input("Enable the {} module? <N/y>".format(_mod.attrib["name"])) == "y":
                        module_list.append(_mod.attrib["name"])

            enabled_modules = ",".join(module_list)
            print("* Enabled modules: {}".format(enabled_modules))
            self.set_config_entry("SERVER", "MODULES",
                                  expected_value=enabled_modules, silent=True)

            if "webserver" in module_list:
                self.set_config_entry(
                    "SERVER", "WEBSERVER_PORT", expected_value="8080")

            if "ifttt" in module_list or "dialogflow" in module_list:
                self.set_config_entry(
                    "SERVER", "VOICE_SERVER_PORT", expected_value="2345")

            if "ifttt" in module_list and "dialogflow" in module_list:
                print(
                    "* Error: you cannot enable IFTTT and DIALOGFLOW modules at the same time. Quitting.")
                quit()

            # USERS
            if "webserver" in module_list or "detector" in module_list:
                print("\n*****")
                print("Users")
                print("*****\n")
                print("* Known users for the homeserver. Allows to link devices IPs with their users, or '_' if user has no associated device.\n* This is required to authenticate some user to the webserver when security is set to 'restrictive'\n* Also shows the user's first name in the detector module")
                _users = ""
                _ips = ""
                while True:
                    if input("Do you wish to create a new user? <N/y>") == "y":
                        _us1 = input("User full name: ")
                        print(
                            "* Tracked devices local LAN IP for user {}. Comma-separated, if there are more than one (for example: 192.168.1.2,192.168.1.3...)")
                        _us2 = input("Tracked devices IP list: ")
                        self.set_config_entry(
                            "USERS", _us1, expected_value=_us2, silent=True)
                    else:
                        break
            else:
                self.add_section("USERS")

            print("\n***************")
            print("Module warnings")
            print("***************")
            if "detector" in module_list:
                print(
                    "* [DETECTOR] Detector events can be configured later from the webserver or in the home.ini file directly")

            if "ifttt" in module_list:
                print(
                    "* [IFTTT] Note that you need to provide a key and cert file to enable SSL (https) on your webserver")
                print(
                    "* [IFTTT] Action presets can be configured later from the webserver or in the home.ini file directly")

            if "dialogflow" in module_list:
                print(
                    "* [DIALOGFLOW] You need to provide a key and cert file to enable SSL, as dialogflow only accepts HTTPS.")
                print(
                    "* [DIALOGFLOW] Dialogflow action presets can be configured later from the webserver or in the home.ini file directly")

            for _mod in module_list:
                self.module_config_prompt(_mod)

            if "backup" in module_list:
                print("\n***************************")
                print("Folders and files to backup")
                print("***************************")
                _cnt = 0
                while True:
                    if input("Do you wish to create a new backup setting? You might want to wait after device configuration to do that, as you need all the devices #. <N/y>") == "y":
                        _bk1 = input("Client (source) device #: ")
                        _bk2 = input(
                            "Try to power-on client before backup (True/False): ")
                        _bk3 = input(
                            "Folders to backup, comma-separated (example: /home/pi/documents,/home/pi/pictures...): ")
                        _bk4 = input(
                            "Destination folder on backup server (example: /home/backup/device1): ")
                        _bk5 = input(
                            "Sync backup. Delete files on server that are also deleted on client (True/False): ")

                        self.set_config_entry(
                            "BACKUP", "CLIENT" + str(_cnt), expected_value=_bk1, silent=True)
                        self.set_config_entry(
                            "BACKUP", "CLIENT" + str(_cnt) + "_FORCE_ON", expected_value=_bk2, silent=True)
                        self.set_config_entry(
                            "BACKUP", "CLIENT" + str(_cnt) + "_FOLDERS", expected_value=_bk3, silent=True)
                        self.set_config_entry(
                            "BACKUP", "CLIENT" + str(_cnt) + "_DESTINATION", expected_value=_bk4, silent=True)
                        self.set_config_entry(
                            "BACKUP", "CLIENT" + str(_cnt) + "_DELETE", expected_value=_bk5, silent=True)
                        _cnt = _cnt + 1
                    else:
                        break

            print("\n*******")
            print("Presets")
            print("*******")
            print("* Presets are predefined state changes for your devices")
            self.set_config_entry("PRESETS", "AUTOMATIC_MODE")
            print(
                "* Presets can be configured later from the webserver or in the home.ini file directly")

            if self.get_value("TCP_START_HOUR", parent="SERVER") != "":
                print("\n**************************")
                print("TCP socket request presets")
                print("**************************")
                self.set_config_entry("TCP-PRESETS", "AUTOMATIC_MODE")
                print(
                    "TCP socket request presets can be configured later from the webserver or in the home.ini file directly")
        else:
            # _for_devices
            for _mod in self.configurables.find("modules").findall("module"):
                if self.has_section(_mod.attrib["name"].upper()):
                    module_list.append(_mod.attrib["name"])

        print("\n*********************")
        print("DEVICES configuration")
        print("*********************")
        # room groups and priority groups
        _devices = []
        _devices_desc = []
        _known_groups = []

        _cnt = 0
        _groups = []
        while True:
            if self.has_section("DEVICE" + str(_cnt)):
                if self.has_option("DEVICE" + str(_cnt), "GROUP"):
                    _grps = self.get_value(
                        "GROUP", parent="DEVICE" + str(_cnt))
                    for _grp in _grps.split(","):
                        _known_groups.append(_grp)
            else:
                break
            _cnt = _cnt + 1

        _room_groups = []
        if self.has_option("WEBSERVER", "ROOM_GROUPS"):
            _roomg = self.get_value("ROOM_GROUPS", parent="WEBSERVER")
            if _roomg is not None:
                _room_groups = _roomg.split(",")

        _priority_groups = []
        if self.has_option("IFTTT", "PRIORITY_GROUPS"):
            _priog = self.get_value("PRIORITY_GROUPS", parent="IFTTT")
            if _priog is not None:
                _prioritary_groups = _priog.split(",")

        for _sct in self.configurables.find("devices").findall("device"):
            _devices.append(_sct.attrib["name"])
            _devices_desc.append(_sct.find("description").text)

        _cnt = 0
        while True:
            if input("\n[DEVICE{}] Do you wish to change device configuration or add new device <N/y> ".format(_cnt)) == "y":
                print("\nAvailable devices")
                print("*****************\n")
                for _dev, _desc in zip(_devices, _devices_desc):
                    print("* {} - {}".format(_dev, _desc))

                if self.has_option("DEVICE" + str(_cnt), "TYPE"):
                    _dtype = self.get_value(
                        "TYPE", parent="DEVICE" + str(_cnt))
                    _name = self.get_value("NAME", parent="DEVICE" + str(_cnt))
                    print("\nDEVICE{} is called: '{}' ({})".format(
                        _cnt, _name, _dtype))
                    if input("Do you wish to reconfigure this device? <Y/n> ") == "n":
                        self.remove_section("DEVICE" + str(_cnt))
                        _dtype = input(
                            "\n[DEVICE{}] What is the new device type? ".format(_cnt))
                else:
                    _dtype = input(
                        "\n[DEVICE{}] What is the new device type? ".format(_cnt))
                if _dtype not in _devices:
                    print(
                        "Device type '{}' does not exist. Choose from the Available devices list".format(_dtype))
                    continue
                if not self.has_section("DEVICE" + str(_cnt)):
                    self.add_section("DEVICE" + str(_cnt))
                self.set("DEVICE" + str(_cnt), "TYPE", _dtype)
                print("* Getting device required configurations...")
                for _sct in self.configurables.find("devices").findall("device"):
                    if _sct.attrib["name"] == _dtype:
                        print("\nDevice requirements")
                        print("*******************")
                        print("* {}\n".format(_sct.find("requirements").text))
                        for _entry in _sct.find("configs").text.split(","):
                            if _entry == "GROUP":
                                print(
                                    "\n* Known device groups: {}".format(", ".join(_known_groups)))

                            _value = None
                            if self.has_option("DEVICE" + str(_cnt), _entry):
                                _value = self.get_value(
                                    _entry, parent="DEVICE" + str(_cnt))

                            self.set_config_entry(
                                "DEVICE" + str(_cnt), _entry, expected_value=_value)
                            if _entry == "GROUP":
                                try:
                                    for _grp in self.get_value("GROUP", parent="DEVICE" + str(_cnt)).split(","):
                                        if _grp not in _known_groups:
                                            _known_groups.append(_grp)
                                            if input("Is '{}' a room group? Room groups are more easily accessible in the web UI. <N/y> ".format(_grp)) == "y":
                                                _room_groups.append(_grp)
                                            if input("Is '{}' a priority group? When a priority group is called in voice commands, the device state is changed without considering its mode. <N/y> ".format(_grp)) == "y":
                                                _priority_groups.append(_grp)
                                except AttributeError:
                                    pass
                        if input("Do you wish to see advanced settings options? <N/y> ") == "y":
                            print("* Getting device optional configurations...")
                            for _entry in _sct.find("optionals").text.split(","):
                                _value = None
                                if self.has_option("DEVICE" + str(_cnt), _entry):
                                    _value = self.get_value(
                                        _entry, parent="DEVICE" + str(_cnt))
                                self.set_config_entry(
                                    "DEVICE" + str(_cnt), _entry, expected_value=_value)
            else:
                if not self.has_section("DEVICE" + str(_cnt)):
                    break
            _cnt = _cnt + 1

        if len(_room_groups) > 0 and 'webserver' in module_list:
            self.set_config_entry(
                "WEBSERVER", "ROOM_GROUPS", expected_value=",".join(_room_groups), silent=True)
        if len(_priority_groups) > 0 and 'ifttt' in module_list:
            self.set_config_entry("IFTTT", "PRIORITY_GROUPS", expected_value=",".join(
                _priority_groups), silent=True)
        with open(CORE_DIR + '/../home.ini', 'w') as _f:
            self.write(_f)
            print("\n* Configuration written to file!")

        quit()

    def module_config_prompt(self, module):
        print("\n{}".format("*" * (len(module) + 7)))
        print("{} module".format(module.upper()))
        print("{}".format("*" * (len(module) + 7)))
        for _sct in self.configurables.find("configentries").findall("section"):
            if _sct.attrib["name"].lower() == module.lower():
                for _ent in _sct.findall("config"):
                    try:
                        if _ent.attrib["manual"] == "True":
                            continue
                    except KeyError:
                        pass
                    try:
                        if _ent.attrib["silent"] == "True":
                            self.set_config_entry(
                                module.upper(), _ent.attrib["name"].upper(), silent=True)
                    except KeyError:
                        self.set_config_entry(
                            module.upper(), _ent.attrib["name"].upper())

    def set_config_entry(self, section, entry, expected_value=None, silent=False):
        if expected_value is None:
            for _sct in self.configurables.find("configentries").findall("section"):
                if _sct.attrib["name"] == section:
                    for _ent in _sct.findall("config"):
                        if _ent.attrib["name"] == entry:
                            expected_value = _ent.find("default").text
                            for _dep in _ent.findall("depends"):
                                if _dep.attrib["being"] == "True":
                                    if self.get_value(_dep.attrib["on"].upper(), parent=section) not in ["True", "true", True]:
                                        print(
                                            "* Skipping non-required option: {}".format(entry))
                                        self.set(section.upper(),
                                                 entry.upper(), "")
                                        return
                                elif _dep.attrib["being"]:
                                    if self.get_value(_dep.attrib["on"].upper(), parent=section) != _dep.attrib["being"]:
                                        print(
                                            "* Skipping non-required option: {}".format(entry))
                                        self.set(section.upper(),
                                                 entry.upper(), "")
                                        return
        if silent:
            _val = expected_value
        else:
            _val = self.get_input_contents(section, entry, expected_value)
        if _val is None:
            _val = ""
        if not self.has_section(section):
            self.add_section(section)
        self.set(section.upper(), entry.upper(), _val)

    def get_input_contents(self, section, entry, expected_value):
        if section[0:6] == "DEVICE":
            section = "DEVICE"
        for _sct in self.configurables.find("configentries").findall("section"):
            if _sct.attrib["name"] == section:
                for _ent in _sct.findall("config"):
                    if _ent.attrib["name"] == entry:
                        print("\n* {}".format(_ent.find("description").text))
                        if expected_value is None:
                            expected_value = ""
                        if self.has_option(section, entry):
                            _default = self.get_value(
                                entry, parent=section)
                            if _default == "":
                                _default = expected_value
                        else:
                            _default = expected_value
                        while True:
                            _in = input(
                                "{} [{}]: ".format(_ent.find("fulltype").text, _default))
                            if _in == "":
                                _in = _default
                            try:
                                _regex = _ent.find("regex").text
                                if not re.search(_regex, _in):
                                    print("\n* Invalid value: {}".format(_in))
                                    continue
                            except AttributeError:
                                pass
                            break
                        return _in
        return None

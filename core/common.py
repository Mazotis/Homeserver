#!/usr/bin/env python3
'''
    File name: common.py
    Author: Maxime Bergeron
    Date last modified: 07/01/2020
    Python Version: 3.5

    Commonly shared variables and functions
'''

import datetime
import gettext
import glob
import os
import pickle
import random
import socket
import struct
import sys
from os.path import dirname, basename, isfile
from core.confighandler import ConfigHandler


# CONSTANTS
DEVICE_STANDBY = "-2"
DEVICE_SKIP = "-1"
DEVICE_OFF = "0"
DEVICE_ON = "1"
DEVICE_DISABLED = "X"
DEVICE_INFERRED_OFF = "*0"
DEVICE_INFERRED_ON = "*1"
DEVICE_TOGGLE = "T"

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(CORE_DIR + "/../VERSION") as f:
    VERSION = f.read()

###


class RequestAborted(Exception):
    # Does nothing for now
    pass


def send_msg(sock, msg):
    # TODO - secure hashing
    msg = pickle.dumps(msg)
    msg = struct.pack('>I', len(msg)) + msg
    sock.sendall(msg)


def recv_msg(sock):
    raw_msglen = recvall(sock, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack('>I', raw_msglen)[0]
    return recvall(sock, msglen, unpickle=True)


def recvall(sock, n, unpickle=False):
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    if unpickle:
        return pickle.loads(data)
    else:
        return data


def getConfigHandler(renew=False):
    if renew:
        HOMECONFIG = ConfigHandler()
    try:
        HOMECONFIG
    except NameError:
        HOMECONFIG = ConfigHandler()
        pass
    return HOMECONFIG


HOMECONFIG = getConfigHandler()
DEBUG_LOCK = False


class NewRequestException(Exception):
    def __init__(self):
        # TODO - is there anything else to cleanup here ?
        debug.write("Aborting state change due to new request", 3)

    def __str__(self):
        return "Aborting state change due to new request"


class DebugLog(object):
    def __init__(self):
        """ Handles debug logging """
        self.config = HOMECONFIG.set_section("SERVER")
        self.LEVELS = {-1: "UNKNOWN", 0: "DEBUG", 1: "ERROR", 2: "FATAL", 3: "WARNING"}
        self.COLOR_LEVELS = {-1: "", 0: "\033[93m", 1: "\033[91m", 2: "\033[41m", 3:"\033[43m"}
        self.device_colors = {}
        self.debug_enabled = self.config.get_value("ENABLE_DEBUG", bool)
        self.journaling_enabled = self.config.get_value('JOURNALING', bool)
        self._lock_socket = None

    def enable_debug(self):
        if self.get_set_lock(True) and self.debug_enabled and self.journaling_enabled:
            # Server not yet initialized. Create log files
            for n in reversed(range(0, self.config.get_value("MAX_DEBUG_FILES", int))):
                if os.path.isfile(get_path_from_config(self.config['JOURNAL_DIR']) + "/home." + str(n) + ".log"):
                    os.remove(
                        get_path_from_config(self.config['JOURNAL_DIR']) + "/home." + str(n) + ".log")
                if os.path.isfile(get_path_from_config(self.config['JOURNAL_DIR']) + "/home." + str(n - 1) + ".log"):
                    os.rename(get_path_from_config(self.config['JOURNAL_DIR']) + "/home." + str(n - 1) + ".log",
                              get_path_from_config(self.config['JOURNAL_DIR']) + "/home." + str(n) + ".log")
            self.write("Starting debug logger", 0)

    def get_set_lock(self, get=False):
        self._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        try:
            self._lock_socket.bind('\0homeserver')
            if get:
                return True
        except socket.error:
            if get:
                return False
            else:
                print("Server is already running. Shutting down.")
                sys.exit()

    def write(self, msg, level=-1, devicetype=None, prefix=""):
        if self.debug_enabled:
            if devicetype is not None:
                if devicetype in self.device_colors.keys():
                    _dcolor = self.device_colors[devicetype]
                else:
                    _dcolor = "\033[38;5;" + \
                        str(random.randint(100, 230)) + "m"
                    self.device_colors[devicetype] = _dcolor

                _cdebugtext = "({}) - [{}{}\033[0m] {}{}[{}] {}\033[0m".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                                               self.COLOR_LEVELS[level], self.LEVELS[level], prefix, _dcolor, devicetype, msg)
                _debugtext = "({}) - [{}] {}[{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                            self.LEVELS[level], prefix, devicetype, msg)
            else:
                _cdebugtext = "({}) - [{}{}\033[0m] {}{}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                                 self.COLOR_LEVELS[level], self.LEVELS[level], prefix, msg)
                _debugtext = "({}) - [{}] {}{}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                       self.LEVELS[level], prefix, msg)
            if not DEBUG_LOCK:
                print(_cdebugtext)
            if self.journaling_enabled:
                try:
                    with open(get_path_from_config(self.config['JOURNAL_DIR']) + "/home.0.log", "a+") as jfile:
                        jfile.write(_debugtext + "\n")
                except IOError:
                    print("* Directory {} does not exist. Running configuration tool...".format(
                        get_path_from_config(self.config['JOURNAL_DIR'])))
                    self.config.configure_prompt()
                    quit()


class LanguageHandler(object):
    def __init__(self):
        self.config = HOMECONFIG.set_section("SERVER")
        self.language = self.config['LANGUAGE']
        self.installed_language = None

    def getLanguage(self):
        return self.language

    def installLanguage(self):
        if self.installed_language is None:
            if language.getLanguage() == "fr":
                lang = gettext.translation(
                    'base', localedir=os.path.join(CORE_DIR, '../locales'), languages=['fr'])
                lang.install()
            else:
                lang = gettext.translation(
                    'base', localedir=os.path.join(CORE_DIR, '../locales'), languages=['en'])
                lang.install()
        return lang.gettext


decora = None
meross = None
debug = DebugLog()
language = LanguageHandler()
_ = language.installLanguage()


def getDevices(to_lower=False):
    """ Getter for available device modules, same as __init__ """
    modules = glob.glob(dirname(__file__) + "/../devices/*.py")
    devices = [basename(f)[:-3] for f in modules if isfile(f)
               and not f.endswith('__init__.py')]
    if to_lower:
        return [x.lower() for x in devices]
    else:
        return devices


def getModules():
    """ Getter for available server modules, same as __init__ """
    modules = glob.glob(dirname(__file__) + "/../modules/*.py")
    devices = [basename(f)[:-3] for f in modules if isfile(f)]
    return devices

def get_path_from_config(path):
    return path.replace("BASEDIR", CORE_DIR + "/..")
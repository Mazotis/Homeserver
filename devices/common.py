#!/usr/bin/env python3
'''
    File name: common.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    Commonly shared variables
'''

import ast
import os
import glob
import configparser
import datetime
import random
import socket
import sys
import time
from os.path import dirname, basename, isfile

# CONSTANTS
LIGHT_SKIP = "-1"
LIGHT_OFF = "0"
LIGHT_ON = "1"
###

class DebugLog(object):
    def __init__(self):
        """ Handles debug logging """
        self.config = configparser.ConfigParser()
        self.config.read('play.ini')
        self.LEVELS = {0: "DEBUG", 1: "ERROR", 2: "FATAL"}
        self.COLOR_LEVELS = {0: "\033[93m", 1: "\033[91m", 2: "\033[41m"}
        self.device_colors = {}
        self.debug_enabled = self.config['SERVER'].getboolean("ENABLE_DEBUG")
        self._lock_socket = None

    def enable_debug(self):
        if self.get_set_lock(True) and self.debug_enabled:
            # Server not yet initialized. Create log files
            for n in reversed(range(0, self.config['SERVER'].getint("MAX_DEBUG_FILES"))):
                if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play." + str(n) + ".log"):
                    os.remove(self.config['SERVER']['JOURNAL_DIR'] + "/play." + str(n) + ".log")
                if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play." + str(n-1) +".log"):
                    os.rename(self.config['SERVER']['JOURNAL_DIR'] + "/play." + str(n-1) + ".log",
                              self.config['SERVER']['JOURNAL_DIR'] + "/play." + str(n) + ".log")

    def get_set_lock(self, get=False):
        self._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        try:
            self._lock_socket.bind('\0playserver')
            if get:
                return True
        except socket.error:
            if get:
                return False
            else:
                print("Server is already running. Shutting down.")
                sys.exit()

    def write(self, msg, level, devicetype = None):
        if self.debug_enabled:
            if devicetype is not None:
                if devicetype in self.device_colors.keys():
                    _dcolor = self.device_colors[devicetype]
                else:
                    _dcolor = "\033[38;5;" + str(random.randint(100,230)) + "m"
                    self.device_colors[devicetype] = _dcolor

                _cdebugtext = "({}) - [{}{}\033[0m] {}[{}] {}\033[0m".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                                self.COLOR_LEVELS[level], self.LEVELS[level], _dcolor, devicetype, msg)
            else:
                _cdebugtext = "({}) - [{}{}\033[0m] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                                self.COLOR_LEVELS[level], self.LEVELS[level], msg)
            _debugtext = "({}) - [{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                                self.LEVELS[level], msg)
            print(_cdebugtext)
            if ast.literal_eval(self.config['SERVER']['JOURNALING']):
                with open(self.config['SERVER']['JOURNAL_DIR'] + "/play.0.log", "a") as jfile:
                    jfile.write(_debugtext + "\n")

decora = None
meross = None
debug = DebugLog()

def getDevices():
    """ Getter for available device modules, same as __init__ """
    modules = glob.glob(dirname(__file__)+"/*.py")
    return [basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py') 
            and not f.endswith('common.py')]

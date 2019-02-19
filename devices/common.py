#!/usr/bin/env python3
'''
    File name: common.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    Commonly shared variables
'''

import os
import glob
import configparser
import datetime
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
        #TODO Dynamic history limits
        if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play.0.log"):
            if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play.1.log"):
                if os.path.isfile(self.config['SERVER']['JOURNAL_DIR'] + "/play.2.log"):
                    os.remove(self.config['SERVER']['JOURNAL_DIR'] + "/play.2.log")
                os.rename(self.config['SERVER']['JOURNAL_DIR'] + "/play.1.log",
                          self.config['SERVER']['JOURNAL_DIR'] + "/play.2.log")
            os.rename(self.config['SERVER']['JOURNAL_DIR'] + "/play.0.log",
                      self.config['SERVER']['JOURNAL_DIR'] + "/play.1.log")

    def write(self, msg, level):
        debugtext = "({}) - [{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                            self.LEVELS[level], msg)
        print(debugtext)
        if self.config['SERVER']['JOURNALING']:
            with open(self.config['SERVER']['JOURNAL_DIR'] + "/play.0.log", "a") as jfile:
                jfile.write(debugtext + "\n")


global debug 
global decora
global meross
decora = None
meross = None
debug = DebugLog()

def getDevices():
	""" Getter for available device modules, same as __init__ """
	modules = glob.glob(dirname(__file__)+"/*.py")
	return [basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py') 
			and not f.endswith('common.py')]
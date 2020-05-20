#!/usr/bin/env python3
'''
    File name: updater.py
    Author: Maxime Bergeron
    Date last modified: 20/05/2020
    Python Version: 3.7

    The updater module for the homeserver
'''

import subprocess
import sys
from core.common import *
from threading import Thread, Event
from urllib.error import HTTPError
from urllib.request import urlopen

VERSION_FILE = "https://raw.githubusercontent.com/Mazotis/Homeserver/master/VERSION"


def check_for_updates(with_pip=False):
    debug.write("Checking for updates (actual version: {})...".format(
        VERSION), 0, "UPDATER")
    try:
        NEW_VERSION = urlopen(VERSION_FILE).read().decode("UTF-8")
    except HTTPError:
        debug.write(
            "Could not check version with the main Github server.", 1, "UPDATER")
        NEW_VERSION = VERSION
    if VERSION != NEW_VERSION:
        debug.write("A new version ({}) is available".format(
            NEW_VERSION), 0, "UPDATER")
        return True
    else:
        debug.write("Homeserver is up to date.", 0, "UPDATER")

    if with_pip:
        debug.write("Updating required python packages...".format(
            VERSION), 0, "UPDATER")
        _pip = None
        if (sys.version_info > (3, 0)):
            _pip = subprocess.Popen(
                "pip3 install -r requirements.txt", shell=True)
        else:
            _pip = subprocess.Popen(
                "pip install -r requirements.txt", shell=True)
        _pip.wait()
    return False


def run_upgrade(dm):
    debug.write("Fetching new version from git", 0, "UPDATER")
    try:
        _update = subprocess.Popen(
            "cd {}/.. && git fetch --all".format(CORE_DIR), shell=True, stdout=subprocess.PIPE)
        _update.wait()
        _update = subprocess.Popen(
            "cd {}/.. && git reset --hard origin/master".format(CORE_DIR), shell=True, stdout=subprocess.PIPE)
        _update.wait()
    except subprocess.CalledProcessError:
        debug.write(
            "Could not run updater. Make sure you have git-core installed.", 1, "UPDATER")
        return
    debug.write("Restarting the Homeserver main script", 0, "UPDATER")

    if dm is not None:
        dm.shutdown_modules()
    python = sys.executable
    os.execl(python, python, *sys.argv)


class updater(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.stopevent = Event()
        self.dm = dm
        self.init_from_config()

    def run(self):
        if check_for_updates(with_pip=self.config.get_value('UPDATE_PYTHON_PACKAGES', bool)) and self.AUTOMATIC_UPDATE:
            run_upgrade(self.dm)
        last_update = datetime.datetime.now().date()

        while not self.stopevent.is_set():
            actual_time = datetime.datetime.now().hour
            actual_date = datetime.datetime.now().date()

            if self.UPDATER_HOUR >= actual_time and \
                    actual_date != last_update:
                if check_for_updates() and self.AUTOMATIC_UPDATE:
                    run_upgrade(self.dm)
                last_update = actual_date
            self.stopevent.wait(300)
        debug.write("Stopped.", 0, "UPDATER")
        return

    def stop(self):
        debug.write("Stopping.", 0, "UPDATER")
        self.stopevent.set()

    def init_from_config(self):
        self.config = getConfigHandler().set_section("UPDATER")
        self.UPDATER_HOUR = self.config.get_value('UPDATER_HOUR', int)
        self.AUTOMATIC_UPDATE = self.config.get_value('AUTOMATIC_UPDATE', bool)

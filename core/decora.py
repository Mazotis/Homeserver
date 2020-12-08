#!/usr/bin/env python3
'''
    File name: Decora.py
    Author: Maxime Bergeron
    Date last modified: 14/07/2020
    Python Version: 3.7

    The Decora device handler. Allows connections to MyLeviton. Not a device per-se.
'''

from core.common import *
from decora_wifi import DecoraWiFiSession
from decora_wifi.models.person import Person
from decora_wifi.models.residential_account import ResidentialAccount
from decora_wifi.models.residence import Residence
from threading import Timer, Lock


class Decora(object):
    decora_lock = Lock()

    def __init__(self, devid):
        # TODO Support multiple MyLeviton accounts at the same time ?
        self.email = getConfigHandler().get_device(devid, "EMAIL")
        self.password = getConfigHandler().get_device(devid, "PASSWORD")
        self.residences = None
        self._connected = False
        self.disabled = False
        self.connect()
        debug.write(
            "Created pseudo-device Decora with account {}.".format(self.email), 0)

    def get_switch(self, name=None):
        try:
            self.session.login(self.email, self.password)
            if self.residences is None:
                self._initialize()
            if name is not None:
                for residence in self.residences:
                    for switch in residence.get_iot_switches():
                        if switch.name == name:
                            return switch
        except ValueError:
            debug.write("Error connecting to Decora servers. Retrying", 1)
            return self.connect()
        return False

    def request(self, name, attribs):
        if not self._connected:
            self.connect()
        self.get_switch(name).update_attributes(attribs)

    def connect(self, name=None):
        with Decora.decora_lock:
            if self._connected:
                self.disconnect()
            try:
                debug.write("Connecting to Decora servers", 0)
                timer = Timer(10, self.failure_handler)
                timer.start()
                self.session = DecoraWiFiSession()
                self.get_switch(name=name)
                self.disabled = False
                timer.cancel()
                debug.write("Connected to Decora", 0)
            except KeyboardInterrupt:
                self.disabled = True
                return
            except Exception as ex:
                # TODO catch all exceptions ?
                debug.write(
                    "Unhandled exception {}. Cannot login to decora account {}, disabling devices .".format(ex, self.email), 1)
                return
            self._connected = True

    def disconnect(self):
        with Decora.decora_lock:
            try:
                Person.logout(self.session)
            except ValueError:
                debug.write(
                    "Error connecting to Decora servers. Skipping disconnection", 1)
            finally:
                self._connected = False

    def failure_handler(self):
        debug.write(
            "Unhandled exception. Cannot login to decora account {}, disabling devices . Press Ctrl+C to ignore.".format(self.email), 1)
        raise KeyboardInterrupt()

    def _initialize(self):
        perms = self.session.user.get_residential_permissions()
        self.residences = []
        for permission in perms:
            if permission.residentialAccountId is not None:
                acct = ResidentialAccount(
                    self.session, permission.residentialAccountId)
                for res in acct.get_residences():
                    self.residences.append(res)
            elif permission.residenceId is not None:
                res = Residence(self.session, permission.residenceId)
                self.residences.append(res)
        for residence in self.residences:
            for switch in residence.get_iot_switches():
                debug.write("Decora account {} got switch: {}".format(
                    self.email, switch.name), 0)

#!/usr/bin/env python3
'''
    File name: Decora.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    The Decora device handler. Allows connections to MyLeviton. Not a device per-se.
'''

from core.common import *
from decora_wifi import DecoraWiFiSession
from decora_wifi.models.person import Person
from decora_wifi.models.residential_account import ResidentialAccount
from decora_wifi.models.residence import Residence
from threading import Timer


class Decora(object):
    def __init__(self, devid):
        # TODO Support multiple MyLeviton accounts at the same time ?
        self.email = HOMECONFIG.get_device(devid, "EMAIL")
        self.password = HOMECONFIG.get_device(devid, "PASSWORD")
        self.residences = None
        self._connected = False
        self.disabled = False
        self.connect()
        debug.write(
            "Created pseudo-device Decora with account {}.".format(self.email), 0)

    def get_switch(self, name=None):
        self.session.login(self.email, self.password)
        if self.residences is None:
            self._initialize()
        if name is not None:
            for residence in self.residences:
                for switch in residence.get_iot_switches():
                    if switch.name == name:
                        return switch
        self.disconnect()
        return False

    def request(self, name, attribs):
        if not self._connected:
            self.connect()
        self.get_switch(name).update_attributes(attribs)

    def connect(self):
        try:
            timer = Timer(10, self.failure_handler)
            timer.start()
            self.session = DecoraWiFiSession()
            self.get_switch()
            self.disabled = False
            timer.cancel()
        except Exception:
            # TODO catch all exceptions ?
            self.failure_handler()
            return
        except KeyboardInterrupt:
            self.disabled = True
            return
        self._connected = True

    def disconnect(self):
        Person.logout(self.session)
        self._connected = False

    def failure_handler(self):
        debug.write(
            "Unhandled exception. Cannot login to decora account {}, disabling devices . Press Ctrl+C to ignore.".format(self.email), 1)

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

#!/usr/bin/env python3
'''
    File name: Decora.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    The Decora device handler. Allows connections to MyLeviton. Not a device per-se.
'''

from decora_wifi import DecoraWiFiSession
from decora_wifi.models.person import Person
from decora_wifi.models.residential_account import ResidentialAccount
from decora_wifi.models.residence import Residence
from core.common import *

class Decora(object):
    def __init__(self, devid, config):
        #TODO Support multiple MyLeviton accounts at the same time ?
        self.email = config["DEVICE"+str(devid)]["EMAIL"]
        self.password = config["DEVICE"+str(devid)]["PASSWORD"]
        self.residences = None
        self._connected = False
        self.disabled = False
        self.connect()
        decora = self
        debug.write("Created pseudo-device Decora with account {}.".format(self.email), 0)

    def get_switch(self, name = None):
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
            self.session = DecoraWiFiSession()
            self.get_switch()
            self.disabled = False
        except:
            #TODO catch all exceptions ?
            debug.write("Cannot login to decora account {}, disabling devices.".format(self.email), 1)
            self.disabled = True
            return
        self._connected = True

    def disconnect(self):
        Person.logout(self.session)
        self._connected = False

    def _initialize(self):
        perms = self.session.user.get_residential_permissions()
        self.residences = []
        for permission in perms:
            if permission.residentialAccountId is not None:
                acct = ResidentialAccount(self.session, permission.residentialAccountId)
                for res in acct.get_residences():
                    self.residences.append(res)
            elif permission.residenceId is not None:
                res = Residence(self.session, permission.residenceId)
                self.residences.append(res)
        for residence in self.residences:
            for switch in residence.get_iot_switches():
                debug.write("Decora account {} got switch: {}".format(self.email, switch.name), 0)
#!/usr/bin/env python3
'''
    File name: texts.py
    Author: Maxime Bergeron
    Date last modified: 01/11/2019
    Python Version: 3.5

    A python text internationalization handler for the webserver
'''

import gettext
from core.common import *

if language.getLanguage() == "fr":
    lang = gettext.translation('base', localedir='locales', languages=['fr'])
    lang.install()
else:
    lang = gettext.translation('base', localedir='locales', languages=['en'])
    lang.install()
_ = lang.gettext


def getTextHTML(textid):
    textDB = {
        "Homeserver control panel": _("Homeserver control panel"),
        "Loading...": _("Loading..."),
        "Updating device status...": _("Updating device status..."),
        "Rooms": _("Rooms"),
        "Devices": _("Devices"),
        "Groups": _("Groups"),
        "No available device groups": _("No available device groups"),
        "Options": _("Options"),
        "Time check feature. Today's start time:": _("Time check feature. Today's start time:"),
        "N/A": _("N/A"),
        "Check time of day before executing changes": _("Check time of day before executing changes"),
        "Execute changes anytime": _("Execute changes anytime"),
        "Automatic mode": _("Automatic mode"),
        "Set all devices to automatic mode": _("Set all devices to automatic mode"),
        "Mode selection toggles": _("Mode selection toggles"),
        "Hide mode selection toggles": _("Hide mode selection toggles"),
        "Show mode selection toggles": _("Show mode selection toggles"),
        "OFF": _("OFF"),
        "ON": _("ON"),
        "Auto": _("Auto"),
        "Manual": _("Manual"),
        "Save": _("Save"),
        "Close": _("Close"),
        "Scheduled": _("Scheduled"),
        "Backup": _("Backup"),
        "Run a preconfigured backup": _("Run a preconfigured backup"),
        "Debug log": _("Debug log"),
        "Refresh": _("Refresh"),
        "Full debug log": _("Full debug log"),
        "'Debug' level logs": _("'Debug' level logs"),
        "'Error' level logs": _("'Error' level logs"),
        "Hello!": _("Hello!"),
        "Running requests and getting cached state status...": _("Running requests and getting cached state status..."),
        "Querying device state...": _("Querying device state..."),
        "Device configuration": _("Device configuration"),
        "Unlock device": _("Unlock device"),
        "Lock device in this state": _("Lock device in this state"),
        "Module configuration": _("Module configuration"),
        "Settings for device ID": _("Settings for device ID"),
        "_text1": _("WARNING - do not use latin characters (é,à,ç...) or upper-case words if not absolutely required (for example, file locations, MAC addresses, True/False) as it may break your configuration"),
        "Settings for module": _("Settings for module")
    }

    try:
        return textDB[textid]
    except KeyError:
        debug.write("Text: {} not found in database", 1)
        return textid

#!/usr/bin/env python3
'''
    File name: texts.py
    Author: Maxime Bergeron
    Date last modified: 01/11/2019
    Python Version: 3.5

    A python text internationalization handler for the webserver
'''

from core.common import *


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
        "Hello": _("Hello"),
        "Running requests and getting cached state status...": _("Running requests and getting cached state status..."),
        "Querying device state...": _("Querying device state..."),
        "Device configuration": _("Device configuration"),
        "Unlock device": _("Unlock device"),
        "Lock device in this state": _("Lock device in this state"),
        "Module configuration": _("Module configuration"),
        "Settings for device ID": _("Settings for device ID"),
        "_text1": _("WARNING - do not use latin characters (é,à,ç...) or upper-case words if not absolutely required (for example, file locations, MAC addresses, True/False) as it may break your configuration"),
        "Settings for module": _("Settings for module"),
        "Attempt device reconnection": _("Attempt device reconnection"),
        "Confirm device state": _("Confirm device state"),
        "device": _("device"),
        "devices": _("devices"),
        "Device follows the time-check feature": _("Device follows the time-check feature"),
        "If the device status is OFF, will ignore all turn-off requests": _("If the device status is OFF, will ignore all turn-off requests"),
        "Device ignores its mode": _("Device ignores its mode"),
        "Device has a delay between state changes": _("Device has a delay between state changes"),
        "Device is read-only": _("Device is read-only"),
        "Presets editor": _("Presets editor"),
        "Existing presets": _("Existing presets"),
        "Edit preset": _("Edit preset"),
        "Preset name": _("Preset name"),
        "State values for the devices": _("State values for the devices"),
        "Apply state change on specified device group(s)": _("Apply state change on specified device group(s)"),
        "Skip the time check and run the script anyways": _("Skip the time check and run the script anyways"),
        "Run the request after a given number of seconds": _("Run the request after a given number of seconds"),
        "Turn all devices selected in current request ON": _("Turn all devices selected in current request ON"),
        "Turn all devices selected in current request OFF": _("Turn all devices selected in current request OFF"),
        "Trigger a device restart for compatible devices": _("Trigger a device restart for compatible devices"),
        "Toggle ON/OFF all devices selected in current request": _("Toggle ON/OFF all devices selected in current request"),
        "Force device state change (whatever the actual mode) and set back devices to AUTO mode": _("Force device state change (whatever the actual mode) and set back devices to AUTO mode"),
        "Run non-DEVICE_SKIP state requests as AUTO mode": _("Run non-DEVICE_SKIP state requests as AUTO mode"),
        "Force device ID# to change mode (as set by auto-mode)": _("Force device ID# to change mode (as set by auto-mode)"),
        "Purge all RTT, locations and location training data": _("Purge all RTT, locations and location training data"),
        "Device types": _("Device types"),
        "_text2": _("1: ON, 0: OFF, -1: Ignore. State choice can either be a single value (will apply to all devices of the same type) or a comma-separated list for each separated devices of the same kind - in order of configuration - device1state,device2state..."),
        "No preconfigured presets found in home.ini!": _("No preconfigured presets found in home.ini!"),
        "You need a preset name": _("You need a preset name"),
        "Preset is invalid. Check the debug file for details.": _("Preset is invalid. Check the debug file for details."),
        "Reload config file": _("Reload config file"),
        "Tools": _("Tools"),
        "Yes": _("Yes"),
        "No": _("No"),
        "Room groups selection": _("Room groups selection"),
        "Available groups": _("Available groups"),
        'Please select the groups that will be considered as "rooms" or "prioritary" groups': _('Please select the groups that will be considered as "rooms" or "prioritary" groups'),
        "No groups configured!": _("No groups configured!"),
        "Add/remove room groups": _("Add/remove room groups")
    }

    try:
        return textDB[textid]
    except KeyError:
        debug.write("Text: {} not found in database".format(textid), 1)
        return textid

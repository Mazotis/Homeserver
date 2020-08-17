#!/usr/bin/env python3
'''
    File name: device.py
    Author: Maxime Bergeron
    Date last modified: 19/06/2020
    Python Version: 3.7

    Main wrapper object for all Homeserver devices. Not a device per-se.
'''

import time
import datetime
from collections import deque
from core.common import *
from core.convert import convert_color
from threading import Lock


class device(object):
    def __init__(self, devid):
        self.devid = devid
        self.success = False
        self._connection = None
        self.group = []
        self.state = DEVICE_OFF
        self.disabled = False
        self.device_type = None
        self.request_auto_mode = True
        self.auto_mode = True
        self.reset_mode = False
        self.name = None
        self.color_type = None
        self.color_brightness = None
        self.skip_run_time = False
        self.forceoff = True
        self.ignoremode = False
        self.icon = None
        self.action_delay = 0
        self.last_action_timestamp = 0
        self.has_pseudodevice = None
        self.request_locked = False
        self.state_inference_group = None
        self.state_getter_mode = "normal"
        self.ignore_global_group = False
        self.retry_delay_on_failure = 0
        self.history_origin = "Unknown"
        self.history = deque(maxlen=10)
        self.interrupt = Lock()
        self.init_from_config()

    def init_from_config(self):
        self.config = getConfigHandler().set_section(device=self.devid)
        self.description = self.config["DESCRIPTION"]
        if self.config.dev_has_option("GROUP"):
            self.group = self.config["GROUP"].split(',')
        if self.config.dev_has_option("DEFAULT_INTENSITY"):
            self.intensity = self.config["DEFAULT_INTENSITY"]
        if self.config.dev_has_option("COLOR_TYPE"):
            self.color_type = self.config["COLOR_TYPE"]
        if self.config.dev_has_option("FORCEOFF"):
            self.forceoff = self.config.get_value("FORCEOFF", bool)
        if self.config.dev_has_option("IGNOREMODE"):
            self.ignoremode = self.config.get_value("IGNOREMODE", bool)
        if self.config.dev_has_option("NAME"):
            self.name = self.config["NAME"]
        if self.config.dev_has_option("ICON"):
            self.icon = self.config["ICON"]
        if self.config.dev_has_option("ACTION_DELAY"):
            self.action_delay = self.config.get_value("ACTION_DELAY", int)
        if self.config.dev_has_option("STATE_INFERENCE_GROUP"):
            self.state_inference_group = self.config["STATE_INFERENCE_GROUP"]
        if self.config.dev_has_option("STATE_GETTER_MODE"):
            self.state_getter_mode = self.config["STATE_GETTER_MODE"]
        if self.config.dev_has_option("IGNORE_GLOBAL_GROUP"):
            self.ignore_global_group = self.config["IGNORE_GLOBAL_GROUP"]
        if self.config.dev_has_option("RETRY_DELAY_ON_FAILURE"):
            self.retry_delay_on_failure = self.config.get_value(
                "RETRY_DELAY_ON_FAILURE", int)

    def pre_run(self, color):
        try:
            if self.success:
                return True
            if (self.color_type == "noop" or self.request_locked):
                if self.convert(color) != DEVICE_SKIP:
                    debug.write("Device '{}' does not handle requests."
                                .format(self.name), 0, self.device_type)
                self.success = True
                return True
            if self.action_delay != 0 and self.last_action_timestamp + self.action_delay > int(time.time()):
                debug.write("Device '{}' is still executing previous request."
                            .format(self.name), 0, self.device_type)
                self.state = DEVICE_STANDBY
                return True
            if color == DEVICE_SKIP:
                self.success = True
                return True
            if color not in (self.convert(DEVICE_OFF), DEVICE_SKIP) and self.skip_run_time:
                self.success = True
                debug.write("Device '{}' skipped due to actual time.".format(
                    self.name), 0, self.device_type)
                return True

            if not self.ignoremode:
                if not self.auto_mode and self.request_auto_mode and not self.reset_mode:
                    # AUTO mode request on MANUAL device
                    debug.write("Device '{}' is set in MANUAL mode, skipping."
                                .format(self.name), 0, self.device_type)
                    self.success = True
                    return True
                if self.auto_mode and not self.request_auto_mode and not self.reset_mode:
                    debug.write("Device '{}' set to MANUAL mode."
                                .format(self.name), 0, self.device_type)
                    self.auto_mode = False
                    self.history.append(
                        history("Mode", "Auto => Manual", self.history_origin))
                if self.reset_mode:
                    if not self.auto_mode:
                        debug.write("Device '{}' set back to AUTO mode."
                                    .format(self.name), 0, self.device_type)
                        self.history.append(
                            history("Mode", "Manual => Auto", self.history_origin))
                    self.auto_mode = True
            else:
                debug.write("Skipping mode evaluation for device '{}'."
                            .format(self.name), 0, self.device_type)
            if self.state == self.convert(color) and str(color) not in [self.convert(DEVICE_OFF), DEVICE_INFERRED_OFF]:
                self.success = True
                debug.write("Device '{}' is already of the requested state, skipping."
                            .format(self.name), 0, self.device_type)
                return True

            if self.state == self.convert(color) and str(color) in [self.convert(DEVICE_OFF), DEVICE_INFERRED_OFF] and not self.forceoff:
                self.success = True
                debug.write("Device '{}' is already off and forcing-off disabled, skipping."
                            .format(self.name), 0, self.device_type)
                return True

            if self.action_delay != 0:
                self.last_action_timestamp = time.time()
            if not self.check_last_history_item("State", "{} => {}".format(self.state, self.convert(color))):
                self.history.append(history("State", "{} => {}".format(
                    self.state, self.convert(color)), self.history_origin))
            return self.run(color)
        except NewRequestException:
            debug.write("Aborting device '{}' state change".format(
                self.name), 0, self.device_type)
            return False

    def convert(self, color):
        if self.color_type is None:
            debug.write("Device '{}' must declare a state type. Quitting.".format(
                self.name), 2, self.device_type)
            quit()
        return convert_color(color, self.color_type)

    def post_run(self):
        """ Prepares the device for a future request """
        self.success = False
        self.reset_mode = False
        self.skip_run_time = False
        self.history_origin = "Unknown"
        return

    def get_state_pre(self):
        """ Pre-state getter functions """
        if self.action_delay != 0 and self.last_action_timestamp + self.action_delay > int(time.time()):
            return DEVICE_STANDBY
        return self.get_state()

    def get_state(self):
        """ Getter for the actual state """
        return self.state

    def get_inferred_group_state(self, dm):
        _states = []
        for _cnt, dev in enumerate(dm):
            if _cnt != self.devid and self.state_inference_group in dm[_cnt].group:
                _states.append(str(dm[_cnt].state))
        if all(x == DEVICE_ON for x in _states):
            if self.state != DEVICE_ON:
                debug.write("Device '{}' actual state inferred as ON from its group state".format(
                    self.name), 0, self.device_type)
                return DEVICE_INFERRED_ON
        elif all(x == DEVICE_OFF for x in _states):
            if self.state != DEVICE_OFF:
                debug.write("Device '{}' actual state inferred as OFF from its group state".format(
                    self.name), 0, self.device_type)
                return DEVICE_INFERRED_OFF
        return self.state

    def set_state(self, state):
        """ Setter for the actual state """
        self.history.append(
            history("State", "{} => {}".format(self.state, state), "Manual"))
        if state in ["0", 0]:
            self.state = DEVICE_OFF
        elif state in ["1", 1]:
            self.state = DEVICE_ON
        else:
            self.state = state
        debug.write("Manually set device ({}) {} state to {}".format(
            self.device_type, self.device, self.state), 0, self.device_type)

    def lock_unlock_requests(self, is_locked):
        self.history.append(
            history("Locked", bool(is_locked), self.history_origin))
        debug.write("Device '{}' is set to locked = {}."
                    .format(self.name, bool(is_locked)), 0, self.device_type)
        self.request_locked = bool(is_locked)
        return

    def descriptions(self):
        """ Getter for the device description """
        return self.description

    def disconnect(self):
        """ Disconnects the device """
        pass

    def reconnect(self):
        """ Function used to reconnect device in case of connection failure, without having to restart the whole server """
        debug.write("Device ({}) {} does not support live reconnection".format(
            self.device_type, self.device), 1, self.device_type)
        pass

    def create_pseudodevice(self):
        """ Used to create shared pseudo-devices (non-state devices), for example linkers/connectors for a wide range of devices """
        pass

    def get_pseudodevice(self, pseudodevice):
        """ Used to receive the shared pseudo-devices class from the devicemanager """
        pass

    def interruptible(self, _f):
        # Function wrapper for interruptible device functions, used with 'lambda: f(args)'
        # The caller function must check for a None return to intercept interrupts
        if self.interrupt.locked():
            raise RequestAborted(
                "'{}' request aborted, falling back to old state.".format(self.name))
        return _f()

    def get_history(self):
        return [str(h) for h in self.history]

    def check_last_history_item(self, element, change):
        try:
            if self.history[-1].element == element and self.history[-1].change == change:
                return True
        except IndexError:
            pass
        return False

    def set_failed_history(self):
        self.history.append(history("Failure", "", self.history_origin))

    def check_for_repeating_failures(self):
        try:
            if self.history[-1].element == "Failure" or self.history[-2].element == "Failure":
                debug.write("Device {} has failed already. Aborting state change attempt.".format(self.name), 1)
                return True
        except IndexError:
            pass
        return False

    @staticmethod
    def _get_time():
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


class history(object):
    def __init__(self, element, change, origin):
        self.element = element
        self.change = change
        self.origin = origin
        self.history_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if self.element not in ["Failure", "State", "Mode", "Locked"]:
            debug.write(
                "Got unexpected element for history tracking: {}".format(self.element), 3)

    def __str__(self):
        return "({}) [{}] {} (Origin: {})".format(self.history_time, self.element, self.change, self.origin)

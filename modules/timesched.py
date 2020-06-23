#!/usr/bin/env python3
'''
    File name: timesched.py
    Author: Maxime Bergeron
    Date last modified: 22/06/2020
    Python Version: 3.7

    The time and scheduling management module for the homeserver
'''

import datetime
import re
import subprocess
from core.common import *
from core.devicemanager import StateRequestObject
from scripts.suntimes import get_sun
from threading import Event, Thread


class timesched(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.stopevent = Event()
        self.dm = dm
        self.last_update = "Never"
        self.default_event_hour = "18:00"
        self.default_event_hour_stop = "06:00"
        # TODO Should they be ignored everywhere (ie webserver) if they're disabled (non-auto)?
        self.sunset = "18:00"
        self.sunrise = "06:00"
        self.tracked_devices_times = {}
        self.tracked_modules_times = {}
        self.always_skip_time = False
        self.init_from_config()

    def run(self):
        debug.write(
            "Started the time scheduler for devices and modules.", 0, "TIMESCHED")
        self.last_time = None
        while not self.stopevent.is_set():
            self.update_event_time()
            self.stopevent.wait(10)
            self.actual_time = datetime.datetime.now().time()
            if self.last_time is None:
                self.fetch_modules()

            if self.last_time is not None and self.last_time < self.new_day_time < self.actual_time:
                # NEW DAY maintenance
                if self.config.get_value('AUTO_RECONNECT_ON_NEW_DAY', bool):
                    debug.write(
                        "Attempting disabled devices reconnection for new day", 0, "TIMESCHED")
                    for _dev in self.dm:
                        if _dev.state == DEVICE_DISABLED:
                            _dev.reconnect()
                if self.config.get_value('FALLBACK_AUTO_ON_NEW_DAY', bool):
                    debug.write(
                        "Setting back all devices to AUTO mode for new day", 0, "TIMESCHED")
                    req = StateRequestObject(force_auto_mode=True, notime=True)
                    req.initialize_dm(self.dm)
                    req()

            for _modStopStart, _time in self.tracked_modules_times.items():
                if self.last_time is not None and self.last_time < _time < self.actual_time:
                    if "_start" in _modStopStart:
                        debug.write("Starting module '{}' (starting time: {})".format(
                            _modStopStart[:-6], _time), 0, "TIMESCHED")
                        self.dm.get_modules_list(
                            load_single_module=_modStopStart[:-6])
                    if "_stop" in _modStopStart:
                        debug.write("Stopping module '{}' (stopping time: {})".format(
                            _modStopStart[:-5], _time), 0, "TIMESCHED")
                        self.dm.shutdown_modules(
                            remove_single_module=_modStopStart[:-5])

            self.last_time = self.actual_time
            self.stopevent.wait(20)
        debug.write("Stopped.", 0, "TIMESCHED")
        return

    def stop(self):
        debug.write("Stopping.", 0, "TIMESCHED")
        self.stopevent.set()

    def init_from_config(self):
        self.last_time = None
        self.full_config = getConfigHandler()
        self.config = self.full_config.set_section("TIMESCHED")
        self.event_hour_config = self.config['DEFAULT_EVENT_HOUR']
        self.event_hour_stop_config = self.config['DEFAULT_EVENT_HOUR_STOP']
        self.event_localization = None
        self.event_localization_parser = "python"
        self.new_day = "06:00"
        if self.config.dev_has_option("EVENT_LOCALIZATION"):
            self.event_localization = self.config['EVENT_LOCALIZATION']
        if self.config.dev_has_option("EVENT_LOCALIZATION_PARSER"):
            self.event_localization_parser = self.config['EVENT_LOCALIZATION_PARSER']
        if self.config.dev_has_option("NEW_DAY_RESET_HOUR"):
            self.new_day = self.config['NEW_DAY_RESET_HOUR']
        for _devid, _dev in enumerate(self.dm):
            if self.config.dev_has_option("DEVICE" + str(_devid)):
                debug.write("Device {} has been configured to accept automatic requests between: '{}'".format(
                    _dev.name, self.config["DEVICE" + str(_devid)]), 0, "TIMESCHED")
                self.tracked_devices_times[_devid] = self.config["DEVICE" +
                                                                 str(_devid)]

    def fetch_modules(self):
        for _mod in getModules():
            if self.full_config.has_section(_mod.upper()) and self.full_config.has_option(_mod.upper(), "RUN_TIME"):
                if self.full_config[_mod.upper()]["RUN_TIME"] != "always":
                    _startTime = datetime.datetime.strptime(
                        self.full_config[_mod.upper()]["RUN_TIME"][0:5], '%H:%M').time()
                    _stopTime = datetime.datetime.strptime(
                        self.full_config[_mod.upper()]["RUN_TIME"][6:11], '%H:%M').time()
                    self.tracked_modules_times[_mod + "_start"] = _startTime
                    self.tracked_modules_times[_mod + "_stop"] = _stopTime
                    debug.write("Module {} configured to run between {}-{}".format(
                        _mod, _startTime, _stopTime), 0, "TIMESCHED")
                    if not self.verify_times(_startTime, _stopTime):
                        debug.write("Stopping module '{}' (stopping time: {})".format(
                            _mod, _stopTime), 0, "TIMESCHED")
                        self.dm.shutdown_modules(remove_single_module=_mod)

    def check_event_time(self, request, skip_time=False):
        has_non_skipped_devices = False
        self.update_event_time()
        if self.always_skip_time or skip_time:
            debug.write("Skipping time check for this request", 0, "TIMESCHED")
            return True
        for _devid, _dev in enumerate(self.dm):
            if _devid in self.tracked_devices_times:
                if self.tracked_devices_times[_devid] == "auto":
                    if not self.verify_times(self.default_event_hour, self.default_event_hour_stop):
                        _dev.skip_run_time = True
                    continue
                if not re.match("^(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]-(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$", self.tracked_devices_times[_devid]):
                    debug.write("The given times '{}' for device {} are invalid. The correct format should be HH:mm-HH:mm, where the first time is the OFF time in the morning, and the second is the ON time later, in 24-hrs format".format(
                        self.tracked_devices_times[_devid], _dev.name), 1)
                    continue
                if not self.verify_times(datetime.datetime.strptime(self.tracked_devices_times[_devid][0:5], '%H:%M').time(), datetime.datetime.strptime(self.tracked_devices_times[_devid][6:11], '%H:%M').time()):
                    debug.write("Device {} will accept automatic runs between {} and {}".format(_dev.name, datetime.datetime.strptime(
                        self.tracked_devices_times[_devid][6:11], '%H:%M').time(), datetime.datetime.strptime(self.tracked_devices_times[_devid][0:5], '%H:%M').time()), 1, "TIMESCHED")
                    _dev.skip_run_time = True
                    continue
            if request.colors[_devid] != DEVICE_SKIP:
                has_non_skipped_devices = True

        if not self.verify_times(self.default_event_hour, self.default_event_hour_stop):
            for _device, _color in zip(self.dm, request.colors):
                if _color == DEVICE_OFF or has_non_skipped_devices:
                    debug.write("Not all devices will be changed.",
                                0, "TIMESCHED")
                    return True
            debug.write("Too soon to change devices. Default device time for changes is at {}"
                        .format(self.default_event_hour), 0, "TIMESCHED")
            return False
        return True

    def update_event_time(self):
        if self.last_update != datetime.date.today():
            self.last_update = datetime.date.today()
            if self.event_localization is not None:
                self.sunset = self._update_sunset_time(
                    self.event_localization, self.event_localization_parser)
                self.sunrise = self._update_sunrise_time(
                    self.event_localization, self.event_localization_parser)
            if str(self.event_hour_config) != "auto":
                self.default_event_hour = datetime.datetime.strptime(
                    self.event_hour_config, '%H:%M').time()
                debug.write("State change event time set as: {}".format(
                    self.default_event_hour), 0, "TIMESCHED")
            else:
                self.default_event_hour = self.sunset
                debug.write("State change event time set as sunset time: {}".format(
                    self.default_event_hour), 0, "TIMESCHED")

            if str(self.event_hour_stop_config) != "auto":
                self.default_event_hour_stop = datetime.datetime.strptime(
                    self.event_hour_stop_config, '%H:%M').time()
                debug.write("State change stop event time set as: {}".format(
                    self.default_event_hour_stop), 0, "TIMESCHED")
            else:
                self.default_event_hour_stop = self.sunrise
                debug.write("State change stop event time set as sunrise time: {}".format(
                    self.default_event_hour_stop), 0, "TIMESCHED")

            if self.new_day == "auto":
                debug.write("New day maintenance time set as sunrise time: {}".format(
                    self.sunrise), 0, "TIMESCHED")
                self.new_day_time = self.sunrise
        return self.default_event_hour

    def set_serverwide_skiptime(self):
        """ Enables skipping time check all the time"""
        debug.write("Skipping time check for all requests", 0, "TIMESCHED")
        self.always_skip_time = True

    def verify_times(self, starttime, stoptime):
        # Times can be inverted (devices may start at DAY-1 then stop the next day, or start and stop on the same day)
        now_time = datetime.datetime.now().time()
        if stoptime > starttime:
            return stoptime > now_time > starttime
        else:
            return now_time > starttime or now_time < stoptime

    @staticmethod
    def _update_sunset_time(localization, localization_parser):
        if localization_parser == "bash":
            p1 = subprocess.Popen('./scripts/sunset.sh %s' % str(localization), stdout=subprocess.PIPE,
                                  shell=True)
            (output, _) = p1.communicate()
            p1.wait()
            try:
                _time = datetime.datetime.strptime(
                    output.rstrip().decode('UTF-8'), '%H:%M').time()
            except ValueError:
                debug.write(
                    "Connection error to the sunset time server. Falling back to 18:00.", 1)
                _time = datetime.datetime.strptime("18:00", '%H:%M').time()
        elif localization_parser == "python":
            _time = get_sun(localization)["sunset"].time()
            if _time is None:
                debug.write(
                    "Failed to fetch sunset time for your city. Falling back to 18:00", 1)
                _time = datetime.datetime.strptime("18:00", '%H:%M').time()
        return _time

    @staticmethod
    def _update_sunrise_time(localization, localization_parser):
        if localization_parser == "bash":
            p1 = subprocess.Popen('./scripts/sunrise.sh %s' % str(localization), stdout=subprocess.PIPE,
                                  shell=True)
            (output, _) = p1.communicate()
            p1.wait()
            try:
                _time = datetime.datetime.strptime(
                    output.rstrip().decode('UTF-8'), '%H:%M').time()
            except ValueError:
                debug.write(
                    "Connection error to the sunset time server. Falling back to 06:00.", 1)
                _time = datetime.datetime.strptime("06:00", '%H:%M').time()
        elif localization_parser == "python":
            _time = get_sun(localization)["sunrise"].time()
            if _time is None:
                debug.write(
                    "Failed to fetch sunset time for your city. Falling back to 06:00", 1)
                _time = datetime.datetime.strptime("06:00", '%H:%M').time()
        return _time

#!/usr/bin/env python3
'''
    File name: devicemanager.py
    Author: Maxime Bergeron
    Date last modified: 22/12/2019
    Python Version: 3.7

    The device and modules manager for the homeserver. Not a module per-se
'''
import ast
import datetime
import re
import subprocess
import time
import unidecode
try:
    import queue
except ImportError:
    import Queue as queue
from copy import deepcopy
from core.common import *
from core.convert import convert_to_web_rgb, convert_color
try:
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
except ImportError:
    pass
from threading import Thread, Timer, Lock


lock = Lock()
state_lock = Lock()
request_queue = queue.Queue()


class ExecutionState():
    exec_lock = Lock()
    executing = False

    @staticmethod
    def get():
        with ExecutionState().exec_lock:
            return ExecutionState().executing

    @staticmethod
    def set(exec_state):
        with ExecutionState().exec_lock:
            ExecutionState().executing = exec_state


class DeviceManager(object):
    """ Methods for instanciating and managing devices """

    def __init__(self):
        debug.get_set_lock()
        debug.enable_debug()
        self.config = getConfigHandler()
        self.devices = []
        self.pseudodevices = {}
        debug.write(
            "***********************************************************", 0)
        debug.write(
            "***               HomeServer, by Mazotis                ***", 0)
        debug.write(
            "***********************************************************", 0)
        debug.write("Version: {}".format(VERSION), 0)
        debug.write("Compiled devices: {}".format(", ".join(getDevices())), 0)
        debug.write("Compiled modules: {}".format(", ".join(getModules())), 0)
        debug.write(
            "***********************************************************", 0)
        debug.write("", 0)
        self.get_devices_list()
        self.lastupdate = None
        self.always_skip_time = False
        self.update_event_time()
        self.queue = queue.Queue()
        self.scheduled_changes = []
        self.scheduled_disconnect = None
        self.states = self.get_state()
        self.skip_time = False
        debug.write("Got initial device states {}".format(self.states), 0)
        self.light_threads = [None] * len(self)
        self.light_pool = None
        self.all_groups = None

    def __len__(self):
        return len(self.devices)

    def __getitem__(self, position):
        return self.devices[position]

    def __setitem__(self, position, device):
        try:
            self.devices[position] = device
        except IndexError:
            self.devices.append(device)

    def __call__(self, is_async=True, async_only_for_devid=None):
        dm_status = {}
        dm_status["state"] = self.get_state(
            is_async=is_async, async_only_for_devid=async_only_for_devid, webcolors=True)
        dm_status["intensity"] = self.get_state(
            is_async=True, intensity=True)
        dm_status["mode"] = self.modes
        dm_status["type"] = self.types
        dm_status["name"] = self.names
        for op in ["skiptime", "forceoff", "ignoremode", "actiondelay"]:
            dm_status["op_" + op] = self.get_option(op)
        dm_status["icon"] = self.icons
        dm_status["description"] = self.get_descriptions(
            True)
        if str(self.config['SERVER']['EVENT_HOUR']) != "auto":
            dm_status["daystarttime"] = "06:00"
        else:
            dm_status["daystarttime"] = "{}".format(self.sunrise)
        dm_status["starttime"] = "{}".format(self.starttime)
        dm_status["endtime"] = "{}".format(self.endtime)
        dm_status["detectorstart"] = "00:00"
        if self.config.has_option("DETECTOR", "START_HOUR"):
            dm_status["detectorstart"] = "{}".format(
                self.config["DETECTOR"]["START_HOUR"])
        dm_status["detectorend"] = "00:01"
        if self.config.has_option("DETECTOR", "END_HOUR"):
            dm_status["detectorend"] = "{}".format(
                self.config["DETECTOR"]["END_HOUR"])
        dm_status["groups"] = self.all_groups
        dm_status["colortype"] = self.colortypes
        dm_status["moduleweb"] = self.module_web
        dm_status["locked"] = self.lock_status
        dm_status["roomgroups"] = ""
        if self.config.has_option("WEBSERVER", "ROOM_GROUPS"):
            dm_status["roomgroups"] = self.config["WEBSERVER"]["ROOM_GROUPS"]
        dm_status["deviceroom"] = self.room_groups
        dm_status["version"] = VERSION
        return dm_status

    @property
    def threaded(self):
        return self.__threaded or False

    @threaded.setter
    def threaded(self, is_threaded):
        self.__threaded = is_threaded
        debug.write("Set threading for state changes as {}".format(
            self.__threaded), 0)

    @property
    def all_groups(self):
        if self.__all_groups is None:
            _groups = []
            for obj in self:
                for group in obj.group:
                    if group not in _groups:
                        _groups.append(group)
            self.all_groups = _groups
        return self.__all_groups

    @all_groups.setter
    def all_groups(self, groups):
        self.__all_groups = groups

    @property
    def types(self):
        typelist = []
        for obj in self:
            typelist.append(obj.__class__.__name__)
        return typelist

    @property
    def modes(self):
        modelist = []
        for obj in self:
            modelist.append(obj.auto_mode)
        return modelist

    @property
    def names(self):
        namelist = []
        for obj in self:
            if obj.name is not None:
                namelist.append(obj.name)
            else:
                # Fallback to device then device type
                try:
                    namelist.append(obj.device)
                except NameError:
                    namelist.append(obj.device_type)
        return namelist

    @property
    def icons(self):
        iconlist = []
        for obj in self:
            if obj.icon is not None:
                iconlist.append(obj.icon)
            else:
                iconlist.append("none")
        return iconlist

    @property
    def colortypes(self):
        ctypelist = []
        for obj in self:
            ctypelist.append(obj.color_type)
        return ctypelist

    @property
    def module_web(self):
        weblist = []
        for obj in self.modules:
            try:
                # TODO - fix non-permanent modules such as weblog
                if obj.isAlive() or obj.__class__.__name__ == "weblog":
                    weblist.append(obj.web)
            except AttributeError:
                weblist.append("none")
                pass
        return weblist

    @property
    def lock_status(self):
        locklist = []
        for obj in self:
            if obj.request_locked:
                locklist.append("1")
            else:
                locklist.append("0")
        return locklist

    @property
    def room_groups(self):
        if self.config.has_option("WEBSERVER", "ROOM_GROUPS"):
            devrooms = []
            room_groups = self.config["WEBSERVER"]["ROOM_GROUPS"].split(",")
            for _cnt, obj in enumerate(self):
                has_room = False
                for group in obj.group:
                    if group in room_groups:
                        try:
                            devrooms[_cnt] = devrooms[_cnt] + "," + group
                        except IndexError:
                            devrooms.append(group)
                            has_room = True
                if not has_room:
                    devrooms.append("")
        else:
            devrooms = [""] * len(self)
        return devrooms

    def get_devices_list(self):
        i = 0
        while True:
            try:
                _devtype = self.config.get_device(i, "TYPE")
                if _devtype in getDevices():
                    _module = __import__(
                        "devices." + _devtype)
                    # TODO Needed twice ? looks unpythonic
                    _class = getattr(
                        _module, _devtype)
                    _class = getattr(
                        _class, _devtype)
                    self[i] = _class(i)
                    self.get_and_link_pseudodevice(i)
                else:
                    debug.write('Unsupported device type {}'
                                .format(_devtype), 1)
            except KeyError:
                debug.write('Loaded {} devices'.format(i), 0)
                break
            i = i + 1

    def get_modules_list(self):
        loaded_modules = getConfigHandler()['SERVER']['MODULES'].split(",")
        # TODO put that check in some module?
        if all(x in loaded_modules for x in ['ifttt', 'dialogflow']):
            debug.write(
                "You cannot load ifttt and dialogflow at the same time. Quitting.", 2)
            sys.exit()

        self.modules = []
        for _cnt, _mod in enumerate(loaded_modules):
            if _mod in getModules():
                _module = __import__("modules." + _mod)
                # TODO Needed twice ? looks unpythonic
                _class = getattr(_module, _mod)
                _class = getattr(_class, _mod)
                self.modules.append(_class(self))
                self.modules[_cnt].start()
            else:
                debug.write('Unsupported module {}'
                            .format(_mod), 1)

    def set_serverwide_skiptime(self):
        """ Enables skipping time check all the time"""
        debug.write("Skipping time check for all requests", 0)
        self.always_skip_time = True

    def set_mode(self, request):
        for _device, _color in zip(self, request):
            if request.colors is not None and _color != DEVICE_SKIP:
                _device.request_auto_mode = request.auto_mode
                _device.reset_mode = request.reset_mode
            if request.force_auto_mode:
                _device.auto_mode = True
        if request.set_mode_for_devid is not None:
            self[request.set_mode_for_devid].auto_mode = request.auto_mode
        if request.force_auto_mode:
            debug.write("All devices set to AUTO mode", 0)
        if request.reset_mode:
            debug.write("All non-skipped devices set back to AUTO mode", 0)

    def get_group(self, request):
        """ Gets devices from a specific group for the light change """
        if type(request.group) == str:
            request.group = [request.group]
        for _cnt, _gr in enumerate(request.group):
            request.group[_cnt] = unidecode.unidecode(_gr.lower())
        for _cnt, _device in enumerate(self):
            if request.group is not None and set(request.group).issubset([unidecode.unidecode(x) for x in _device.group]):
                continue
            debug.write("Skipping device '{}' as it does not belong in the {} group(s)"
                        .format(_device.name, request.group), 0)
            request[_cnt] = DEVICE_SKIP

    def get_toggle(self):
        """ Toggles the devices on/off """
        # TODO Check if this still works or deprecate it.
        states = [DEVICE_ON] * len(self)
        for _cnt, _state in enumerate(self.get_state(is_async=True)):
            if _state not in [DEVICE_OFF, DEVICE_INFERRED_OFF]:
                states[_cnt] = [DEVICE_OFF]
        return states

    def get_descriptions(self, as_list=False):
        """ Getter for configured devices descriptions """
        desclist = []
        desctext = ""
        i = 1
        for obj in self:
            desctext += str(i) + " - " + obj.descriptions() + "\n"
            if as_list:
                desclist.append(obj.descriptions())
            i += 1
        if as_list:
            return desclist
        return desctext

    def get_option(self, option):
        oplist = []
        for obj in self:
            if option == "skiptime":
                oplist.append(obj.default_skip_time)
            elif option == "forceoff":
                oplist.append(obj.forceoff)
            elif option == "ignoremode":
                oplist.append(obj.ignoremode)
            elif option == "actiondelay":
                oplist.append(obj.action_delay)
        return oplist

    def reload_configs(self):
        self.config = getConfigHandler(renew=True)
        for _dev in self:
            try:
                _dev.init_from_config()
            except NameError:
                pass
        self.shutdown_modules()
        self.get_modules_list()

    def shutdown_modules(self):
        for _cnt, _mod in enumerate(self.modules):
            try:
                _mod.stop()
            except NameError:
                pass

    def update_event_time(self):
        if self.lastupdate != datetime.date.today():
            self.lastupdate = datetime.date.today()
            if str(self.config['SERVER']['EVENT_HOUR']) != "auto":
                self.lastupdate = datetime.date.today()
                self.starttime = datetime.datetime.strptime(
                    self.config['SERVER']['EVENT_HOUR'], '%H:%M').time()
            else:
                self.starttime = self._update_sunset_time(
                    self.config['SERVER']['EVENT_LOCALIZATION'])
                self.sunrise = self._update_sunrise_time(
                    self.config['SERVER']['EVENT_LOCALIZATION'])
                debug.write("State change event time set as sunset time: {}".format(
                    self.starttime), 0)
            self.endtime = datetime.datetime.strptime(
                self.config['SERVER']['EVENT_HOUR_STOP'], '%H:%M').time()
        return self.starttime

    def check_event_time(self, request, skip_time=False):
        now_time = datetime.datetime.now().time()
        self.update_event_time()
        for _dev in self:
            if self.always_skip_time or skip_time:
                _dev.set_event_time(self.starttime, True)
            else:
                _dev.set_event_time(self.starttime)
        if not skip_time and datetime.datetime.strptime(self.config['SERVER']['EVENT_HOUR_STOP'], '%H:%M').time() < now_time < self.starttime:
            for _device, _color in zip(self, request.colors):
                if _color != DEVICE_SKIP and _device.get_time_check(now_time):
                    debug.write("Not all devices will be changed. Device changes begins at {}"
                                .format(self.starttime), 0)
                    return True
            debug.write("Too soon to change devices. Device changes begins at {}"
                        .format(self.starttime), 0)
            return False
        return True

    def get_state(self, devid=None, is_async=False, async_only_for_devid=None, webcolors=False, intensity=False, _for_state_change=False):
        """ Getter for configured devices actual colors """
        if state_lock.locked():
            # There's most likely another SYNC state getter running
            is_async = True
        if not _for_state_change:
            while lock.locked():
                # Do not run state checks while there are state changes ?
                time.sleep(0.2)
        with state_lock:
            states = [None] * len(self)
            for _cnt, dev in enumerate(self):
                if devid is not None and devid != _cnt:
                    continue
                if is_async:
                    if intensity and self[_cnt].color_type in ["argb", "rgb", "255"]:
                        states[_cnt] = convert_color(dev.state, "100")
                    else:
                        states[_cnt] = dev.state
                else:
                    if async_only_for_devid is not None and _cnt != async_only_for_devid:
                        states[_cnt] = dev.state
                    else:
                        states[_cnt] = dev.get_state()
                if webcolors:
                    states[_cnt] = convert_to_web_rgb(
                        states[_cnt], dev.color_type, dev.color_brightness)
            if not is_async and devid is None:
                debug.write(
                    "All devices state status updated in real-time", 0)
            if devid is not None:
                if self[devid].state_inference_group is not None:
                    states[devid] = self[devid].get_inferred_group_state(self)
                return states[devid]
            for _cnt, dev in enumerate(self):
                # Has to be called after device states all updated ? Only relevant on non-async requests ?
                if self[_cnt].state_inference_group is not None:
                    states[_cnt] = self[_cnt].get_inferred_group_state(self)
        return states

    def set_light_stream(self, devid, color, is_group):
        """ Simplified function for quick, streamed light change requests """
        if is_group:
            for device in self:
                if device.group == devid:
                    cnt = 0
                    _color = device.convert(color)
                    while True:
                        if cnt == 4:
                            break
                        if device.run(color, 3):
                            break
                        time.sleep(0.3)
                        cnt = cnt + 1
        else:
            cnt = 0
            _color = device.convert(color)
            while True:
                if cnt == 4:
                    break
                if self[devid].run(_color, 3):
                    break
                time.sleep(0.3)
                cnt = cnt + 1
        self.reinit()

    def clean_delayed_changes(self):
        for _sched in self.scheduled_changes:
            if _sched is not None and not _sched.isAlive():
                self.scheduled_changes.remove(_sched)

    def stop_delayed_changes(self):
        self.clean_delayed_changes()
        for _sched in self.scheduled_changes:
            if _sched is not None:
                _sched.cancel()

    def reinit(self):
        """ Resets the Success bool to False """
        i = 0
        while i < len(self):
            self[i].post_run()
            i += 1

    def get_and_link_pseudodevice(self, devid):
        _pseudodev = self.devices[devid].has_pseudodevice
        if _pseudodev is not None:
            if _pseudodev not in self.pseudodevices:
                self.pseudodevices[_pseudodev] = self[devid].create_pseudodevice(
                )
            self[devid].get_pseudodevice(
                self.pseudodevices[_pseudodev])

    def disconnect_devices(self):
        """ Disconnects all configured devices """
        self.scheduled_disconnect = None
        debug.write("Server unused. Disconnecting devices.", 0)
        for _dev in self:
            _dev.disconnect()

    def _decode_colors(self, request):
        _has_delays = False
        dev_delays = [0] * len(self)
        colors = request.colors
        for _cnt, _col in enumerate(colors):
            if type(_col) is not tuple:
                if re.match("[0-9a-fA-F]+del[0-9]+", str(_col)) is not None:
                    """ This is a delayed change (delay then action) """
                    _vals = _col.split("del")
                    colors[_cnt] = _vals[0]
                    dev_delays[_cnt] = int(_vals[1])
                    _has_delays = True
                if re.match("[0-9a-fA-F]+for[0-9]+", str(_col)) is not None:
                    """ This is a for-delay change (action, delay then off)"""
                    _vals = _col.split("for")
                    colors[_cnt] = _vals[0]
                    dev_delays[_cnt] = -int(_vals[1])
                    _has_delays = True
        if _has_delays:
            _delay_list = []
            for _delay in dev_delays:
                if _delay != 0 and _delay not in _delay_list:
                    _delay_list.append(_delay)
                    _delay_colors = [DEVICE_SKIP] * len(self)
                    for _acnt, _adelay in enumerate(dev_delays):
                        if _adelay == _delay:
                            if _adelay < 0:
                                _delay_colors[_acnt] = DEVICE_OFF
                                _delay = -_delay
                            else:
                                _delay_colors[_acnt] = colors[_acnt]
                                colors[_acnt] = DEVICE_SKIP
                            dev_delays[_acnt] = 0

                    delayed_req = StateRequestObject()
                    delayed_req.initialize_dm(self)
                    delayed_req.from_request(request)
                    delayed_req.set_colors(_delay_colors)
                    debug.write("Scheduling device state change ({}) after {} seconds".format(
                        _delay_colors, _delay), 0)
                    _sched = Timer(int(_delay), delayed_req.run, ())
                    _sched.start()
                    self.scheduled_changes.append(_sched)
        return colors

    def _set_lights(self):
        lock.acquire()
        if self.threaded:
            if len(self) == 0:
                max_workers = 1
            else:
                max_workers = len(self)
            self.light_pool = ThreadPoolExecutor(max_workers=max_workers)
        debug.write("Running a change of states...", 0)
        firstran = False
        colors = None
        try:
            while not self.queue.empty():
                _req = self.queue.get()
                if firstran:
                    debug.write("Getting remainder of queue", 0)
                    _req = self._merge_requests(_req, self.old_request)
                    self.reinit()
                self.old_request = _req
                colors = self._decode_colors(
                    _req)  # TODO Check performance
                self.check_event_time(
                    _req, _req.skip_time or self.always_skip_time)
                if all(c == DEVICE_SKIP for c in colors):
                    debug.write("All device requests skipped", 0)
                    break
                i = 0
                tries = 0
                firstran = True

                while i < len(self):
                    if not self[i].success:
                        _color = self[i].convert(colors[i])
                        self.light_threads[i] = None

                        if _color != DEVICE_SKIP:
                            self.states[i] = self.get_state(
                                i, _for_state_change=True)
                            if _color != self.states[i] or _color == DEVICE_OFF:
                                debug.write(("Device '{}', change {} => "
                                             "{} (Automatic mode: {})")
                                            .format(self[i].name,
                                                    self.states[i], _color,
                                                    self[i].auto_mode),
                                            0)
                                if self.threaded:
                                    if not self.queue.empty():
                                        break
                                    self.light_threads[i] = self.light_pool.submit(
                                        self[i].pre_run, _color)
                        if not self.threaded:
                            self[i].pre_run(_color)

                    i += 1

                    if i == len(self):
                        debug.write("Awaiting state change results", 0)
                        if self.threaded:
                            for _cnt, _thread in enumerate(self.light_threads):
                                if not self.queue.empty():
                                    break
                                if _thread is not None:
                                    try:
                                        _res = _thread.result(
                                            self.config["SERVER"].getint("REQUEST_TIMEOUT"))
                                        if not _res:
                                            debug.write("Repeating failed request for device: {} ({})".format(
                                                self[_cnt].name, self[_cnt].device_type), 1)
                                            self.light_threads[_cnt].set_exception(
                                                NewRequestException)
                                            self.light_threads[_cnt].cancel()
                                            self.light_threads[_cnt] = None
                                            i = 0
                                    except NewRequestException:
                                        debug.write(
                                            "Sent exception for new request", 0)
                                        break
                                    except TimeoutError:
                                        debug.write(
                                            "Request timed-out for device: {}".format(self[_cnt].name), 1)
                                        self.light_threads[_cnt].set_exception(
                                            NewRequestException)
                                        self.light_threads[_cnt].cancel()
                                        self.light_threads[_cnt] = None
                                        i = 0
                        else:
                            for _cnt, _dev in enumerate(self):
                                if not self.queue.empty():
                                    break
                                if not self[_cnt].success:
                                    debug.write("Device {} ({}) success bool off".format(
                                        _cnt, self[_cnt].name), 1)
                                    i = 0
                        tries = tries + 1
                        if tries == 5:
                            debug.write(
                                "Failed to change all states. Aborting", 1)
                            break

        except queue.Empty:
            debug.write("Nothing in queue", 0)
            pass

        finally:
            debug.write("Clearing up device change queues.", 0)
            if colors:
                self.queue.task_done()
            self.reinit()
            lock.release()
            ExecutionState().set(False)
            if self.threaded:
                self.light_pool.shutdown()
                # Let the Webserver some time to fetch single device state changes results
                time.sleep(0.5)
                self.states = self.get_state()

        debug.write("Change of device states completed.", 0)

    def _merge_requests(self, new_request, old_request):
        for _cnt, _color in enumerate(old_request.colors):
            if new_request[_cnt] == DEVICE_SKIP and _color != DEVICE_SKIP:
                new_request[_cnt] = _color
                if old_request.skip_time and not new_request.skip_time:
                    self[_cnt].skip_time = True
        return new_request

    @staticmethod
    def _update_sunset_time(localization):
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
        return _time

    @staticmethod
    def _update_sunrise_time(localization):
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
        return _time


class StateRequestObject(object):
    """ Methods for properly handling devicemanager state change requests """

    def __init__(self, **kwargs):
        self.hexvalues = []
        self.off = False
        self.on = False
        self.restart = False
        self.toggle = False
        self.devices = []
        for _dev in getDevices(True):
            if _dev not in self.devices:
                setattr(self, _dev, None)
        self.notime = False
        self.delay = 0
        self.preset = None
        self.manual_mode = False
        self.set_mode_for_devid = None
        self.reset_location_data = False
        self.stream_group = None
        self.stream_dev = None
        self.changed_vars = {}

        """ Initialization data from the devicemanager """
        self.length = 0
        self.device_list = []

        """ Vars for the completed request, used by the devicemanager directly """
        self.colors = None
        self.skip_time = False
        self.group = None
        self.device_type = None
        self.device_type_args = None
        self.auto_mode = False
        self.reset_mode = False
        self.force_auto_mode = False
        self.set(**kwargs)

    def __call__(self):
        self.run()

    def __str__(self):
        _str = ""
        for i, (_var, _chg) in enumerate(self.changed_vars.items()):
            if i != 0:
                _str += ", "
            if re.match("[0-9a-fA-F]+del[0-9]+", str(_chg)) is not None:
                """ This is a delayed change (delay then action) """
                _vals = _chg.split("del")
                _chg = "{} in {} seconds".format(_vals[0], _vals[1])
            if re.match("[0-9a-fA-F]+for[0-9]+", str(_chg)) is not None:
                """ This is a for-delay change (action, delay then off)"""
                _vals = _chg.split("for")
                _chg = "{} for {} seconds then turned off".format(
                    _vals[0], _vals[1])
            _str += "{} will be set to {}".format(_var, _chg)
        return _str

    def __getitem__(self, position):
        return self.colors[position]

    def __setitem__(self, position, color):
        if self.colors is None:
            debug.write(
                "State request must be initialized first using initialize_dm()", 1)
            raise ValueError
        self.colors[position] = color

    def set(self, **kwargs):
        allowed_keys = ['hexvalues', 'off', 'on', 'restart', 'toggle', 'group',
                        'notime', 'delay', 'preset', 'manual_mode', 'reset_location_data',
                        'force_auto_mode', 'auto_mode', 'reset_mode', 'skip_time', 'set_mode_for_devid']
        for _dev in getDevices(True):
            allowed_keys.append(_dev)
        for k, v in kwargs.items():
            k = k.replace("-", "_")
            if k not in allowed_keys and v is not None:
                debug.write(
                    "Missing or unallowed variable in request: {}".format(k), 1)
                return False
            if v in ["True", "true"]:
                v = True
            elif v in ["False", "false"]:
                v = False
            elif v == "":
                v = None
            if getattr(self, k, False) != v:
                self.changed_vars[k] = v
            if k in getDevices(True):
                if v is not None and not self.set_typed_colors(k, v):
                    return False
        self.__dict__.update((k, v)
                             for k, v in kwargs.items() if k in allowed_keys)
        return True

    def from_request(self, request):
        '''
        Create new request from old request, keeping only the
        options and parameters not related to requested state
        values
        '''
        ignore_vars = ['devices', 'changed_vars',
                       'length', 'device_list', 'colors', 'preset']
        for k, v in request.__dict__.items():
            if k not in ignore_vars and k not in getDevices(True):
                self.set(**{k: v})

    def from_string(self, json_str):
        if json_str is None or json_str == "":
            return False
        try:
            _args = ast.literal_eval(json_str)
            if not self.set(**_args):
                return False
            return True
        except ValueError:
            debug.write(
                "Request {} is incorrectly formed.".format(json_str), 1)
            return False

    def parse_args(self, args):
        for _arg in vars(args):
            if getattr(self, _arg, False) != vars(args)[_arg]:
                self.changed_vars[_arg] = vars(args)[_arg]
                setattr(self, _arg, vars(args)[_arg])
        for _dev in getDevices(True):
            if type(getattr(self, _dev, None)) == "str":
                debug.write(
                    'Converting values to lists for {}'.format(_dev), 0)
                setattr(self, _dev, str(
                    getattr(self, _dev, None).replace("'", "").split(',')))

    def initialize_dm(self, dm):
        """ Fetches the required variables from the devicemanager """
        self.length = len(dm.devices)
        self.device_list = [x.device_type for x in dm.devices]
        if self.colors is None:
            self.colors = [DEVICE_SKIP] * int(self.length)

    def set_colors(self, colors):
        if self.colors is None:
            debug.write(
                "ERROR - You need to initialize the request using initialize_dm() first", 1)
            return False

        if len(colors) == 1 and self.length != 1:
            self.colors = colors * self.length
            return
        for i, _color in enumerate(colors):
            if self[i] != _color:
                self[i] = _color

    def set_typed_colors(self, device_type, device_args):
        """ Gets devices of a specific  type for the light change """
        if self.device_list is None:
            debug.write(
                "ERROR - You need to initialize the request using initialize_dm() first", 1)
            return False

        device_indexes = [i for i, x in enumerate(
            self.device_list) if x.lower() == device_type.lower()]

        # TODO Fix that
        if type(device_args) == str:
            device_args = [device_args]

        if len(device_args) == 1 and len(device_indexes) > 1:
            debug.write("Expanding state {} to {} ({}) devices."
                        .format(len(device_args), len(device_indexes), device_type), 0)
            for i in device_indexes:
                self[i] = device_args[0]
        elif len(device_indexes) != len(device_args):
            debug.write("Received state hexvalues length {} ({}) for {} ({}) device(s). Quitting"
                        .format(len(device_args), device_args, len(device_indexes), device_type), 2)
            return False
        else:
            for _cnt, i in enumerate(device_indexes):
                self[i] = device_args[_cnt]
        return True

    def run(self):
        request_queue.put(self)


class RequestExecutor(object):
    """ This will connect all threads with the DM on the main thread """

    def __init__(self):
        ExecutionState().set(False)

    def run(self, dm):
        try:
            while True:
                self.execute(request_queue.get(), dm)
                time.sleep(0.1)
        except (KeyboardInterrupt, SystemExit):
            pass

    def execute(self, request, dm):
        """ Validates the request and runs the light change """
        ExecutionState().set(True)
        if dm.scheduled_disconnect is not None:
            dm.scheduled_disconnect.cancel()
            dm.scheduled_disconnect = None
        request.initialize_dm(dm)
        if not self.validate_request(dm, dm.config, request):
            return
        dm.clean_delayed_changes()

        if request.colors is None:
            request.colors = [DEVICE_SKIP] * len(dm)

        dm.skip_time = request.skip_time
        dm.set_mode(request)

        if request.group is not None:
            dm.get_group(request)

        if request.delay is not 0:
            delay = request.delay
            debug.write(
                "Delaying request for {} seconds".format(request.delay), 0)
            request.delay = 0
            _sched = Timer(int(delay), self.execute, (request,))
            _sched.start()
            dm.scheduled_changes.append(_sched)
            return
        debug.write("Locked status: {}".format(lock.locked()), 0)
        dm.queue.put(request)
        if not lock.locked():
            _thr = Thread(target=dm._set_lights).start()
        elif dm.threaded:
            for _thread in dm.light_threads:
                if _thread is not None and not _thread.done():
                    debug.write("Canceling thread {}".format(_thread), 1)
                    _thread.set_exception(NewRequestException)
                    _thread.cancel()
        dm.scheduled_disconnect = Timer(
            60, dm.disconnect_devices, ())
        dm.scheduled_disconnect.start()

    @staticmethod
    def validate_request(dm, config, request):
        debug.write("Validating arguments", 0)
        if request.reset_location_data:
            # TODO eventually add training data cleanup
            os.remove("../dnn/train.log")
            debug.write("Purged location and RTT data", 0)

        has_device_requests = False
        for _dev in getDevices(True):
            if getattr(request, _dev, None) is not None:
                has_device_requests = True
        if (request.colors is not None and len(request.colors) == len(dm.devices)) or request.set_mode_for_devid is not None:
            has_device_requests = True

        if request.hexvalues and has_device_requests:
            debug.write("Got color hexvalues for multiple devices in the same request, which is not \
                        supported. Use '{} -h' for help. Quitting".format(sys.argv[0]),
                        2)
            return False

        if len(request.hexvalues) != len(dm.devices) and not any([request.notime, request.off, request.on,
                                                                  request.toggle, request.preset, request.restart,
                                                                  request.group, has_device_requests,
                                                                  request.force_auto_mode]):
            debug.write("Got {} color hexvalues, {} expected. Use '{} -h' for help. Quitting"
                        .format(len(request.hexvalues), len(dm.devices), sys.argv[0]), 2)
            return False
        if request.hexvalues:
            debug.write("Received color hexvalues length {} for {} devices"
                        .format(len(request.hexvalues), len(dm.devices)), 0)
            request.set_colors(request.hexvalues)
        else:
            if request.set_mode_for_devid is not None:
                try:
                    debug.write("Received mode change request for devid {}".format(
                        request.set_mode_for_devid), 0)
                except KeyError:
                    debug.write("Devid {} does not exist".format(
                        request.set_mode_for_devid), 1)
                    return False

            for _dev in getDevices(True):
                if getattr(request, _dev, None) is not None:
                    debug.write("Received {} change request".format(_dev), 0)
                    if not request.set_typed_colors(_dev, getattr(request, _dev, None)):
                        return False

            if request.preset is not None:
                debug.write(
                    "Received change to preset [{}] request".format(request.preset), 0)
                try:
                    if not request.from_string(config["PRESETS"][request.preset]):
                        return False
                    request.auto_mode = config["PRESETS"].getboolean(
                        "AUTOMATIC_MODE")
                except KeyError:
                    debug.write(
                        "Preset '{}' not found in home.ini. Quitting.".format(request.preset), 3)
                    return False
            if request.off:
                debug.write("Received OFF change request", 0)
                request.set_colors([DEVICE_OFF])
            if request.on:
                debug.write("Received ON change request", 0)
                request.set_colors([DEVICE_ON])
            if request.restart:
                debug.write("Received RESTART change request", 0)
                request.device_type = "GenericOnOff"
                request.device_type_args = ["2"]
            if request.toggle:
                debug.write("Received TOGGLE change request", 0)
                request.set_colors(dm.get_toggle())
        if request.notime or request.off:
            request.skip_time = True

        debug.write("Arguments are OK", 0)
        return True

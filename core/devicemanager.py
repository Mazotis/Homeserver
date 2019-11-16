#!/usr/bin/env python3
'''
    File name: devicemanager.py
    Author: Maxime Bergeron
    Date last modified: 15/11/2019
    Python Version: 3.5

    The device and modules manager for the homeserver. Not a module per-se
'''
import ast
import datetime
import re
import subprocess
import time
import queue
from core.common import *
from core.convert import convert_to_web_rgb, convert_color
from concurrent.futures import ThreadPoolExecutor
from threading import Timer, Lock


lock = Lock()


class DeviceManager(object):
    """ Methods for instanciating and managing devices """

    def __init__(self, config=None):
        debug.get_set_lock()
        debug.enable_debug()
        self.config = config
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
        self.delays = [0] * len(self)
        self.scheduled_changes = []
        self.states = self.get_state()
        self.skip_time = False
        debug.write("Got initial device states {}".format(self.states), 0)
        self.light_threads = [None] * len(self)
        self.light_pool = None
        self.all_groups = None
        self.modules = []

    def __len__(self):
        return len(self.devices)

    def __getitem__(self, position):
        return self.devices[position]

    def __setitem__(self, position, device):
        try:
            self.devices[position] = device
        except IndexError:
            self.devices.append(device)

    def __call__(self, async=True):
        dm_status = {}
        dm_status["state"] = self.get_state(
            async=async, webcolors=True)
        dm_status["intensity"] = self.get_state(
            async=True, intensity=True)
        dm_status["mode"] = self.modes
        dm_status["type"] = self.types
        dm_status["name"] = self.names
        for op in ["skiptime", "forceoff", "ignoremode", "actiondelay"]:
            dm_status["op_" + op] = self.get_option(op)
        dm_status["icon"] = self.icons
        dm_status["description"] = self.get_descriptions(
            True)
        dm_status["starttime"] = "{}".format(self.starttime)
        dm_status["groups"] = self.all_groups
        dm_status["colortype"] = self.colortypes
        dm_status["moduleweb"] = self.module_web
        dm_status["locked"] = self.lock_status
        dm_status["roomgroups"] = ""
        if self.config.has_option("WEBSERVER", "ROOM_GROUPS"):
            dm_status["roomgroups"] = self.config["WEBSERVER"]["ROOM_GROUPS"]
        dm_status["deviceroom"] = self.room_groups
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
            for obj in self:
                for group in obj.group:
                    if group in room_groups:
                        devrooms.append(group)
                        break
                else:
                    devrooms.append("")
        else:
            devrooms = [""] * len(self)
        return devrooms

    def get_devices_list(self):
        i = 0
        while True:
            try:
                if self.config["DEVICE" + str(i)]["TYPE"] in getDevices():
                    _module = __import__(
                        "devices." + self.config["DEVICE" + str(i)]["TYPE"])
                    # TODO Needed twice ? looks unpythonic
                    _class = getattr(
                        _module, self.config["DEVICE" + str(i)]["TYPE"])
                    _class = getattr(
                        _class, self.config["DEVICE" + str(i)]["TYPE"])
                    self[i] = _class(i, self.config)
                    self.get_and_link_pseudodevice(i)
                else:
                    debug.write('Unsupported device type {}'
                                .format(self.config["DEVICE" + str(i)]["TYPE"]), 1)
            except KeyError:
                debug.write('Loaded {} devices'.format(i), 0)
                break
            i = i + 1

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
        for _cnt, _device in enumerate(self):
            if request.group is not None and set(request.group).issubset(_device.group):
                continue
            debug.write("Skipping device {} as it does not belong in the {} group(s)"
                        .format(_device.device, request.group), 0)
            request[_cnt] = DEVICE_SKIP

    def get_toggle(self):
        """ Toggles the devices on/off """
        # TODO Check if this still works or deprecate it.
        states = [DEVICE_ON] * len(self)
        for _cnt, _state in enumerate(self.get_state()):
            if _state not in [DEVICE_OFF, DEVICE_INFERRED_OFF]:
                states[_cnt] = [DEVICE_OFF]
        return states

    def set_typed_colors(self, request):
        """ Gets devices of a specific  type for the light change """
        device_indexes = [i for i, x in enumerate(
            self) if x.__class__.__name__.lower() == request.device_type.lower()]

        if len(request.device_type_args) == 1 and len(device_indexes) > 1:
            debug.write("Expanding state {} to {} devices."
                        .format(len(request.device_type_args), len(device_indexes)), 0)
            for i in device_indexes:
                request[i] = request.device_type_args[0]
        elif len(device_indexes) != len(request.device_type_args):
            debug.write("Received state hexvalues length {} for {} devices. Quitting"
                        .format(len(request.device_type_args), len(device_indexes)), 2)
            return False
        else:
            for _cnt, i in enumerate(device_indexes):
                request[i] = request.device_type_args[_cnt]
        return True

    def run(self, request):
        """ Validates the request and runs the light change """
        if not request.request_is_validated and not request.validate_request(self, self.config, called_on_run=True):
            return
        self.clean_delayed_changes()

        if request.colors is None:
            request.colors = [DEVICE_SKIP] * len(self)

        self.skip_time = request.skip_time
        self.set_mode(request)
        if request.device_type is not None:
            if not self.set_typed_colors(request):
                return
        if request.group is not None:
            self.get_group(request)

        if request.delay is not 0:
            delay = request.delay
            debug.write(
                "Delaying request for {} seconds".format(request.delay), 0)
            request.delay = 0
            _sched = Timer(int(delay), self.run, (request,))
            _sched.start()
            self.scheduled_changes.append(_sched)
            return
        # TODO Manage locking out when the run thread hangs
        debug.write("Locked status: {}".format(lock.locked()), 0)
        self.queue.put(request)
        if not lock.locked():
            self._set_lights()
        elif self.threaded:
            for _thread in self.light_threads:
                if _thread is not None and not _thread.done():
                    _thread.set_exception(NewRequestException)
                    _thread.cancel()

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
        self.config.read('home.ini')
        for _dev in self:
            try:
                _dev.config = self.config
                _dev.init_from_config()
            except NameError:
                pass
        for _mod in self.modules:
            try:
                _mod.config = self.config
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
                self.lastupdate = datetime.date.today()
                self.starttime = self._update_sunset_time(
                    self.config['SERVER']['EVENT_LOCALIZATION'])
                debug.write("State change event time set as sunset time: {}".format(
                    self.starttime), 0)
        return self.starttime

    def check_event_time(self, request, skip_time=False):
        now_time = datetime.datetime.now().time()
        self.update_event_time()
        for _dev in self:
            if self.always_skip_time or skip_time:
                _dev.set_event_time(self.starttime, True)
            else:
                _dev.set_event_time(self.starttime)
        if not skip_time and datetime.time(6, 00) < now_time < self.starttime:
            for _device, _color in zip(self, request.colors):
                if _color != DEVICE_SKIP and _device.get_time_check(now_time):
                    debug.write("Not all devices will be changed. Device changes begins at {}"
                                .format(self.starttime), 0)
                    return True
            debug.write("Too soon to change devices. Device changes begins at {}"
                        .format(self.starttime), 0)
            return False
        return True

    def get_state(self, devid=None, async=False, webcolors=False, intensity=False):
        """ Getter for configured devices actual colors """
        states = [None] * len(self)
        for _cnt, dev in enumerate(self):
            if devid is not None and devid != _cnt:
                continue
            if async:
                if intensity and self[_cnt].color_type in ["argb", "rgb", "255"]:
                    states[_cnt] = convert_color(dev.state, "100")
                else:
                    states[_cnt] = dev.state
            else:
                states[_cnt] = dev.get_state()
            if webcolors:
                states[_cnt] = convert_to_web_rgb(
                    states[_cnt], dev.color_type, dev.color_brightness)
        if not async and devid is None:
            debug.write(
                "All devices state status updated from devices get_state()", 0)
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

    def _decode_colors(self, colors):
        _has_delays = False
        self.delays = [0] * len(self)
        for _cnt, _col in enumerate(colors):
            if type(_col) is not tuple:
                if re.match("[0-9a-fA-F]+del[0-9]+", str(_col)) is not None:
                    """ This is a delayed change (delay then action) """
                    _vals = _col.split("del")
                    colors[_cnt] = _vals[0]
                    self.delays[_cnt] = int(_vals[1])
                    _has_delays = True
                if re.match("[0-9a-fA-F]+for[0-9]+", str(_col)) is not None:
                    """ This is a for-delay change (action, delay then off)"""
                    _vals = _col.split("for")
                    colors[_cnt] = _vals[0]
                    self.delays[_cnt] = -int(_vals[1])
                    _has_delays = True
        if _has_delays:
            _delay_list = []
            for _delay in self.delays:
                if _delay != 0 and _delay not in _delay_list:
                    _delay_list.append(_delay)
                    _delay_colors = [DEVICE_SKIP] * len(self)
                    for _acnt, _adelay in enumerate(self.delays):
                        if _adelay == _delay:
                            if _adelay < 0:
                                _delay_colors[_acnt] = DEVICE_OFF
                                _delay = -_delay
                            else:
                                _delay_colors[_acnt] = colors[_acnt]
                                colors[_acnt] = DEVICE_SKIP
                            self.delays[_acnt] = 0
                    req = StateRequestObject()
                    req.set_colors(_delay_colors, len(self))
                    if self.skip_time:
                        req.set(skip_time=True)
                    debug.write("Scheduling device state change ({}) after {} seconds".format(
                        _delay_colors, _delay), 0)
                    _sched = Timer(int(_delay), self.run, (req,))
                    _sched.start()
                    self.scheduled_changes.append(_sched)
        return colors

    def _set_lights(self):
        lock.acquire()
        if self.threaded:
            self.light_pool = ThreadPoolExecutor(max_workers=len(self))
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
                    _req.colors)  # TODO Check performance
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

                        if _color != DEVICE_SKIP:
                            self.states[i] = self.get_state(i)
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
                                else:
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
                                        _res = _thread.result(5)
                                        if not _res:
                                            debug.write("Repeating failed request for device: {}".format(
                                                self[_cnt].name), 1)
                                            i = 0
                                    except NewRequestException:
                                        break
                                    except TimeoutError:
                                        debug.write(
                                            "Request timed-out for device: {}".format(self[_cnt].name), 1)
                                        i = 0
                        else:
                            for _cnt, _dev in enumerate(self):
                                if not self.queue.empty():
                                    break
                                if not self[_cnt].success:
                                    i = 0
                        tries = tries + 1
                        if tries == 5:
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
            if self.threaded:
                self.light_pool.shutdown()
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

        """ Vars for the completed request, used by the devicemanager directly """
        self.colors = None
        #self.delays = []
        self.skip_time = False
        self.group = None
        self.device_type = None
        self.device_type_args = None
        self.auto_mode = False
        self.reset_mode = False
        self.force_auto_mode = False
        self.request_is_validated = False
        self.set(**kwargs)

    def __call__(self, dm):
        dm.run(self)

    def __str__(self):
        _str = ""
        for i, (_var, _chg) in enumerate(self.changed_vars.items()):
            if i != 0:
                _str += ", "
            _str += "{} will be set to {}".format(_var, _chg)
        return _str

    def __getitem__(self, position):
        return self.colors[position]

    def __setitem__(self, position, color):
        if self.colors is None:
            debug.write(
                "Requested states must be initialized first using set_colors()", 1)
            raise ValueError
        self.colors[position] = color

    def set(self, **kwargs):
        allowed_keys = ['hexvalues', 'off', 'on', 'restart', 'toggle', 'group',
                        'notime', 'delay', 'preset', 'manual_mode', 'reset_location_data',
                        'force_auto_mode', 'auto_mode', 'reset_mode', 'skip_time', 'set_mode_for_devid']
        for _dev in getDevices(True):
            allowed_keys.append(_dev)
        for k, v in kwargs.items():
            if k not in allowed_keys:
                debug.write(
                    "Missing or unallowed variable in request: {}".format(k), 1)
        self.__dict__.update((k, v)
                             for k, v in kwargs.items() if k in allowed_keys)

    def from_string(self, json_str):
        if json_str is None or json_str == "":
            return False
        debug.write("Parsing request: {}".format(json_str), 0)
        try:
            _args = ast.literal_eval(json_str)
            self.set(**_args)
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

    def set_colors(self, colors, length):
        if self.colors is None:
            self.colors = [DEVICE_SKIP] * int(length)
        for i, _color in enumerate(colors):
            if self[i] != _color:
                self[i] = _color

    def validate_request(self, dm, config, called_on_run=False):
        debug.write("Validating arguments", 0)
        if self.reset_location_data:
            # TODO eventually add training data cleanup
            os.remove("../dnn/train.log")
            debug.write("Purged location and RTT data", 0)

        has_device_requests = False
        for _dev in getDevices(True):
            if getattr(self, _dev, None) is not None:
                has_device_requests = True
        if (self.colors is not None and len(self.colors) == len(dm.devices)) or self.set_mode_for_devid is not None:
            has_device_requests = True

        if self.hexvalues and has_device_requests:
            debug.write("Got color hexvalues for multiple devices in the same request, which is not \
                        supported. Use '{} -h' for help. Quitting".format(sys.argv[0]),
                        2)
            return False

        if len(self.hexvalues) != len(dm.devices) and not any([self.notime, self.off, self.on,
                                                               self.toggle, self.preset, self.restart,
                                                               self.group, has_device_requests,
                                                               self.force_auto_mode]):
            debug.write("Got {} color hexvalues, {} expected. Use '{} -h' for help. Quitting"
                        .format(len(self.hexvalues), len(dm.devices), sys.argv[0]), 2)
            return False
        if self.hexvalues:
            debug.write("Received color hexvalues length {} for {} devices"
                        .format(len(self.hexvalues), len(dm.devices)), 0)
            self.set_colors(self.hexvalues, len(dm.devices))
        else:
            if self.set_mode_for_devid is not None:
                try:
                    debug.write("Received mode change request for devid {}".format(
                        self.set_mode_for_devid), 0)
                except KeyError:
                    debug.write("Devid {} does not exist".format(
                        self.set_mode_for_devid), 1)
                    return False

            for _dev in getDevices(True):
                if getattr(self, _dev, None) is not None:
                    debug.write("Received {} change request".format(_dev), 0)
                    self.device_type = _dev
                    self.device_type_args = getattr(self, _dev, None)

            if self.preset is not None:
                debug.write(
                    "Received change to preset [{}] request".format(self.preset), 0)
                try:
                    preset_colors = config["PRESETS"][self.preset].split(',')
                    if len(preset_colors) != len(dm.devices):
                        debug.write("Preset '{}' does not have the adequate number of states, {} expected.".format(
                            self.preset, len(dm.devices)), 1)
                        return False
                    self.set_colors(
                        config["PRESETS"][self.preset].split(','), len(dm.devices))
                    self.auto_mode = config["PRESETS"].getboolean(
                        "AUTOMATIC_MODE")
                except KeyError:
                    debug.write(
                        "Preset '{}' not found in home.ini. Quitting.".format(self.preset), 3)
                    return False
            if self.off:
                debug.write("Received OFF change request", 0)
                self.set_colors(
                    [DEVICE_OFF] * len(dm.devices), len(dm.devices))
            if self.on:
                debug.write("Received ON change request", 0)
                self.set_colors([DEVICE_ON] * len(dm.devices), len(dm.devices))
            if self.restart:
                debug.write("Received RESTART change request", 0)
                self.device_type = "GenericOnOff"
                self.device_type_args = ["2"]
            if self.toggle:
                debug.write("Received TOGGLE change request", 0)
                self.set_colors(dm.get_toggle(), len(dm.devices))
        if self.notime or self.off:
            self.skip_time = True

        debug.write("Arguments are OK", 0)
        self.request_is_validated = True
        if not called_on_run:
            self(dm)
        return True

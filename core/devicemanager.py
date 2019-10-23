#!/usr/bin/env python3
'''
    File name: devicemanager.py
    Author: Maxime Bergeron
    Date last modified: 01/10/2019
    Python Version: 3.5

    The device and modules manager for the homeserver. Not a module per-se
'''
import datetime
import re
import subprocess
import time
import queue
from core.common import *
from core.convert import convert_to_web_rgb, convert_color
from multiprocessing.pool import ThreadPool
from threading import Timer


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
        self.colors = [DEVICE_SKIP] * len(self.devices)
        self.delays = [0] * len(self.devices)
        self.scheduled_changes = []
        self.states = self.get_state()
        self.skip_time = False
        debug.write("Got initial device states {}".format(self.states), 0)
        self.set_lock(0)
        self.lockcount = 0
        self.threaded = False
        self.light_threads = [None] * len(self.devices)
        self.light_pool = None
        self.all_groups = None
        self.modules = []

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
                    self.devices.append(_class(i, self.config))
                    self.get_and_link_pseudodevice(i)
                else:
                    debug.write('Unsupported device type {}'
                                .format(self.config["DEVICE" + str(i)]["TYPE"]), 1)
            except KeyError:
                debug.write('Loaded {} devices'.format(i), 0)
                break
            i = i + 1

    def start_threaded(self):
        """ Enables multithreaded light change requests """
        self.threaded = True
        self.light_pool = ThreadPool(processes=4)

    def set_serverwide_skiptime(self):
        """ Enables skipping time check all the time"""
        debug.write("Skipping time check for all requests", 0)
        self.always_skip_time = True

    def set_mode(self, auto_mode, reset_mode, device_id, force_auto_mode=False):
        for _device, _color in zip(self.devices, self.colors):
            if self.colors is not None and _color != DEVICE_SKIP:
                _device.request_auto_mode = auto_mode
                _device.reset_mode = reset_mode
            if force_auto_mode:
                _device.auto_mode = True
        if device_id is not None:
            self.devices[device_id].auto_mode = auto_mode
        if force_auto_mode:
            debug.write("All devices set to AUTO mode", 0)
        if reset_mode:
            debug.write("All non-skipped devices set back to AUTO mode", 0)

    def get_group(self, group):
        """ Gets devices from a specific group for the light change """
        if type(group) == str:
            group = [group]
        for _cnt, _device in enumerate(self.devices):
            if group is not None and set(group).issubset(_device.group):
                continue
            debug.write("Skipping device {} as it does not belong in the {} group(s)"
                        .format(_device.device, group), 0)
            self.colors[_cnt] = DEVICE_SKIP

    def get_toggle(self):
        """ Toggles the devices on/off """
        colors = [DEVICE_ON] * len(dm.devices)
        i = 0
        for color in self.get_state():
            if color != DEVICE_OFF:
                colors = [DEVICE_OFF] * len(dm.devices)
            i = i + 1
        return colors

    def set_typed_colors(self, colorargs, atype):
        """ Gets devices of a specific  type for the light change """
        self.colors = [DEVICE_SKIP] * len(self.devices)
        device_indexes = [i for i, x in enumerate(
            self.devices) if x.__class__.__name__.lower() == atype.lower()]

        if len(colorargs) == 1 and len(device_indexes) > 1:
            debug.write("Expanding state {} to {} devices."
                        .format(len(colorargs), len(device_indexes)), 0)
            for i in device_indexes:
                self.colors[i] = colorargs[0]
        elif len(device_indexes) != len(colorargs):
            debug.write("Received state hexvalues length {} for {} devices. Quitting"
                        .format(len(colorargs), len(device_indexes)), 2)
            return False
        else:
            for _cnt, i in enumerate(device_indexes):
                self.colors[i] = colorargs[_cnt]
        return True

    def run(self, request):
        """ Validates the request and runs the light change """
        if not request.request_is_validated and not request.validate_request(self, self.config, called_on_run=True):
            return
        self.clean_delayed_changes()

        if request.colors is not None:
            self.colors = request.colors
        else:
            self.colors = [DEVICE_SKIP] * len(self.devices)
        self.skip_time = request.skip_time
        self.set_mode(request.auto_mode, request.reset_mode,
                      request.set_mode_for_devid, request.force_auto_mode)
        if request.device_type is not None:
            self.set_typed_colors(
                request.device_type_args, request.device_type)
        if request.group is not None:
            self.get_group(request.group)

        if self.colors is not None:
            if request.delay is not 0:
                delay = request.delay
                debug.write(
                    "Delaying request for {} seconds".format(request.delay), 0)
                request.delay = 0
                _sched = Timer(int(delay), self.run, (request,))
                _sched.start()
                self.scheduled_changes.append(_sched)
                return
            if self.check_event_time(request.skip_time or self.always_skip_time):
                self.queue.put(self.colors)
                # TODO Manage locking out when the run thread hangs
                debug.write("Locked status: {}".format(self.locked), 0)
                if not self.locked or self.lockcount == 2:
                    self._set_lights()
                else:
                    self.lockcount = self.lockcount + 1

    def get_all_groups(self):
        if self.all_groups is None:
            _groups = []
            for obj in self.devices:
                for group in obj.group:
                    if group not in _groups:
                        _groups.append(group)
            self.all_groups = _groups
        return self.all_groups

    def get_descriptions(self, as_list=False):
        """ Getter for configured devices descriptions """
        desclist = []
        desctext = ""
        i = 1
        for obj in self.devices:
            desctext += str(i) + " - " + obj.descriptions() + "\n"
            if as_list:
                desclist.append(obj.descriptions())
            i += 1
        if as_list:
            return desclist
        return desctext

    def get_types(self):
        typelist = []
        for obj in self.devices:
            typelist.append(obj.__class__.__name__)
        return typelist

    def get_modes(self):
        modelist = []
        for obj in self.devices:
            modelist.append(obj.auto_mode)
        return modelist

    def get_names(self):
        namelist = []
        for obj in self.devices:
            if obj.name is not None:
                namelist.append(obj.name)
            else:
                # Fallback to device then device type
                try:
                    namelist.append(obj.device)
                except NameError:
                    namelist.append(obj.device_type)

        return namelist

    def get_option(self, option):
        oplist = []
        for obj in self.devices:
            if option == "skiptime":
                oplist.append(obj.default_skip_time)
            elif option == "forceoff":
                oplist.append(obj.forceoff)
            elif option == "ignoremode":
                oplist.append(obj.ignoremode)
            elif option == "actiondelay":
                oplist.append(obj.action_delay)
        return oplist

    def get_icons(self):
        iconlist = []
        for obj in self.devices:
            if obj.icon is not None:
                iconlist.append(obj.icon)
            else:
                iconlist.append("none")
        return iconlist

    def get_colortypes(self):
        ctypelist = []
        for obj in self.devices:
            ctypelist.append(obj.color_type)
        return ctypelist

    def get_module_web(self):
        weblist = []
        for obj in self.modules:
            try:
                weblist.append(obj.web)
            except AttributeError:
                weblist.append("none")
                pass
        return weblist

    def get_lock_status(self):
        locklist = []
        for obj in self.devices:
            if obj.request_locked:
                locklist.append("1")
            else:
                locklist.append("0")
        return locklist

    def get_room_for_devices(self):
        if self.config.has_option("WEBSERVER", "ROOM_GROUPS"):
            devrooms = []
            room_groups = self.config["WEBSERVER"]["ROOM_GROUPS"].split(",")
            for obj in self.devices:
                for group in obj.group:
                    if group in room_groups:
                        devrooms.append(group)
                        break
                else:
                    devrooms.append("")
        else:
            devrooms = [""] * len(self.devices)
        return devrooms

    def reload_configs(self):
        self.config.read('home.ini')
        for _dev in self.devices:
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

    def check_event_time(self, skip_time=False):
        now_time = datetime.datetime.now().time()
        self.update_event_time()
        for _dev in self.devices:
            _dev.set_event_time(self.starttime)
            if self.always_skip_time or skip_time:
                _dev.set_event_time(self.starttime, True)
            else:
                _dev.set_event_time(self.starttime)
        if not skip_time and datetime.time(6, 00) < now_time < self.starttime:
            for _device, _color in zip(self.devices, self.colors):
                if _color != DEVICE_SKIP and _device.get_time_check(now_time):
                    debug.write("Not all devices will be changed. Device changes begins at {}"
                                .format(self.starttime), 0)
                    return True
            debug.write("Too soon to change devices. Device changes begins at {}"
                        .format(self.starttime), 0)
            return False
        return True

    def set_lock(self, is_locked):
        """ Locks the light change request """
        self.locked = is_locked

    def get_state(self, devid=None, async=False, webcolors=False, intensity=False):
        """ Getter for configured devices actual colors """
        states = [None] * len(self.devices)
        for _cnt, dev in enumerate(self.devices):
            if devid is not None and devid != _cnt:
                continue
            if async:
                if intensity and self.devices[_cnt].color_type in ["argb", "rgb", "255"]:
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
            return states[devid]
        return states

    def set_light_stream(self, devid, color, is_group):
        """ Simplified function for quick, streamed light change requests """
        if is_group:
            for device in self.devices:
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
                if self.devices[devid].run(_color, 3):
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
        while i < len(self.devices):
            self.devices[i].post_run()
            i += 1

    def get_and_link_pseudodevice(self, devid):
        _pseudodev = self.devices[devid].has_pseudodevice
        if _pseudodev is not None:
            if _pseudodev not in self.pseudodevices:
                self.pseudodevices[_pseudodev] = self.devices[devid].create_pseudodevice(
                )
            self.devices[devid].get_pseudodevice(
                self.pseudodevices[_pseudodev])

    def _decode_colors(self, colors):
        _has_delays = False
        self.delays = [0] * len(self.devices)
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
                    _delay_colors = [DEVICE_SKIP] * len(self.devices)
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
                    req.set_colors(_delay_colors, len(self.devices))
                    if self.skip_time:
                        req.skip_time = True
                    debug.write("Scheduling device state change ({}) after {} seconds".format(
                        _delay_colors, _delay), 0)
                    _sched = Timer(int(_delay), self.run, (req,))
                    _sched.start()
                    self.scheduled_changes.append(_sched)
        return colors

    def _set_lights(self):
        debug.write("Running a change of states...", 0)
        self.lockcount = 0
        firstran = False
        try:
            while not self.queue.empty():
                colors = None
                if firstran:
                    debug.write("Getting remainder of queue", 0)
                    self.reinit()
                colors = self._decode_colors(
                    self.queue.get())  # TODO Check performance
                if all(c == DEVICE_SKIP for c in colors):
                    debug.write("All device requests skipped", 0)
                    break
                debug.write("Changing states to {} from state {}"
                            .format(colors, self.states), 0)
                self.set_lock(1)
                i = 0
                tries = 0
                firstran = True

                while i < len(self.devices):
                    if not self.devices[i].success:
                        _color = self.devices[i].convert(colors[i])

                        if _color != DEVICE_SKIP:
                            self.states[i] = self.get_state(i)
                            if _color != self.states[i]:
                                debug.write(("Device '{}', change {} => "
                                             "{} (Automatic mode: {})")
                                            .format(self.devices[i].name,
                                                    self.states[i], _color,
                                                    self.devices[i].auto_mode),
                                            0)
                        if self.threaded:
                            if not self.queue.empty():
                                break
                            self.light_threads[i] = self.light_pool.apply_async(self._set_device,
                                                                                args=(i, _color,))
                        else:
                            self._set_device(i, _color)
                    i += 1

                    if i == len(self.devices):
                        if self.threaded:
                            debug.write("Awaiting results", 0)
                            for _thread in self.light_threads:
                                if not self.queue.empty():
                                    break
                                if _thread is not None:
                                    try:
                                        if not _thread.ready() and _thread.get(5) is not None:
                                            i = 0
                                    except:
                                        # TODO is this still necessary ?
                                        i = 0
                            tries = tries + 1
                            if tries == 5:
                                break
                        else:
                            for _cnt, _dev in enumerate(self.devices):
                                if not self.queue.empty():
                                    break
                                self.states[_cnt] = self.get_state(_cnt)
                                if self.devices[_cnt].convert(colors[_cnt]) != self.states[_cnt] and not self.devices[_cnt].success:
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
            self.set_lock(0)
            if firstran:
                self.states = self.get_state()

        debug.write("Change of device states completed.", 0)

    def _set_device(self, count, color):
        return self.devices[count].pre_run(color)

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
        self.delays = []
        self.skip_time = False
        self.group = None
        self.device_type = None
        self.device_type_args = None
        self.auto_mode = False
        self.reset_mode = False
        self.force_auto_mode = False
        self.request_is_validated = False
        self.set(**kwargs)

    def set(self, **kwargs):
        allowed_keys = {'hexvalues', 'off', 'on', 'restart', 'toggle', 'group',
                        'notime', 'delay', 'preset', 'manual_mode', 'reset_location_data',
                        'force_auto_mode', 'auto_mode', 'reset_mode'}
        self.__dict__.update((k, v)
                             for k, v in kwargs.items() if k in allowed_keys)

    def run(self, dm):
        dm.run(self)

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

    def get_request_string(self):
        _str = ""
        for i, (_var, _chg) in enumerate(self.changed_vars.items()):
            if i != 0:
                _str += ", "
            _str += "{} will be set to {}".format(_var, _chg)
        return _str

    def set_colors(self, colors, length):
        if self.colors is None:
            self.colors = [DEVICE_SKIP] * int(length)
        for i, _color in enumerate(colors):
            if self.colors[i] != _color:
                self.colors[i] = _color

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
        if self.colors is not None and len(self.colors) == len(dm.devices):
            has_device_requests = True

        if self.hexvalues and has_device_requests:
            debug.write("Got color hexvalues for multiple devices in the same request, which is not \
                        supported. Use '{} -h' for help. Quitting".format(sys.argv[0]),
                        2)
            return False

        if len(self.hexvalues) != len(dm.devices) and not any([self.notime, self.off, self.on,
                                                               self.toggle, self.preset, self.restart,
                                                               self.group, has_device_requests]):
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
            self.run(dm)
        return True

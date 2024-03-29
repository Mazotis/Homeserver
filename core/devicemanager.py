#!/usr/bin/env python3
'''
    File name: devicemanager.py
    Author: Maxime Bergeron
    Date last modified: 29/03/2021
    Python Version: 3.8

    The device and modules manager for the homeserver. Not a module per-se
'''
import ast
import re
import time
import unidecode
try:
    import queue
except ImportError:
    import Queue as queue
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

    def __init__(self, threaded=False, dryrun=False):
        debug.get_set_lock()
        debug.enable_debug()
        self.running = False
        self.dryrun = dryrun
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
        self.all_groups = None
        self.get_devices_list()
        self.get_modules_list()
        self.lastupdate = None
        self.queue = queue.Queue()
        self.scheduled_changes = []
        self.scheduled_state_getters = []
        self.scheduled_disconnect = None
        self.threaded = threaded
        self.light_threads = [None] * len(self)
        self.light_pool = None
        self.skip_time = False
        self.state_threads = [None] * len(self)
        self.state_pool = None
        if self.dryrun:
            self.states = [DEVICE_OFF] * len(self)
            self.threaded = False
            debug.write("", 0)
            debug.write("****************************************************************", 0)
            debug.write("*** Starting a dry run. State changes and detection disabled ***", 0)
            debug.write("****************************************************************", 0)
            debug.write("", 0)
        else:
            self.states = self.get_state(_initial_call=True)
        self.status = self()
        self.running = True
        debug.write("Got initial device states {}".format(self.states), 0)

    def __len__(self):
        return len(self.devices)

    def __getitem__(self, position):
        return self.devices[position]

    def __setitem__(self, position, device):
        try:
            self.devices[position] = device
        except IndexError:
            self.devices.append(device)

    def __call__(self, is_async=True, sync_only_for_devid=None, sync_only_states=False):
        dm_status = {}
        dm_status["state"] = self.get_state(is_async=is_async, devid=sync_only_for_devid, webcolors=True)
        dm_status["intensity"] = self.get_intensity()
        dm_status["groupstates"] = self.get_group_states
        if self.has_module("timesched") is not False:
            #TODO Are they the same time or should they be distinct ?
            dm_status["sunrise"] = "{}".format(self.get_module("timesched").sunrise)
            dm_status["sunset"] = "{}".format(self.get_module("timesched").sunset)
            dm_status["starttime"] = "{}".format(self.get_module("timesched").default_event_hour)
            dm_status["endtime"] = "{}".format(self.get_module("timesched").default_event_hour_stop)
        else:
            dm_status["sunrise"] = False
            dm_status["sunset"] = False
            dm_status["starttime"] = "18:00"
            dm_status["endtime"] = "06:00"
        if not sync_only_states:
            dm_status["mode"] = self.modes
            dm_status["type"] = self.types
            dm_status["name"] = self.names
            for op in ["skiptime", "forceoff", "ignoremode", "actiondelay"]:
                dm_status["op_" + op] = self.get_option(op)
            dm_status["icon"] = self.icons
            dm_status["description"] = self.get_descriptions(
                True)

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
            dm_status["history"] = self.history
        self.status = dm_status
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
    def get_group_states(self):
        _group_states = []
        for _grp in self.all_groups:
            _state = "2"  # All on
            has_ons = False
            for obj in self:
                if _grp in obj.group:
                    if obj.state == DEVICE_DISABLED:
                        _state = "-1"
                        break
                    if obj.state == obj.convert(DEVICE_OFF):
                        if has_ons:
                            _state = "1"  # Partially on
                        else:
                            _state = "0"
                    else:

                        has_ons = True
                        if _state == "0":
                            _state = "1"
            _group_states.append(_state)
        return _group_states

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

    def get_toggle(self, requested_states):
        """ Toggles the devices on/off """
        states = requested_states
        for _cnt, _state in enumerate(self.get_state(is_async=True)):
            if requested_states[_cnt] == DEVICE_TOGGLE:
                if _state in [DEVICE_OFF, DEVICE_INFERRED_OFF]:
                    states[_cnt] = [DEVICE_ON]
                else:
                    states[_cnt] = [DEVICE_OFF]
        return states

    @property
    def history(self):
        historylist = []
        for obj in self:
            historylist.append(obj.get_history())
        return historylist

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
                    if self.dryrun:
                        self[i].dryrun = True
                    else:
                        self.get_and_link_pseudodevice(i)
                else:
                    debug.write('Unsupported device type {}'
                                .format(_devtype), 1)
            except KeyError:
                debug.write('Loaded {} devices'.format(i), 0)
                break
            i = i + 1

    def get_modules_list(self, load_single_module=None):
        _config = getConfigHandler()
        loaded_modules = _config['SERVER']['MODULES'].split(",")

        for _mod in _config.configurables.find("modules").findall("module"):
            if _mod.find("conflicts") is not None:
                if _mod.find("conflicts").text in loaded_modules and _mod.attrib["name"] in loaded_modules:
                    debug.write("You cannot load {} and {} at the same time. Quitting.".format(
                        _mod.attrib["name"], _mod.find("conflicts").text), 2)
                    sys.exit()

        if load_single_module is None:
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
        else:
            if load_single_module in getModules():
                _module = __import__("modules." + load_single_module)
                # TODO Needed twice ? looks unpythonic
                _class = getattr(_module, load_single_module)
                _class = getattr(_class, load_single_module)
                self.modules.append(_class(self))
                self.modules[-1].start()

    def has_module(self, module_name):
        for _index, _mod in enumerate(self.modules):
            if _mod.__class__.__name__ == module_name and _mod.isAlive():
                return _index
        return False

    def get_module(self, module_name):
        for _mod in self.modules:
            if _mod.__class__.__name__ == module_name and _mod.isAlive():
                return _mod
        return None

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

    def set_history_origin(self, origin):
        for _dev in self:
            _dev.history_origin = origin

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
                if self.has_module("timesched") is not False:
                    if int(obj.devid) in self.get_module("timesched").tracked_devices_times:
                        oplist.append(True)
                        continue
                oplist.append(False)
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

    def shutdown_modules(self, remove_single_module=None):
        if remove_single_module is None:
            for _cnt, _mod in enumerate(self.modules):
                try:
                    _mod.stop()
                except NameError:
                    pass
        else:
            try:
                self.get_module(remove_single_module).stop()
            except NameError:
                pass
            try:
                self.modules.remove(self.get_module(remove_single_module))
            except ValueError:
                debug.write("{} not in list {}".format(self.get_module(remove_single_module), self.modules), 2)

    def get_state(self, devid=None, is_async=False, webcolors=False, 
                  _for_state_change=False, _initial_call=False):
        """ Getter for configured devices actual colors """
        if state_lock.locked() and devid is None:
            # There's most likely another SYNC state getter running
            is_async = True
        if not _for_state_change:
            while lock.locked():
                # Do not run state checks while there are state changes ?
                time.sleep(0.2)
        with state_lock:
            old_states = [None] * len(self)
            states = [None] * len(self)
            if self.threaded:
                max_workers = len(self)
                self.state_pool = ThreadPoolExecutor(max_workers=max_workers)
            for _cnt, dev in enumerate(self):
                if devid is not None and devid != _cnt:
                    continue
                if is_async and dev.state_getter_mode != "always" and dev.state != DEVICE_STANDBY:
                    states[_cnt] = dev.state
                else:
                    old_states[_cnt] = dev.state

                    if dev.state_getter_mode in ["always","normal"] or (dev.state_getter_mode == "init" and _initial_call):
                        if self.threaded and devid is None:
                            self.state_threads[_cnt] = self.state_pool.submit(dev.get_state_pre)
                        else:
                            states[_cnt] = dev.get_state_pre()
                    else:
                        states[_cnt] = dev.state

            for _cnt, dev in enumerate(self):
                if devid is not None and devid != _cnt:
                    continue
                if (not is_async or dev.state_getter_mode == "always") or not self.dryrun:
                    if dev.state_getter_mode in ["always","normal"] or (dev.state_getter_mode == "init" and _initial_call):
                        if self.threaded:
                            states[_cnt] = self.state_threads[_cnt].result()
                        if old_states[_cnt] is not None and states[_cnt] is not None:
                            if dev.convert(old_states[_cnt]) != dev.convert(states[_cnt]) and DEVICE_STANDBY not in [old_states[_cnt], states[_cnt]] and not _initial_call and DEVICE_DISABLED not in [old_states[_cnt], states[_cnt]]:
                                debug.write("Device {} state changed ({} -> {}) without involvement of the Homeserver. Consider as a MANUAL change".format(dev.name, old_states[_cnt], states[_cnt]), 0)
                                dev.auto_mode = False

                if webcolors:
                    states[_cnt] = convert_to_web_rgb(states[_cnt], dev.color_type, dev.color_brightness)

            for _cnt, dev in enumerate(self):
                # Has to be called after device states all updated ? Only relevant on non-async requests ?
                if self[_cnt].state_inference_group is not None:
                    states[_cnt] = self[_cnt].get_inferred_group_state(self)

        if self.threaded and not self.dryrun:
            self.state_pool.shutdown()

        if _for_state_change:
            return states[devid]

        if not is_async:
            debug.write("All devices state status updated in real-time", 0)

        return states

    def get_intensity(self):
        intensity = [None] * len(self)
        for _cnt, dev in enumerate(self):
            if self[_cnt].color_type in ["argb", "rgb", "255"]:
                intensity[_cnt] = convert_color(dev.state, "100")
            else:
                intensity[_cnt] = "null"
        return intensity


    def clean_delayed_changes(self):
        for _sched in self.scheduled_changes:
            if _sched is not None and not _sched.isAlive():
                self.scheduled_changes.remove(_sched)
        for _sched in self.scheduled_state_getters:
            if _sched is not None and not _sched.isAlive():
                self.scheduled_state_getters.remove(_sched)

    def stop_delayed_changes(self):
        self.clean_delayed_changes()
        for _sched in self.scheduled_changes:
            if _sched is not None:
                _sched.cancel()
        for _sched in self.scheduled_state_getters:
            if _sched is not None:
                _sched.cancel()

    def reinit(self):
        """ Resets the Success bool to False """
        i = 0
        while i < len(self):
            self[i].post_run()
            i += 1

    def get_and_link_pseudodevice(self, devid):
        if self.dryrun:
            return
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
        if self.dryrun:
            return
        for _dev in self:
            _dev.disconnect()

    def disconnect_pseudodevices(self):
        debug.write("Server shutting down. Disconnecting pseudodevices.", 0)
        if self.dryrun:
            return
        for _pdev in self.pseudodevices.values():
            _pdev.disconnect()

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

                    self._delayed_request(request, _delay_colors, _delay)
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
        scheduled_getters = {}
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
                if self.has_module("timesched") is not False:
                    self.get_module("timesched").check_event_time(_req, _req.skip_time)
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

                        if _color not in [DEVICE_SKIP, DEVICE_STANDBY, DEVICE_DISABLED]:
                            self.states[i] = self.get_state(
                                devid=i, _for_state_change=True)
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
                            #TODO should this ignore faulty devices?
                            if self[i].action_delay != 0:
                                scheduled_getters[i] = self[i].action_delay

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
                                            if tries != 4:
                                                debug.write("Repeating failed request for device: {} ({})".format(
                                                    self[_cnt].name, self[_cnt].device_type), 1)
                                            self[_cnt].interrupt.acquire()
                                            while not _thread.done():
                                                time.sleep(0.5)
                                            self[_cnt].interrupt.release()
                                            _thread = None
                                            i = 0
                                    except NewRequestException:
                                        debug.write(
                                            "Sent exception for new request", 3)
                                        break
                                    except TimeoutError:
                                        debug.write(
                                            "Request timed-out for device: {}".format(self[_cnt].name), 1)
                                        self[_cnt].interrupt.acquire()
                                        while not _thread.done():
                                            time.sleep(0.5)
                                        self[_cnt].interrupt.release()
                                        _thread = None
                                        i = 0
                        else:
                            for _cnt, _dev in enumerate(self):
                                if not self.queue.empty():
                                    break
                                _color = self[_cnt].convert(colors[_cnt])
                                if not self[_cnt].success and _color not in [DEVICE_SKIP, DEVICE_STANDBY, DEVICE_DISABLED]:
                                    debug.write("Device {} ({}) success bool off".format(
                                        _cnt, self[_cnt].name), 1)
                                    i = 0
                        tries = tries + 1
                        if tries == 5:
                            debug.write(
                                "Failed to change all states. Aborting", 1)
                            for _cnt, _dev in enumerate(self):
                                if not _dev.success and colors[_cnt] not in [DEVICE_SKIP, DEVICE_DISABLED, DEVICE_STANDBY]:
                                    if _dev.retry_delay_on_failure > 0 and not _dev.check_for_repeating_failures():
                                        debug.write("Retrying state change for device {} in {} seconds".format(_dev.name, _dev.retry_delay_on_failure), 1)
                                        _colors = [DEVICE_SKIP] * len(self)
                                        _colors[_cnt] = self[_cnt].convert(colors[_cnt])
                                        self._delayed_request(_req, _colors, _dev.retry_delay_on_failure)
                                    _dev.set_failed_history()
                            break

        except queue.Empty:
            debug.write("Nothing in queue", 3)
            pass

        finally:
            debug.write("State getters: {}".format(scheduled_getters), 1)
            debug.write("Clearing up device change queues", 0)
            if colors:
                self.queue.task_done()
            self.reinit()
            self.scheduled_disconnect = Timer(60, self.disconnect_devices, ())
            self.scheduled_disconnect.start()
            for devid, timer in scheduled_getters.items():
                # TODO needed to add an extra 1 second to make sure that the getter passes ?
                _sched = Timer(int(timer+1), self.get_state, (), {"devid": devid, "is_async": False})
                _sched.start()
                self.scheduled_state_getters.append(_sched)
            if self.threaded:
                self.light_pool.shutdown(True)
                lock.release()
                ExecutionState().set(False)
                # Let the Webserver some time to fetch single device state changes results
                time.sleep(0.5)
                self.states = self.get_state()
            else:
                lock.release()
                ExecutionState().set(False)

        debug.write("Change of device states completed.", 0)

    def _merge_requests(self, new_request, old_request):
        for _cnt, _color in enumerate(old_request.colors):
            if new_request[_cnt] == DEVICE_SKIP and _color != DEVICE_SKIP:
                new_request[_cnt] = _color
                if old_request.skip_time and not new_request.skip_time:
                    self[_cnt].skip_time = True
        return new_request

    def _delayed_request(self, old_request, colors, delay):
        delayed_req = StateRequestObject()
        delayed_req.initialize_dm(self)
        delayed_req.set(history_origin="Scheduler")
        delayed_req.from_request(old_request)
        delayed_req.set_colors(colors)
        debug.write("Scheduling device state change ({}) after {} seconds".format(colors, delay), 0)
        _sched = Timer(int(delay), delayed_req.run, ())
        _sched.start()
        self.scheduled_changes.append(_sched)


class StateRequestObject(object):
    """ Methods for properly handling devicemanager state change requests """

    def __init__(self, **kwargs):
        self.hexvalues = []
        self.group = None
        self.off = False
        self.on = False
        self.restart = False
        self.toggle = False
        self.notime = False
        self.delay = 0
        self.preset = None
        self.manual_mode = False
        self.set_mode_for_devid = None
        self.reset_location_data = False
        self.history_origin = "Unknown"
        self.changed_vars = {}

        """ Initialization data """
        self.length = 0
        self.config = None
        self.device_types = []
        self.device_groups = []

        """ Vars for the completed request, used by the devicemanager directly """
        self.colors = None
        self.skip_time = False
        self.device_type = None
        self.device_type_args = None
        self.auto_mode = False
        self.reset_mode = False
        self.force_auto_mode = False
        self.debug_wait = []
        self.set(**kwargs)

    def __call__(self):
        self.run()

    def __str__(self):
        _str = ""
        if len(self.changed_vars.items()) == 0:
            return "* No changes requested *"
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

    def __setattr__(self, name, value):
        ''' Checks for collisions or undefined behaviour in variable settings '''
        if value not in [None, 0, [], {}, "Unknown"] and name not in ['dm', 'length', 'config'] and self.check_for_initialization():
            if name == "hexvalues" and len(value) != self.length:
                debug.write("Got {} color hexvalues, {} expected. Use '{} -h' for help. Skipping".format(
                    len(value), self.length, sys.argv[0]), 2)
                return
            if name == "preset" and not dm.config.has_option("PRESETS", value):
                debug.write(
                    "Preset '{}' not found in home.ini. Skipping.".format(value), 3)
                return
            if name == "set_mode_for_devid" and value > self.length:
                debug.write(
                    "Devid {} does not exist. Skipping".format(value), 3)
                return

        super().__setattr__(name, value)

    def set(self, **kwargs):
        allowed_keys = ['hexvalues', 'off', 'on', 'restart', 'toggle', 'group',
                        'client', 'notime', 'delay', 'preset', 'manual_mode',
                        'reset_location_data', 'force_auto_mode', 'auto_mode',
                        'reset_mode', 'skip_time', 'set_mode_for_devid',
                        'history_origin']
        ignored_keys = ['nowait', 'update', 'init_from', 'configure']
        for _dev in getDevices(True):
            allowed_keys.append(_dev)
        for k, v in kwargs.items():
            k = k.replace("-", "_")
            if k in ignored_keys:
                continue
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

            if k == "hexvalues":
                self.debug_wait.append("Got state changes from hexvalues: {}".format(v))
                if len(v) == 1 and self.length > 1 and ":" not in v[0]:
                    self.colors = v * self.length
                else:
                    for _cnt, _col in enumerate(v):
                        if ":" in _col:
                            _vals = _col.split(":")
                            if int(_vals[0]) < len(self.colors):
                                self[int(_vals[0])] = _vals[1]
                        else:
                            self[_cnt] = _col

            # TODO Allow matching these to non-groups changes ?
            if k == "off":
                self.debug_wait.append("Received OFF change request")
                self.colors = [DEVICE_OFF] * self.length
            if k == "on":
                self.debug_wait.append("Received ON change request")
                self.colors = [DEVICE_ON] * self.length
            if k == "restart":
                self.debug_wait.append("Received RESTART change request")
                self.set_typed_colors("GenericOnOff", "2", self)
            if k == "toggle":
                self.debug_wait.append("Received TOGGLE change request. Setting all non-SKIPPED devices to toggle their state")
                for _pos, _color in enumerate(self.colors):
                    if _color != DEVICE_SKIP:
                        self.colors[_pos] = DEVICE_TOGGLE

            for _dev in getDevices(True):
                if k == _dev and v is not None:
                    self.debug_wait.append("Received {} change request".format(_dev.capitalize()))
                    self.set_typed_colors(_dev.capitalize(), v, self)

            if k == "group" and v is not None:
                self.get_group(v)
            if k == "preset" and v is not None:
                self.get_preset(v)
            if k not in ['client', 'history_origin']:
                if k in getDevices(True):
                    if v is not None:
                        self.changed_vars[k] = v
                        continue
                elif getattr(self, k, False) != v:
                    self.changed_vars[k] = v
                    continue

        self.__dict__.update((k, v)
                             for k, v in kwargs.items() if k in allowed_keys)
        return True

    def from_request(self, request):
        '''
        Create new request from old request, keeping only the
        options and parameters not related to requested state
        values
        '''
        ignore_vars = ['devices', 'changed_vars', 'dm', 'hexvalues',
                       'length', 'devices', 'colors', 'preset', 
                       'init_from']
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
        # Prioritize order of operations
        first_run = ['on', 'off', 'restart', 'hexvalues']
        second_run = ['group', 'preset']
        for _arg in vars(args):
            if _arg in first_run:
                if getattr(self, _arg, False) != vars(args)[_arg]:
                    self.set(**{ k:v for k,v in vars(args).items() if _arg in k })
        for _arg in vars(args):
            if _arg in second_run:
                if getattr(self, _arg, False) != vars(args)[_arg]:
                    self.set(**{ k:v for k,v in vars(args).items() if _arg in k })
        for _arg in vars(args):
            if _arg not in first_run and _arg not in second_run:
                if getattr(self, _arg, False) != vars(args)[_arg]:
                    self.set(**{ k:v for k,v in vars(args).items() if _arg in k })
        for _dev in getDevices(True):
            if type(getattr(self, _dev, None)) == "str":
                debug.write(
                    'Converting values to lists for {}'.format(_dev), 0)
                setattr(self, _dev, str(
                    getattr(self, _dev, None).replace("'", "").split(',')))

    def initialize(self, dm=None, config=None):
        if dm is not None:
            self.length = len(dm.devices)
            self.config = dm.config
            self.device_types = [x.device_type for x in dm.devices]
            self.device_groups = [x.group for x in dm.devices]
            if self.colors is None:
                self.colors = [DEVICE_SKIP] * int(self.length)
            return True
        elif config is not None:
            self.config = config
            self._initialize_from_config()
            if self.colors is None:
                self.colors = [DEVICE_SKIP] * int(self.length)
            return True
        else:
            debug.write("Missing initialization data either from DM or from the config file. Quitting.", 2)
            quit()

    def initialize_dm(self, dm):
        """ Fetches the required variables from the devicemanager """
        return self.initialize(dm=dm)

    def set_colors(self, colors):
        if self.check_for_initialization():
            for i, _color in enumerate(colors):
                if self[i] != _color:
                    self[i] = _color

    def set_color_for_devid(self, color, devid):
        if self.check_for_initialization():
            if self[devid] != color:
                self[devid] = color

    def set_color_for_groups(self, color, groups):
        if self.check_for_initialization():
            if type(groups) == str:
                groups = [groups]
            for _cnt, _gr in enumerate(groups):
                groups[_cnt] = unidecode.unidecode(_gr.lower())
            for _cnt, _device in enumerate(self.device_groups):
                if set(groups).issubset([unidecode.unidecode(x) for x in _device.group]):
                    self[_cnt] = color

    def set_typed_colors(self, device_type, device_args, colors):
        """ Gets devices of a specific  type for the light change """
        if self.check_for_initialization():
            device_indexes = [i for i, x in enumerate(
                self.device_types) if x.lower() == device_type.lower()]
            if type(device_args) == str:
                device_args = [device_args]
            if len(device_args) > len(device_indexes):
                debug.write("Got {} states for only {} device(s) of type '{}'. Quitting.".format(len(device_args), len(device_indexes), device_type), 1)
                return False

            if len(device_args) == 1 and len(device_indexes) > 1:
                self.debug_wait.append("Expanding state {} to {} ({}) devices."
                            .format(len(device_args), len(device_indexes), device_type))
                device_args = device_args[0] * len(device_indexes)
            elif len(device_indexes) != len(device_args):
                debug.write("Received state hexvalues length {} ({}) for {} '{}' device(s). Considering last devices as skipped.".format(
                    len(device_args), device_args, len(device_indexes), device_type), 0)

            for _cnt, i in enumerate(device_indexes):
                if _cnt < len(device_args):
                    self[i] = device_args[_cnt]
        return False

    def run(self):
        for _debug in self.debug_wait:
            debug.write(_debug, 0)
        request_queue.put(self)

    def has_requested_changes(self):
        if len(self.changed_vars) == 0:
            return False
        return True

    def check_for_initialization(self):
        if (self.length is None or self.config is None) and not hasattr(self, 'client'):
            debug.write(
                "ERROR - You need to initialize the request using initialize() or initialize_dm() first", 2)
            return False
        return True

    def get_group(self, group):
        """ Sets devices from a specific group for state change """
        if self.check_for_initialization():
            if type(group) == str:
                group = [group]
            for _cnt, _gr in enumerate(group):
                group[_cnt] = unidecode.unidecode(_gr.lower())
            _has_devices = False
            for _cnt, _group in enumerate(self.device_groups):
                if _group is None:
                    continue
                if not set(group).issubset([unidecode.unidecode(x) for x in _group]):
                    self[_cnt] = DEVICE_SKIP
                else:
                    if not _has_devices:
                        self.debug_wait.append("Got the following device types from the {} group(s):".format(group))
                        _has_devices = True
                    self.debug_wait.append("\tDevice '{}'".format(self.device_types[_cnt]))

    def get_preset(self, preset):
        if self.check_for_initialization():
            self.debug_wait.append(
                "Received change to preset [{}] request".format(preset))
            if not self.from_string(self.config["PRESETS"][preset]):
                debug.write("Preset does not exist. Ignoring", 1)
                return False
            self.auto_mode = self.config["PRESETS"].getboolean("AUTOMATIC_MODE")

    def _initialize_from_config(self):
        i = 0
        while True:
            try:
                _devtype = self.config.get_device(i, "TYPE")
                try:
                    _devgroup = self.config.get_device(i, "GROUP")
                except KeyError:
                    _devgroup = None
                if _devtype in getDevices():
                    self.device_types.append(_devtype)
                    try:
                        self.device_groups.append(_devgroup.split(","))
                    except AttributeError:
                        self.device_groups.append(["NO-GROUP"])
                else:
                    debug.write('Unsupported device type {}'
                                .format(_devtype), 1)
            except KeyError:
                self.length = i
                break
            i = i + 1


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
        if not request.check_for_initialization():
            request.initialize_dm(dm)
        dm.clean_delayed_changes()
        dm.set_history_origin(request.history_origin)

        if request.notime or request.off:
            request.skip_time = True
        dm.skip_time = request.skip_time

        if request.set_mode_for_devid is not None:
            debug.write("Received mode change request for devid {}".format(
                request.set_mode_for_devid), 0)

        if request.reset_location_data:
            # TODO eventually add training data cleanup
            os.remove("../dnn/train.log")
            debug.write("Purged location and RTT data", 0)

        dm.set_mode(request)

        # Handle state toggling
        # TODO extensive testing to see if this always works 
        request.colors = dm.get_toggle(request.colors)

        if request.delay is not 0:
            delay = request.delay
            debug.write(
                "Delaying request for {} seconds".format(delay), 0)
            request.set(delay=0, preset=None)
            _sched = Timer(int(delay), self.execute, (request, dm,))
            _sched.start()
            dm.scheduled_changes.append(_sched)
            return
        debug.write("Locked status: {}".format(lock.locked()), 0)
        dm.queue.put(request)
        if not lock.locked():
            Thread(target=dm._set_lights).start()
        elif dm.threaded:
            for _cnt, _thread in enumerate(dm.light_threads):
                if _thread is not None and not _thread.done():
                    dm[_cnt].interrupt.acquire()
                    while not _thread.done():
                        time.sleep(0.5)
                    dm[_cnt].interrupt.release()

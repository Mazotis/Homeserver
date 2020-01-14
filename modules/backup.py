#!/usr/bin/env python3
'''
    File name: backup.py
    Author: Maxime Bergeron
    Date last modified: 19/11/2019
    Python Version: 3.5

    A backup manager/rsync wrapper module for the homeserver
'''

import os
import queue
import shlex
import signal
import subprocess
from core.common import *
from core.devicemanager import StateRequestObject
from configparser import NoOptionError
from datetime import datetime, timedelta
from threading import Thread, Event


class backup(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.init_from_config()
        self.dm = dm
        self.stopevent = Event()
        self.last_backup = 0
        self.running = True
        self.rsync = None
        self.web = "backup.html"
        self.backup_queue = queue.Queue()

    def run(self):
        debug.write("Starting backup manager", 0, "BACKUP")
        if self.backup_server != "local":
            if int(self.backup_server) > len(self.dm):
                debug.write("DEVICE{} is not valid. Quitting module".format(
                    self.backup_server), 2, "BACKUP")
                self.stop()
                return
            if self.dm[int(self.backup_server)].device_type != "Computer":
                debug.write("DEVICE{} ({}) is not listed as Computer device in the Devicemanager. Quitting module"
                            .format(self.backup_server, self.dm[int(self.backup_server)].name), 2, "BACKUP")
                self.stop()
                return

        self.run_backup()
        _next_run = self.last_backup + timedelta(hours=self.backup_interval)
        debug.write("Will do another backup at: {}".format(_next_run.strftime('%d %B, %H:%M')),
                    0, "BACKUP")
        while not self.stopevent.is_set():
            if _next_run > datetime.now():
                if not self.backup_queue.empty():
                    needs_backup = self.backup_queue.get()
                    self.run_backup(needs_backup)
                    self.backup_queue.task_done()
                self.stopevent.wait(60)
                continue
            self.run_backup()
            _next_run = self.last_backup + \
                timedelta(hours=self.backup_interval)
            debug.write("Will do another backup at: {}".format(_next_run.strftime('%d %B, %H:%M')),
                        0, "BACKUP")
        debug.write("Stopped.", 0, "BACKUP")
        return

    def run_backup(self, clientid=None):
        self.last_backup = datetime.now()
        debug.write("Starting backups", 0, "BACKUP")
        backup_server = None
        server_was_off = False
        if self.backup_server != "local":
            backup_server = self.dm[int(self.backup_server)]
            if str(backup_server.get_state()) != DEVICE_ON:
                if self.config.get_value("BACKUP_SERVER_FORCE_ON", bool):
                    server_was_off = True
                    debug.write("Turning on backup server", 0, "BACKUP")
                    self.change_state_for_device(self.backup_server, DEVICE_ON)

                    while str(backup_server.get_state()) != DEVICE_ON:
                        debug.write(
                            "Waiting for backup server...", 0, "BACKUP")
                        self.stopevent.wait(5)
                else:
                    debug.write(
                        "Backup server is offline and no FORCE_ON. Reporting backups.", 0, "BACKUP")
                    return

        i = 0
        while self.running:
            if clientid is not None and clientid != i:
                if i > clientid:
                    break
                continue
            try:
                destination = ""
                if not self.config.has_option("BACKUP", "CLIENT" + str(i)):
                    break
                if self.config["CLIENT" + str(i)] != "local":
                    client = self.dm[self.config.get_value(
                        "CLIENT" + str(i), int)]
                    client_was_off = False
                    if str(client.get_state()) != DEVICE_ON:
                        if self.config.get_value("CLIENT" + str(i) + "_FORCE_ON", bool):
                            client_was_off = True
                            debug.write(
                                "Turning ON CLIENT{}".format(i), 0, "BACKUP")
                            self.change_state_for_device(
                                self.config.get_value("CLIENT" + str(i), int), DEVICE_ON)

                            while str(client.get_state()) != DEVICE_ON:
                                debug.write(
                                    "Waiting for client...", 0, "BACKUP")
                                self.stopevent.wait(5)
                        else:
                            debug.write(
                                "Skipping CLIENT{}, device is offline.".format(i), 0, "BACKUP")
                            i = i + 1
                            continue

                debug.write('Backing up client: {}'.format(
                    client.name), 0, "BACKUP")
                if self.backup_server != "local" and self.backup_server != self.config["CLIENT" + str(i)]:
                    destination = "{}@{}:{}".format(
                        backup_server.user, backup_server.ip, self.config["CLIENT" + str(i) + "_DESTINATION"])
                else:
                    destination = self.config["CLIENT" +
                                              str(i) + "_DESTINATION"]

                folders = []
                folders = self.config["CLIENT" +
                                      str(i) + "_FOLDERS"].split(",")
                for _folder in folders:
                    command = ""
                    if self.config.get_value("CLIENT" + str(i) + "_DELETE", bool):
                        command = "/usr/bin/rsync -az --delete"
                    else:
                        command = "/usr/bin/rsync -az"
                    if client == "local":
                        command = "{} {} {}".format(
                            command, _folder, destination)
                    else:
                        if self.backup_server != "local":
                            command = "/usr/bin/ssh -T {}@{} '{} {} {}'".format(
                                client.user, client.ip, command, _folder, destination)
                        else:
                            command = "{} {}@{}:{} {}".format(
                                command, client.user, client.ip, _folder, destination)

                    debug.write('Backing up folder {}'.format(
                        _folder), 0, "BACKUP")
                    debug.write('Running rsync command: {}'.format(
                        command), 0, "BACKUP")

                    # TODO handle keyboardinterrupts properly ?
                    self.rsync = subprocess.Popen(shlex.split(command), stdout=None,
                                                  preexec_fn=os.setsid, stdin=None)
                    self.rsync.wait()
                    self.rsync = None
                    if not self.running:
                        return

                if client_was_off:
                    debug.write(
                        "Turning back OFF CLIENT{}".format(i), 0, "BACKUP")
                    self.change_state_for_device(self.config.get_value(
                        "CLIENT" + str(i), int), DEVICE_OFF)

            except KeyError:
                debug.write('Backups are done', 0, "BACKUP")
                break

            i = i + 1

        if clientid is not None:
            debug.write('Backups are done', 0, "BACKUP")

        if server_was_off:
            debug.write(
                "Turning back OFF backup server".format(i), 0, "BACKUP")
            self.change_state_for_device(self.backup_server, DEVICE_OFF)
        return

    def change_state_for_device(self, devid, state):
        req = StateRequestObject()
        req.initialize_dm(self.dm)
        _col = [DEVICE_SKIP] * len(self.dm)
        _col[int(devid)] = state
        req.set_colors(_col)
        req.set(skip_time=True, auto_mode=False)
        req()

    def init_from_config(self):
        self.config = getConfigHandler().set_section("BACKUP")
        self.backup_interval = self.config.get_value(
            "DELAY_BETWEEN_BACKUPS", int)
        self.backup_server = self.config["BACKUP_SERVER"]
        self.backup_server_forceon = self.config.get_value(
            "BACKUP_SERVER_FORCE_ON", bool)

    def stop(self):
        debug.write("Stopping.", 0, "BACKUP")
        self.running = False
        if self.rsync is not None:
            debug.write("Killing remaining backup.", 0, "BACKUP")
            os.killpg(os.getpgid(self.rsync.pid), signal.SIGTERM)
        self.stopevent.set()
        return

    def get_web(self):
        web = """
<table class="table table-dark table-striped table-bordered">
  <thead>
    <tr>
      <th scope="col">#</th>
      <th scope="col">Device name</th>
      <th class="d-none d-md-table-cell" scope="col">Folders</th>
      <th scope="col"></th>
    </tr>
  </thead>
  <tbody> """
        i = 0
        has_devices = False
        while True:
            try:
                client = self.dm.devices[self.config.get_value(
                    "CLIENT" + str(i), int)]
                web += '<tr><th scope="row">{}</th>'.format(i + 1)
                web += '<td>{}</td>'.format(client.name)
                web += '<td class="d-none d-md-table-cell" style="font-size:x-small;">{}</td>'.format(
                    self.config["CLIENT" + str(i) + "_FOLDERS"].replace(',', ', '))
                web += '<td><center><button id="backupbtn{}" type="button" class="btn btn-warning" onclick="doBackup({})">Backup</button></center></td></tr>'.format(
                    i, i)
                has_devices = True
            except NoOptionError:
                break
            i = i + 1
        if not has_devices:
            web += '<tr><th rowspan="3">No backup devices configured</th></tr>'
        web += "</tbody></table>"
        return web

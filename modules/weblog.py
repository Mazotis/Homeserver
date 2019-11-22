#!/usr/bin/env python3
'''
    File name: weblog.py
    Author: Maxime Bergeron
    Date last modified: 31/10/2019
    Python Version: 3.5

    A web debug log access tool module
'''

from core.common import *
from threading import Thread


class weblog(Thread):
    def __init__(self, dm):
        Thread.__init__(self)
        self.init_from_config()
        self.running = True
        self.rsync = None
        self.web = "weblog.html"

    def run(self):
        debug.write("Starting web debug log access module", 0, "WEBLOG")
        pass

    def stop(self):
        debug.write("Stopped.", 0, "WEBLOG")
        self.running = False
        pass

    def init_from_config(self):
        self.config = HOMECONFIG

    def get_web(self, level="all"):
        web = """
<style>
#debugarea {
    font-size:small;
    width:100%;
    height:150px;
    font-family:monospace,serif;
    background-color:black;
    color:white;
}
</style>
        """
        with open(self.config['SERVER']['JOURNAL_DIR'] + "/home.0.log", "r") as jfile:
            _logfile = jfile.readlines()
        _logstr = ""
        for _line in _logfile:
            if level == 'all' or "[" + level.upper() + "]" in _line:
                _logstr += _line
        if _logstr == "":
            _logstr = "- No logs found for this level -"
        web += '<textarea id="debugarea">{}</textarea>'.format(_logstr)
        return web

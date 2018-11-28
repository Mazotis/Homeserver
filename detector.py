#!/usr/bin/env python3
"""
Simple playserver device detector
"""
import os
import time
import datetime

DETECTION_HOUR = 18
DEVICE_MAC = ["40:4E:36:87:0B:51", "40:4E:36:87:0B:89"]
DEVICE_STATUS = [0]*len(DEVICE_MAC)
STATUS = 0
DELAYED_START = 0

class LightManager(object):
    """ Methods for instanciating and managing BLE lightbulbs """
    @staticmethod
    def debugger(msg, level):
        """ Handles debug logging """
        levels = {0: "DEBUG", 1: "ERROR", 2: "FATAL"}
        debugtext = "({}) - [{}] {}".format(datetime.datetime.now().time(), levels[level], msg)
        print(debugtext)
        with open("./detector.0.log", "a") as jfile:
            jfile.write(debugtext + "\n")

if os.path.isfile("./detector.0.log"):
    if os.path.isfile("./detector.1.log"):
        if os.path.isfile("./detector.2.log"):
            os.remove("./detector.2.log")
        os.rename("./detector.1.log", "./detector.2.log")
    os.rename("./detector.0.log", "./detector.1.log")

for _cnt, device in enumerate(DEVICE_MAC):
    if os.system("wl assoclist | grep {} > /dev/null".format(device)):
        DEVICE_STATUS[_cnt] = 0
    else:
        DEVICE_STATUS[_cnt] = 1
LightManager.debugger("Got initial states {} and status {}".format(DEVICE_STATUS, STATUS), 0)
while True:
    try:
        for _cnt, device in enumerate(DEVICE_MAC):
            if os.system("wl assoclist | grep {} > /dev/null".format(device)):
                if DEVICE_STATUS[_cnt] == 1:
                    LightManager.debugger("DEVICE {} DISconnected".format(device), 0)
                DEVICE_STATUS[_cnt] = 0
            else:
                if DEVICE_STATUS[_cnt] == 0:
                    LightManager.debugger("DEVICE {} CONnected".format(device), 0)
                DEVICE_STATUS[_cnt] = 1

        if STATUS == 1 and all(s == 0 for s in DEVICE_STATUS):
            LightManager.debugger("STATE changed to {} and DELAYED_START {}, turned off" \
                                  .format(DEVICE_STATUS, DELAYED_START), 0)
            os.system('./playclient.py --off --notime --priority 3')
            STATUS = 0
            DELAYED_START = 0
        if datetime.datetime.now().hour == DETECTION_HOUR and DELAYED_START == 1:
            LightManager.debugger("DELAYED STATE with actual state {}, turned on".format(DEVICE_STATUS), 0)
            os.system('./playclient.py --on --group passage')
            DELAYED_START = 0
        if STATUS == 0 and 1 in DEVICE_STATUS:
            if datetime.datetime.now().hour < DETECTION_HOUR:
                LightManager.debugger("Scheduling state change, with actual state {}" \
                                      .format(DEVICE_STATUS), 0)
                DELAYED_START = 1
            else:
                LightManager.debugger("STATE changed to {}, turned on".format(DEVICE_STATUS), 0)
                os.system('./playclient.py --on --group passage')
            STATUS = 1

        time.sleep(10)

    except KeyboardInterrupt:
        quit()

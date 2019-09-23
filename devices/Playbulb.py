#!/usr/bin/env python3
'''
    File name: Playbulb.py
    Author: Maxime Bergeron
    Date last modified: 6/02/2019
    Python Version: 3.7

    The Playbulb BLE bulbs handler class
'''

import functools
import bluepy.btle as ble
import time
from devices.common import *
from devices.Bulb import Bulb

def connect_ble(_f):
    """ Wrapper for functions which requires an active BLE connection using bluepy """
    @functools.wraps(_f)
    def _conn_wrap(self, *args):
        if self._connection is None:
            try:
                debug.write("CONnecting to device ({})...".format(self.description), 0, self.device_type)
                self._connection = ble.Peripheral(self.device)
            except Exception as ex:
                debug.write("Device ({}) connection failed. Exception: {}" \
                                      .format(self.description, ex), 1, self.device_type)
                self._connection = None
        return _f(self, *args)
    return _conn_wrap


class Playbulb(Bulb):
    """ Methods for driving a rainbow BLE lightbulb """
    def __init__(self, devid, config):
        super().__init__(devid, config)
        self.device_type = "Playbulb"
        #TODO get actual color at instanciation
        self.state = "00000000"
        self.intensity = config["DEVICE"+str(devid)]["DEFAULT_INTENSITY"]
        self.color_type = "argb"

    def run(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        if color == DEVICE_OFF:
            color = "00000000"
        elif color == DEVICE_ON:
            color = self.intensity
        debug.write("Changing ({}) color to {}".format(self.description, color), 0, self.device_type)
        if not self._write(color): return False
        return True

    @connect_ble
    def _write(self, color):
        _oldcolor = self.state
        try:
            if self._connection is not None:
                    #NOT YET STABLE
#                   state = self.server.get_state(self.devid)
#                   if (state == "0"):
#                       state = "00000000"
#                   elif (state == "1"):
#                       state = self.intensity
#                   debug.write("Got color: {} and state: {}".format(color, state), 0)
#                   delta_w = (int(color[0:2]) - int(state[0:2]))/20
#                   delta_r = (int(color[2:4]) - int(state[2:4]))/20
#                   delta_g = (int(color[4:6]) - int(state[4:6]))/20
#                   delta_b = (int(color[6:8]) - int(state[6:8]))/20
#                   debug.write("deltaw: {}, deltar: {}, deltag: {}, deltab: {}".format(delta_w, delta_r, delta_g, delta_b), 0)
#                   for _iter in range(20):
#                       if (int(_iter*delta_w) != 0 and int(_iter*delta_r) != 0 and int(_iter*delta_g) != 0 and int(_iter*delta_b) != 0):
#                           deltacolor = str(int(color[0:2]) + int(_iter*delta_w)) + str(int(color[2:4]) + int(_iter*delta_r)) + str(int(color[4:6]) + int(_iter*delta_g)) + str(int(color[6:8]) + int(_iter*delta_b))
#                           self._connection.getCharacteristics(uuid="0000fffc-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(deltacolor))
#                           time.sleep(0.5)


                self.state = color
                self._connection.getCharacteristics(uuid="0000fffc-0000-1000-8000-00805f9b34fb")[0] \
                                .write(bytearray.fromhex(color))

                #Prebuilt animations: blink=00, pulse=01, hard rainbow=02, smooth rainbow=03, candle=04
                #self._connection.getCharacteristics(uuid="0000fffb-0000-1000-8000-00805f9b34fb")[0].write(bytearray.fromhex(color+"02ffffff"))
                self.success = True
                debug.write("({}) color changed to {}".format(self.description, color), 0, self.device_type)
                return True

            self.state = _oldcolor
            debug.write("Connection error to device ({}). Retrying" \
                                  .format(self.description), 1, self.device_type)
            time.sleep(0.2)
            return False

        except Exception as ex:
            #TODO manage "overwritten" thread by queued requests
            self.state = _oldcolor
            debug.write("Unhandled response. Thread died?\n{}".format(ex), 0, self.device_type)
            self.disconnect()
            return False
#!/usr/bin/env python3
'''
    File name: Playbulb.py
    Author: Maxime Bergeron
    Date last modified: 29/02/2020
    Python Version: 3.7

    The Playbulb BLE bulbs handler class
'''

from core.common import *
from core.bulb import Bulb, connect_ble


class LostConnection(Exception):
    # Does nothing for now
    pass


class Playbulb(Bulb):
    """ Methods for driving a rainbow BLE lightbulb """
    _COLOR_UUID = "0000fffc-0000-1000-8000-00805f9b34fb"

    def __init__(self, devid):
        super().__init__(devid)
        self.device_type = "Playbulb"
        # TODO get actual color at instanciation
        self.state = "00000000"
        if self.color_type is None:
            self.color_type = "argb"
        debug.write("Created device Playbulb: {}.".format(
            self.description), 0, self.device_type)

    def run(self, color):
        """ Checks the request and trigger a light change if needed """
        if color == DEVICE_OFF:
            color = "00000000"
        elif color == DEVICE_ON:
            color = self.convert(self.intensity)
        debug.write("Changing ({}) color to {}".format(
            self.description, color), 0, self.device_type)
        if not self._write(color):
            return False
        return True

    @connect_ble
    def get_state(self):
        if self._connection is not None:
            self.state = self._connection.getCharacteristics(
                uuid=Playbulb._COLOR_UUID)[0].read().hex()
        return self.state

    @connect_ble
    def _write(self, color):
        if self._connection is None:
            debug.write("Could not change device state for device ({})".format(
                self.description), 1, self.device_type)
            return False
        try:
                    # NOT YET STABLE
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
                #                           self._connection.getCharacteristics(uuid=Playbulb._COLOR_UUID)[0].write(bytearray.fromhex(deltacolor))
                #                           time.sleep(0.5)

            self.check_for_interrupts()
            _res = self._connection.getCharacteristics(uuid=Playbulb._COLOR_UUID)[0] \
                .write(bytearray.fromhex(color))

            # Prebuilt animations: blink=00, pulse=01, hard rainbow=02, smooth rainbow=03, candle=04
            # self._connection.getCharacteristics(uuid=_COLOR_UUID)[0].write(bytearray.fromhex(color+"02ffffff"))
            self.success = True
            if self._connection is None:
                # For some reason, threaded requests may reach this point and not crash on getCharacteristics, even
                # if conn is None
                raise LostConnection(
                    "Playbulb connection lost whilst changing device state, falling back to old state.")
            self.state = color
            debug.write("({}) color changed to {}".format(
                self.description, color), 0, self.device_type)
            # self.disconnect()
            return True

        except Exception as ex:
            # TODO manage "overwritten" thread by queued requests
            debug.write("Connection error to device ({}) with error: {}. Retrying"
                        .format(self.device, ex), 1, self.device_type)
            self.disconnect()
            return False

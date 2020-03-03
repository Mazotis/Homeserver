#!/usr/bin/env python3
'''
    File name: Milight.py
    Author: Maxime Bergeron
    Date last modified: 03/03/2020
    Python Version: 3.7

    The Milight BLE bulbs handler class
'''

from core.common import *
from core.bulb import Bulb, connect_ble


class Milight(Bulb):
    """ Methods for driving a milight BLE lightbulb """

    def __init__(self, devid):
        super().__init__(devid)
        self.device_type = "Milight"
        self.id1 = self.config["ID1"]
        self.id2 = self.config["ID2"]
        if self.color_type is None:
            self.color_type = "255"
        self.color_temp = self.config.get_value("DEFAULT_TEMP", int)
        if self.color_temp < 2000 or self.color_temp > 6500:
            debug.write(
                "Default color temperature should be between 2000K and 6500K. Quitting.", 2, self.device_type)
            quit()
        # TODO is this accurate enough?
        self.color_temp = int((self.color_temp - 2000) * 125 / 6500)
        self.intensity = int(self.convert(self.intensity))
        if self.intensity < 0 or self.intensity > 100:
            debug.write(
                "Default bulb brightness should be between 0 and 100. Quitting.", 2, self.device_type)
            quit()
        debug.write("Created device Milight: {}.".format(
            self.description), 0, self.device_type)

    def turn_on(self):
        """ Helper function to turn on device """
        if not self._write(self.get_query(32, 161, 1, self.id1, self.id2), "1"):
            return False
        return self._write(self.get_query(20, 161, 4, self.id1, self.id2, 1, 4, 255), "1")

    def turn_off(self):
        """ Helper function to turn off device """
        debug.write("Setting ({}) OFF".format(
            self.description), 0, self.device_type)
        return self._write(self.get_query(32, 161, 2, self.id1, self.id2), "0")

    def turn_on_and_set_color(self, color):
        """ Helper function to change color """
        debug.write("Setting ({}) to COLOR {}".format(
            self.description, color), 0, self.device_type)
        if self.state == DEVICE_OFF:
            if not self.turn_on():
                return False
        if type(color) is tuple:
            if not self._write(self.get_query(45, 161, 4, self.id1, self.id2, int(color[0]), 2, 100), color[0]):
                return False
            return self._write(self.get_query(45, 161, 5, self.id1, self.id2, int(color[0]), 2, int(color[1])), color)
        else:
            if not self._write(self.get_query(45, 161, 4, self.id1, self.id2, color, 2, 100), color):
                return False
            return self._write(self.get_query(45, 161, 5, self.id1, self.id2, color, 2, self.intensity), color)

    def turn_on_and_dim_on(self, color, intensity=None):
        """ Helper function to turn on device to default intensity """
        debug.write("Setting ({}) ON".format(
            self.description), 0, self.device_type)
        if not self.turn_on():
            return False
        return self.dim_on(color, intensity)

    def dim_on(self, color, intensity=None):
        """ Helper function to set default intensity """
        if intensity is None:
            intensity = self.intensity
        return self._write(self.get_query(20, 161, 5, self.id1, self.id2, self.color_temp, 4, intensity), color)

    def run(self, color):
        """ Checks the request and trigger a light change if needed """
        if color == DEVICE_OFF:
            if not self.turn_off():
                return False
        elif color == DEVICE_ON:
            if not self.turn_on_and_dim_on(color):
                return False
        else:
            # TODO How to properly handle collision between luminosity and 255-type hue values ??
            hue = 0
            if type(color) is tuple:
                hue, lum = color
                if hue is None:
                    if str(lum) == DEVICE_OFF:
                        if not self.turn_off():
                            return False
                    elif not self.turn_on_and_dim_on(color, lum):
                        return False
            if hue is not None:
                if not self.turn_on_and_set_color(color):
                    return False
        debug.write("({}) color changed to {}".format(
            self.description, color), 0, self.device_type)
        return True

    def get_query(self, value1, value2, value3, id1, id2, value4=0, value5=2, value6=0):
        """
        Generate encrypted request string.
        ON (value3 = 1)/OFF (value3 = 2): value1 = 32, value2 = 161
        CHANGE COLOR: value1 = 45, value2 = 161, value3 = 4, value4 = colorid
        """
        packet = self._create_command("[" + str(value1) + ", " + str(value2) + ", " + str(id1) + ", " + str(
            id2) + ", " + str(value5) + ", " + str(value3) + ", " + str(value4) + ", " + str(value6) + ", 0, 0, 0]")
        return packet

    @connect_ble
    def _write(self, command, color):
        try:
            if self._connection is not None:
                self._connection.getCharacteristics(uuid="00001001-0000-1000-8000-00805f9b34fb")[0] \
                    .write(bytearray.fromhex(command
                                             .replace('\n', '')
                                             .replace('\r', '')))
                self.success = True
                self.state = color
                return True
            debug.write("Connection to device '{}' unavailable".format(
                self.name), 1, self.device_type)
            return False
        except Exception as ex:
            debug.write("({}) Error sending data to device ({}). Retrying"
                        .format(ex, self.name), 1, self.device_type)
            self.disconnect()
            return False

    def _create_command(self, bledata):
        _input = eval(bledata)
        k = _input[0]
        j = 0
        i = 0
        while i <= 10:
            j += _input[i] & 0xff
            i += 1
        checksum = ((((k ^ j) & 0xff) + 131) & 0xff)
        xored = [(s & 0xff) ^ k for s in _input]
        offs = [0, 16, 24, 1, 129, 55, 169, 87, 35, 70, 23, 0]
        adds = [x + y & 0xff for(x, y) in zip(xored, offs)]
        adds[0] = k
        adds.append(checksum)
        hexs = [hex(x) for x in adds]
        hexs = [x[2:] for x in hexs]
        hexs = [x.zfill(2) for x in hexs]

        return ''.join(hexs)

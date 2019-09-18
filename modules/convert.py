#!/usr/bin/env python3
'''
    File name: convert.py
    Author: Maxime Bergeron
    Date last modified: 17/09/2019
    Python Version: 3.5

    A general color/state code converter. Accepts various formats and tries to output a usable
    color/state code value for the device 

    Accepted formats:
    io - returns 1 (ON) or 0 (OFF)
    io-ops - returns 1 (ON), 0 (OFF) and pass values from 2 to 10 for options
    100 - Brightness percentage code for white bulbs
    255 - 255 colors format (hue)
    rgb - RGB color code (RRGGBB)
    argb - RGBA color code (AARRGGBB)
'''

import colorsys
import re
from devices.common import *

def convert_color(color, output_type=None):
    if output_type not in ["io","io-ops","255","100","rgb","argb"]:
        debug.write("Required color code output_type doesn't exist. Quitting",2)
        quit()

    is_argb=is_rgb=is_8bit=is_100=is_ioops=is_io=False

    if color == LIGHT_SKIP:
        return LIGHT_SKIP

    ''' Type autodetect '''
    is_argb = bool(re.search(r'[a-fA-F0-9]{8}$', color)) and len(color) == 8
    is_rgb = bool(re.search(r'[a-fA-F0-9]{6}$', color)) and len(color) == 6
    if color.isdigit():
        is_8bit = int(color) in range(0,256)
        is_100 = int(color) in range(0,101)
        is_ioops = int(color) in range(0,11)
        is_io = int(color) in range(0,2)
    if not is_ioops:
        is_ioops = color in ["True","False"]
    if not is_io:
        is_io = color in ["True","False"]

    if is_argb and output_type == "argb":
        return color
    if is_rgb and output_type == "rgb":
        return color
    if is_8bit and output_type == "255":
        return color
    if is_100 and output_type == "100":
        return color
    if is_ioops and output_type == "io-ops":
        return color
    if is_io and output_type == "io":
        return color

    ''' Try to convert color types '''
    if output_type in ["io", "io-ops"]:
        #TODO - consider all non-zero requests as ON requests ?
        debug.write("Converted {} to an ON request for IO/IO-OPS color type".format(color),0)
        return LIGHT_ON

    if output_type in ["255","100"]:
        if is_argb:
            color = color[2:8]
        if is_argb or is_rgb:
            if output_type == "255":
                lum_hue = int(colorsys.rgb_to_hls(int(color[0:2], 16)/255, int(color[2:4], 16)/255, int(color[4:7], 16)/255)[0]*255)
                lum_brightness = int(colorsys.rgb_to_hls(int(color[0:2], 16)/255, int(color[2:4], 16)/255, int(color[4:7], 16)/255)[1]*100)
                debug.write("Conversion from rgb {} to hue-brightness (type: 255) {}-{}".format(color, lum_hue, lum_brightness),0)
                return (lum_hue, lum_brightness)
            lum_color = int(colorsys.rgb_to_hls(int(color[0:2], 16)/255, int(color[2:4], 16)/255, int(color[4:7], 16)/255)[1]*100)
            debug.write("Conversion from rgb {} to luminosity (type: 100) level {}".format(color, lum_color),0)
            return lum_color
        debug.write("Conversion from unexpected value {} to 8-bit/brightness color code not yet implemented".format(color),1)
        return LIGHT_ON

    if output_type in ["argb","rgb"]:
        if is_argb:
            if output_type == "rgb":
                return color[2:8]
            else:
                return color
        if is_rgb:
            if output_type == "argb":
                return "00" + color
        if is_io or is_ioops:
            if color in [LIGHT_OFF, LIGHT_ON]:
                return color
            else:
                debug.write("Conversion from IO/IO-OPS {} to RGB color code not yet implemented".format(color),1)
                return LIGHT_ON
        if is_8bit:
            debug.write("Conversion from Milight 8-bit {} to RGB color code not yet implemented".format(color),1)
            return LIGHT_ON
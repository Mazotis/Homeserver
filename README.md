# Lightserver
New - [Read the WIKI](https://github.com/Mazotis/Lightserver/wiki)

A python websocket server/client to control various cheap IoT RGB BLE lightbulbs, DIY devices and programmable ON/OFF devices (TVs via HDMI-CEC, sound systems using LIRC, HTPCs using shutdown/wake-on-lan functions...)

The server runs on a RPi3 or a linux-based bluetooth-enabled processor board and waits for requests, either from IFTTT (using a webhook Then That), from a device on-connection event (detected by pinging a static local IP, ie. for a mobile phone) or by a direct command-line call using playclient.py (for example, when called on a specific event/via a menu button on Kodi - or other HTPC softwares). 

## Why Lightserver ?
* It allows to control multiple devices that uses different protocols at the same time.
* It can change device states using threads, which is much faster than running individual scripts one after another.
* It can be integrated with any project that can run python, for example Kodi HTPCs.
* It allows to change device states (turn lights on/off for example) depending on someone's presence at home or depending on the sunset time at your actual location.
* It is portable - the server can be executed on any python3 compatible machine. You may also have multiple servers if, for example, your bluetooth devices are too far away.
* Compatible with IFTTT (can be interfaced with Google Assistant/Google home and other voice devices) to add vocal commands to any non-smart device.
* Allows indoor localization with [FIND3](https://github.com/schollz/find3) to turn on/off devices depending on where you are located inside your home.
* Can receive commands from any IoT device/detectors that can connect via TCP wifi socket (see [WIKI](https://github.com/Mazotis/Lightserver/wiki/Connecting-a-Arduino-ESP8266-other-devices-via-TCP-socket) page on this) 

## Supported devices
- Milight BLE light bulbs
- Mipow Playbulbs (tested with Rainbow, other BLE Pb devices should work)
- Decora Leviton switches (all switches that are accessible via the MyLeviton app)
- Generic ON/OFF devices (devices that can be turned ON, OFF or restarted using a sh/bash command. Includes TVs with cec-client commands, HTPCs with wakeonlan commands, IR Devices with LIRC irsend commands and everything else. TIP - Group or subgroup them together with a similar name (for example SUBGROUP = livingroom) and call "./playclient.py --on --subgroup livingroom" to turn them all ON simultaneously)
- Meross smart switches MSS110, MSS210, MSS310 and MSS425E (ON/OFF functions - via the Meross cloud app)
- Input devices (arduinos, esp8266 and other wifi-enable boards) to link various sensors to the Lightserver setup


## Requirements
### Absolute requirements
- Python 3
- Some BLE-enabled microprocessor (runs the server. Tested with the RPi3)

### Relative requirements
- HDMI cable (to send HDMI-CEC commands to TV. Check cec-client for infos about how to use this)
- RPI-GPIO + LIRC setup (to create a small, sub-20$ IR remote controller for IR devices, such as a sound device)
- Edited sudoers file to allow shutdown/reboot requests via ssh (UNIX systems)


## Installation and configuration
### On a RPi3 or a linux-based bluetooth-enabled processor board
1) Setup python3 + required pip imports.
2) Configure your server and devices in the play.ini file. Read the file itself or the wiki for all the tweakable parameters.
3) Run 
```
./play.py --server 
Optional command-line options:
--ifttt (to run a websocket IFTTT server to receive requests).
--detector (to run a ip-pinging server to run events on device presence on wifi - for example mobile phones).
--threaded (runs light changes on different threads - faster but might be less stable)
--notime (ignores the EVENT_HOUR parameter. Run events anytime)
```
4) To use HDMI-CEC, connect HDMI cable to a free TV port.

Note - to run the IFTTT server, you need to configure your actions on IFTTT and send the response via websocket. Configure a
dynamic DNS for your local LAN and forward the server port (as set by the PORT variable in play.ini) to your raspberry pi local LAN address port on your router.

### On a client device
1) Setup python3 + required pip imports
2) You can also trigger light changes/HDMI-CEC requests by runing ./playclient.py OPTIONS
```
Examples:
To turn everything on:
./playclient.py --on
To turn everything on any time of day:
./playclient.py --on --notime
To turn the living room (group) devices on any time:
./playclient.py --on --notime --group livingroom
To turn the living room (group) devices off any time, after a 50 seconds delay:
./playclient.py --off --notime --group livingroom --delay 50
To turn off the living room lights over the tv any time:
./playclient.py --off --notime --group livingroom tvlights

```

## Development
More devices can be hardcoded directly in the devices folder. See below for examples.

The __init__ function of your device will receive variables devid (device number) and config (handler for the play.ini configparser).

Decora compatible devices should use the decora variable to send requests (created by the Decora.py module).

BLE bulbs can use the Bulb.py module to simplify development. Integrate this module using super().__init__(devid, config) in the __init__ block.
```
from devices.common import *
from devices.device import device

class MyNewDevice(device):
    def __init__(self, devid, config):
        super().__init__(devid, config) # loads base functions from device.py
        # devid is this device's index within the devicemanager device list, and the play.ini DEVICE# number
        # config is the handler to the play.ini config file
        self.device = config["DEVICE"+str(devid)]["DEVICE"] # Value of the DEVICE configurable in play.ini for DEVICE# (where # is devid)
        # use the same approach for any required variable taken from the config file
        # self._connection is provided by device.py to handle your device connection - True or False
        # self.priority is provided by device.py to give you the actual priority level of this device
        self.state = 0 # You might want a variable to keep in memory the actual color/state of your bulb/device, in this case the initial value is 0
        self.device_type = "MyNewDevice" # Tells the lightserver the actual device type - inheritance safe
```
Each new device class must provide the following functions to properly work. This is subject to change.

device.py provides all functions except color, but you might want to override them if required.
Bulb.py provides the device.py functions + additional features used in BLE lightbulbs. 
```
    def reinit(self):
        """ Prepares the device for a future request. """
        self.success = False

    def get_state(self):
        """ Getter for the actual color/state of device """
        return self.color

    def disconnect(self):
        """ Disconnects the device """
        pass

    def convert(self, color):
        """ Conversion to a color code/state code acceptable by the device """
        """ Ideally to convert a AARRGGBB (or any value that could be sent """
        """ to this device) to a value that the device can handle """
        return color
        
    def descriptions(self):
        """ Getter for the device description """
        return "[{}] - {}".format(self.device_type, self.description)
        
    def color(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        # Some code that can handle a state change request
        # EXAMPLE BELOW. Returning True completes the request. False reruns the request.
        if len(color) > 3:
            debug.write("Unhandled color format {}".format(color), 1)
            return True
        if color == LIGHT_OFF:
            if not self.turn_off(): return False
            return True
        elif color == LIGHT_ON:
            if not self.turn_on_and_dim_on(color):
                return False
            return True
        else:
            if not self.turn_on_and_set_color(color): return False
            return True
``` 

## Credits
* albertogeniola for the [Meross API](https://github.com/albertogeniola/MerossIot)
* moosd for the [Milight BLE protocol](https://github.com/moosd/ReverseEngineeredMiLightBluetooth)
* tlyakhov for the [Decora WIFI API](https://github.com/tlyakhov/python-decora_wifi)
* schollz for the [FIND3](https://github.com/schollz/find3) protocol
# Homeserver
New - [Read the WIKI](https://github.com/Mazotis/Homeserver/wiki)

A python websocket server/client to control various cheap IoT RGB BLE lightbulbs, DIY devices and programmable ON/OFF devices (TVs via HDMI-CEC, sound systems using LIRC, HTPCs using shutdown/wake-on-lan functions...)

The server runs on a RPi3 or a linux-based bluetooth-enabled processor board and waits for requests, either from IFTTT (using a webhook Then That), from a device on-connection event (detected by pinging a static local IP, ie. for a mobile phone), from the included webserver or by a direct command-line call using homeclient.py (for example, when called on a specific event/via a menu button on Kodi - or other HTPC softwares). 

## Why Homeserver ?
* It allows to control multiple devices that uses different protocols at the same time.
* It can change device states using threads, which is much faster than running individual scripts one after another.
* It can be integrated with any project that can run python, for example Kodi HTPCs.
* It allows to change device states (turn lights on/off for example) depending on someone's presence at home or depending on the sunset time at your actual location.
* It is portable - the server can be executed on any python3 compatible machine. You may also have multiple servers if, for example, your bluetooth devices are too far away.
* It supports delayed changes (open x device for n seconds, or change y device state after n seconds).
* Compatible with IFTTT (can be interfaced with Google Assistant/Google home and other voice devices) to add vocal commands to any non-smart device.
* Allows indoor localization with [FIND3](https://github.com/schollz/find3) to turn on/off devices depending on where you are located inside your home.
* Can receive commands from any IoT device/detectors that can connect via TCP wifi socket (see [WIKI](https://github.com/Mazotis/Homeserver/wiki/Connecting-a-Arduino-ESP8266-other-devices-via-TCP-socket) page on this) 
* Can receive commands from a mobile-friendly web interface (for a rpi3, default address is raspberrypi:8080 if the server is started with the "--webserver 8080" commandline option)

## Supported devices
- Milight BLE light bulbs
- Mipow Playbulbs (tested with Rainbow, other BLE Pb devices should work)
- Decora Leviton switches (all switches that are accessible via the MyLeviton app)
- Generic ON/OFF devices (devices that can be turned ON, OFF or restarted using a sh/bash command. Includes TVs with cec-client commands, HTPCs with wakeonlan commands, IR Devices with LIRC irsend commands and everything else. TIP - Group or subgroup them together with a similar name (for example SUBGROUP = livingroom) and call "./homeclient.py --on --subgroup livingroom" to turn them all ON simultaneously)
- Meross smart switches MSS110, MSS210, MSS310 and MSS425E (ON/OFF functions - via the Meross cloud app)
- Input devices (arduinos, esp8266 and other wifi-enable boards) to link various sensors to the homeserver setup
- TPLink smart switches (HS200, HS210, HS220)


## Requirements
### Absolute requirements
- Python 3
- Some BLE-enabled microprocessor (runs the server. Tested with the RPi3)

### Relative requirements
- HDMI cable (to send HDMI-CEC commands to TV. Check cec-client for infos about how to use this)
- RPI-GPIO + LIRC setup (to create a small, sub-20$ IR remote controller for IR devices, such as a sound device)
- Edited sudoers file to allow shutdown/reboot requests via ssh (UNIX systems)

## Installation and configuration
### Using the systemd script
1) Setup python3 + required pip imports.
2) Configure your server and devices in the home.ini file. Read the file itself or the wiki for all the tweakable parameters.
3) Git clone the repository in your RPi home folder (or wherever you want but don't forget to change the service script)
```
cd /home/pi
git clone https://github.com/Mazotis/Homeserver
```
4) Copy and start the systemd script
```
sudo cp ./hosmeerver.service /etc/systemd/system
sudo systemctl enable homeserver
sudo systemctl start hosemerver
```

### On a RPi3 or a linux-based bluetooth-enabled processor board (manual use)
1) Setup python3 + required pip imports.
2) Configure your server and devices in the home.ini file. Read the file itself or the wiki for all the tweakable parameters.
3) Run 
```
./home.py --server 
Optional command-line options:
--ifttt (to run a websocket IFTTT server to receive requests).
--detector (to run a ip-pinging server to run events on device presence on wifi - for example mobile phones).
--threaded (runs device state changes on different threads - faster but might be less stable)
--notime (ignores the EVENT_HOUR parameter. Run events anytime)
--webserver PORT (runs a small webserver at given PORT that allows you to control the homeserver)
```
4) To use HDMI-CEC, connect HDMI cable to a free TV port.

Note - to run the IFTTT server, you need to configure your actions on IFTTT and send the response via websocket. Configure a
dynamic DNS for your local LAN and forward the server port (as set by the PORT variable in home.ini) to your raspberry pi local LAN address port on your router.

### On a client device
1) Setup python3 + required pip imports
2) You can also trigger device state changes/HDMI-CEC requests by runing ./homeclient.py OPTIONS
```
Examples:
To turn everything on:
./homeclient.py --on
To turn everything on any time of day:
./homeclient.py --on --notime
To turn the living room (group) devices on any time:
./homeclient.py --on --notime --group livingroom
To turn the living room (group) devices off any time, after a 50 seconds delay:
./homeclient.py --off --notime --group livingroom --delay 50
To turn off the living room lights over the tv any time:
./homeclient.py --off --notime --group livingroom tvlights

```

## Development
More devices can be hardcoded directly in the devices folder. See below for examples.

The __init__ function of your device will receive variables devid (device number) and config (handler for the home.ini configparser).

Decora compatible devices should use the decora variable to send requests (created by the Decora.py module).

BLE bulbs can use the Bulb.py module to simplify development. Integrate this module by changing MyNewDevice(device) to MyNewDevice(Bulb).
```
from devices.common import *
from devices.device import device

class MyNewDevice(device):
    def __init__(self, devid, config):
        super().__init__(devid, config) # loads base functions from device.py
        # devid is this device's index within the devicemanager device list, and the hmeo.ini DEVICE# number
        # config is the handler to the home.ini config file
        self.device = config["DEVICE"+str(devid)]["DEVICE"] # Value of the DEVICE configurable in home.ini for DEVICE# (where # is devid)
        # use the same approach for any required variable taken from the config file
        # self._connection is provided by device.py to handle your device connection - True or False
        # self.priority is provided by device.py to give you the actual priority level of this device
        # self.auto_mode is provided by device.py to give you the AUTO mode status (True or False)
        self.state = 0 # You might want a variable to keep in memory the actual color/state of your bulb/device, in this case the initial value is 0
        self.device_type = "MyNewDevice" # Tells the homeserver the actual device type - inheritance safe
        self.color_type = "rgb" # Tells the homeserver the expected device state variable type - see convert.py for more info
```
Each new device class must provide the following functions to properly work. This is subject to change.

device.py provides all functions except color, but you might want to override them if required.
Bulb.py provides the device.py functions + additional features used in BLE lightbulbs. 
```
    def get_state(self):
        """ Getter for the actual color/state of device """
        return self.color

    def disconnect(self):
        """ Disconnects the device """
        pass
        
    def descriptions(self):
        """ Getter for the device description """
        return "[{}] - {}".format(self.device_type, self.description)
        
    def run(self, color, priority):
        """ Checks the request and trigger a device state change if needed """
        # Some code that can handle a state change request
        # EXAMPLE BELOW. Returning True completes the request. False reruns the request.
        if len(color) > 3:
            debug.write("Unhandled color format {}".format(color), 1)
            return True
        if color == DEVICE_OFF:
            if not self.turn_off(): return False
            return True
        elif color == DEVICE_ON:
            if not self.turn_on_and_dim_on(color):
                return False
            return True
        else:
            if not self.turn_on_and_set_color(color): return False
            return True

    def post_run(self):
        """ Prepares the device for a future request. """
        self.success = False
``` 

## Credits
* albertogeniola for the [Meross API](https://github.com/albertogeniola/MerossIot)
* moosd for the [Milight BLE protocol](https://github.com/moosd/ReverseEngineeredMiLightBluetooth)
* tlyakhov for the [Decora WIFI API](https://github.com/tlyakhov/python-decora_wifi)
* schollz for the [FIND3](https://github.com/schollz/find3) protocol
* GadgetReactor for the [TPLink switches](https://github.com/GadgetReactor/pyHS100) support

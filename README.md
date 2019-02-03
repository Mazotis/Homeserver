# Lightserver
A python websocket server/client to control various cheap IoT RGB BLE lightbulbs and HDMI-CEC-to-TV RPi3

## Supported devices
- Milight BLE light bulbs
- Mipow Playbulbs (tested with Rainbow, other BLE Pb devices should work)
- Decora Leviton switches (accessible via the MyLeviton app)

## Requirements
- Python 3
- Some BLE-enabled microprocessor (runs the server. Tested with the RPi3)
- HDMI cable (to send HDMI-CEC commands to TV)

## Installation and configuration
### On a RPi3 or a linux-based bluetooth-enabled processor board
1) Setup python3 + required pip imports.
2) Configure your server and bulbs in the play.ini file.
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
dynamic DNS for your local LAN and forward the IFTTT port (as set by the port variable in the script) to your raspberry pi local LAN address.

### On a client device
1) Setup python3 + required pip imports
2) You can also trigger light changes/HDMI-CEC requests by runing ./playclient.py OPTIONS
```
To turn everything on:
./playclient.py --on
To turn everything on any time of day:
./playclient.py --on --notime
To turn the living room (group) devices on any time:
./playclient.py --on --notime --group livingroom
To turn off the living room lights over the tv any time:
./playclient.py --off --notime --group livingroom --subgroup tvlights

```

## Development
More devices can be hardcoded directly in the play.py script. They will then be instantiated as configured in the play.ini file: [DEVICE#] TYPE = MyNewDevice.
You can pass play.ini configurables and needed variables from the lightmanager __init__ block (where the devices are instantiated).
```
class LightManager(object):
    """ Methods for instanciating and managing BLE lightbulbs """
    def __init__(self, config=None):
            if self.config["DEVICE"+str(i)]["TYPE"] == "MyNewDevice":
                    self.devices.append(MyNewDevice(i, self.config["DEVICE"+str(i)]["ADDRESS"],
                                                 self.config["DEVICE"+str(i)]["DESCRIPTION"],
                                                 self.config["DEVICE"+str(i)]["GROUP"],
                                                 self.config["DEVICE"+str(i)]["SUBGROUP"],
                                                 self.config["DEVICE"+str(i)]["DEFAULT_INTENSITY"],
                                                 self))
                    debug.write("Created device MyNewDevice {}. Description: {}" \
                                          .format(self.config["DEVICE"+str(i)]["ADDRESS"],
                                                  self.config["DEVICE"+str(i)]["DESCRIPTION"]),
                                          0)

...

class MyNewDevice(object):
    def __init__(self, devid, device, description, group, subgroup, default_intensity):
        global debug # Needed to access the debug log
        self.devid = devid # In this case, this device's index within the lightmanager device list
        self.device = device
        self.description = description
        self.success = False # You might need a thread-safe boolean flag to avoid requests when your device is already of the good color 
        self._connection = None # You might want a variable to handle your device connection
        self.group = group
        self.subgroup = subgroup
        self.default_intensity = default_intensity
        self.priority = 0 # You might need a variable to handle the device actual light change priority level
        self.color = 0 # You might want a variable to keep in memory the actual color/state of your bulb/device
```
Each new device class must provide the following functions to properly work. This is subject to change
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
        if color == 0:
            color = "00000000"
        elif color == 1:
            color = self.default_intensity
        return color
        
    def descriptions(self):
        """ Getter for the device description """
        description_text = "[MyNewDevice MAC: " + self.device + "] " + self.description
        return description_text
        
    def color(self, color, priority):
        """ Checks the request and trigger a light change if needed """
        # Some code that can handle a color/state (color) request and the priority level of current request (priority)
``` 

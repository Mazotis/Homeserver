# Lightserver
A python websocket server/client to control various cheap IoT RGB BLE lightbulbs and HDMI-CEC-to-TV RPi3

# Usage

*** On a RPi3 or a linux-based bluetooth-enabled processor board ***
1) Setup python3 + required pip imports.
2) Configure your playbulb/milight bulbs in the __init__ section of play.py.
3) Run ./play.py --server (or execute as systemd startup script).
4) To use HDMI-CEC, connect HDMI cable to a free TV port.

*** On a client device (tested on an AsusWRT router) ***
1) Setup python3 + required pip imports (opkg)
2) Run server.py using the init.d script. This will receive web POST requests (using POST variables action and hash - a SHA512 hashed SALT+action string).
3) Run detector.py using the init.d script. This will query active WIFI devices (cellphones, tablets...using the MAC addresses) on the network and open/close lights accordingly.
4) You can also trigger light changes/HDMI-CEC requests by runing ./playclient.py OPTIONS

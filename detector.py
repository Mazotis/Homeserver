#!/usr/bin/env python3
"""
Simple playserver device detector
"""
import os
import time, datetime

DEVICE_MAC = ["40:4E:36:87:0B:51"]
STATUS = 0
DELAYED_START = 0

for device in DEVICE_MAC:
	if (os.system("wl assoclist | grep {}".format(device))):
		STATUS = 0
	else:
		STATUS = 1
while True:
	try:
		for device in DEVICE_MAC:
			if (os.system("wl assoclist | grep {}".format(device))):
				if (STATUS == 1):
					os.system('./playclient.py --off --notime --priority 3')
				STATUS = 0
			else:
				if (DELAYED_START == 0):
					if (datetime.datetime.now().hour == 18):
						os.system('./playclient.py --on')
						DELAYED_START = 1
				if (STATUS == 0):
					os.system('./playclient.py --on')	
				if (DELAYED_START == 1 and datetime.datetime.now().hour == 19):
					DELAYED_START = 0
				STATUS = 1
		
		time.sleep(10)
		
	except KeyboardInterrupt:
		quit()
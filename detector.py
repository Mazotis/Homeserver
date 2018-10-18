#!/usr/bin/env python3
"""
Simple playserver device detector
"""
import os
import time, datetime

DEVICE_MAC = ["40:4E:36:87:0B:51", "40:4E:36:87:0B:89"]
DEVICE_STATUS = [0]*len(DEVICE_MAC)
STATUS = 0
DELAYED_START = 0

for _cnt, device in enumerate(DEVICE_MAC):
	if (os.system("wl assoclist | grep {}".format(device))):
		DEVICE_STATUS[_cnt] = 0
	else:
		DEVICE_STATUS[_cnt] = 1
while True:
	try:
		for device in DEVICE_MAC:
			if (os.system("wl assoclist | grep {}".format(device))):
				DEVICE_STATUS[_cnt] = 0
			else:
				DEVICE_STATUS[_cnt] = 1

		if (STATUS == 1 and all(s == 0 for s in DEVICE_STATUS)):
			os.system('./playclient.py --off --notime --priority 3')
			STATUS = 0
			DELAYED_START = 0
		if (datetime.datetime.now().hour == 18 and DELAYED_START == 1):
			os.system('./playclient.py --on --group passage')
			DELAYED_START = 0
		if (STATUS == 0 and 1 in DEVICE_STATUS):
			if (datetime.datetime.now().hour < 18):
				DELAYED_START = 1
			else:
				os.system('./playclient.py --on --group passage')	
			STATUS = 1
		
		time.sleep(10)
		
	except KeyboardInterrupt:
		quit()
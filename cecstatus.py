#!/usr/bin/env python3

import pexpect
import time

status = 0

while (True):
	p = pexpect.spawn('cec-client -s -d 1')
	p.sendline('pow 0')
	try:
		pindex = p.expect(['status: standby','status: on'])
	except OSError:
		pindex = "-1"
	print(pindex)
	time.sleep(5)
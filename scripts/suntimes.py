#!/usr/bin/env python3
'''
    File name: suntimes.py
    Author: Maxime Bergeron
    Date last modified: 20/05/2020
    Python Version: 3.7

    Helper script to fetch sun times - useful for light controls
'''

from astral.geocoder import database, lookup
from astral.sun import sun


def get_sun(location):
    try:
        li = lookup(location, database())
    except KeyError:
        return None

    return sun(li.observer, tzinfo=li.timezone)

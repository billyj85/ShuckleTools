#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import configargparse
import os
import json
import logging
import random
import time
import socket
import struct
import hashlib
import psutil
import subprocess
import requests

from s2sphere import CellId, LatLng
from geopy.geocoders import GoogleV3
from requests_futures.sessions import FuturesSession
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from cHaversine import haversine
from pprint import pformat

log = logging.getLogger(__name__)


def parse_unicode(bytestring):
    decoded_string = bytestring.decode(sys.getfilesystemencoding())
    return decoded_string


def memoize(function):
    memo = {}

    def wrapper(*args):
        if args in memo:
            return memo[args]
        else:
            rv = function(*args)
            memo[args] = rv
            return rv
    return wrapper


def now():
    # The fact that you need this helper...
    return int(time.time())


# Gets the seconds past the hour.
def cur_sec():
    return (60 * time.gmtime().tm_min) + time.gmtime().tm_sec


# Gets the total seconds past the hour for a given date.
def date_secs(d):
    return d.minute * 60 + d.second


# Checks to see if test is between start and end accounting for hour
# wraparound.
def clock_between(start, test, end):
    return ((start <= test <= end and start < end) or
            (not (end <= test <= start) and start > end))


# Return the s2sphere cellid token from a location.
def cellid(loc):
    return CellId.from_lat_lng(LatLng.from_degrees(loc[0], loc[1])).to_token()


# Return approximate distance in meters.
def distance(pos1, pos2):
    return haversine((tuple(pos1))[0:2], (tuple(pos2))[0:2])


# Return True if distance between two locs is less than distance in meters.
def in_radius(loc1, loc2, radius):
    return distance(loc1, loc2) < radius



# Generate random device info.
# Original by Noctem.
IPHONES = {'iPhone5,1': 'N41AP',
           'iPhone5,2': 'N42AP',
           'iPhone5,3': 'N48AP',
           'iPhone5,4': 'N49AP',
           'iPhone6,1': 'N51AP',
           'iPhone6,2': 'N53AP',
           'iPhone7,1': 'N56AP',
           'iPhone7,2': 'N61AP',
           'iPhone8,1': 'N71AP',
           'iPhone8,2': 'N66AP',
           'iPhone8,4': 'N69AP',
           'iPhone9,1': 'D10AP',
           'iPhone9,2': 'D11AP',
           'iPhone9,3': 'D101AP',
           'iPhone9,4': 'D111AP',
           'iPhone10,1': 'D20AP',
           'iPhone10,2': 'D21AP',
           'iPhone10,3': 'D22AP',
           'iPhone10,4': 'D201AP',
           'iPhone10,5': 'D211AP',
           'iPhone10,6': 'D221AP'}


def generate_device_info(identifier):
    md5 = hashlib.md5()
    md5.update(identifier)
    pick_hash = int(md5.hexdigest(), 16)

    device_info = {'device_brand': 'Apple', 'device_model': 'iPhone',
                   'hardware_manufacturer': 'Apple',
                   'firmware_brand': 'iPhone OS'}
    devices = tuple(IPHONES.keys())

    ios9 = ('9.0', '9.0.1', '9.0.2', '9.1', '9.2', '9.2.1', '9.3', '9.3.1',
            '9.3.2', '9.3.3', '9.3.4', '9.3.5')
    # 10.0 was only for iPhone 7 and 7 Plus, and is rare.
    ios10 = ('10.0.1', '10.0.2', '10.0.3', '10.1', '10.1.1', '10.2', '10.2.1',
             '10.3', '10.3.1', '10.3.2', '10.3.3')
    ios11 = ('11.0.1', '11.0.2', '11.0.3', '11.1', '11.1.1', '11.1.2')

    device_pick = devices[pick_hash % len(devices)]
    device_info['device_model_boot'] = device_pick
    device_info['hardware_model'] = IPHONES[device_pick]
    device_info['device_id'] = md5.hexdigest()

    if device_pick in ('iPhone10,1', 'iPhone10,2', 'iPhone10,3',
                       'iPhone10,4', 'iPhone10,5', 'iPhone10,6'):
        # iPhone 8/8+ and X started on 11.
        ios_pool = ios11
    elif device_pick in ('iPhone9,1', 'iPhone9,2', 'iPhone9,3', 'iPhone9,4'):
        # iPhone 7/7+ started on 10.
        ios_pool = ios10 + ios11
    elif device_pick == 'iPhone8,4':
        # iPhone SE started on 9.3.
        ios_pool = ('9.3', '9.3.1', '9.3.2', '9.3.3', '9.3.4', '9.3.5') \
                   + ios10 + ios11
    elif device_pick in ('iPhone5,1', 'iPhone5,2', 'iPhone5,3', 'iPhone5,4'):
        # iPhone 5/5c doesn't support iOS 11.
        ios_pool = ios9 + ios10
    else:
        ios_pool = ios9 + ios10 + ios11

    device_info['firmware_type'] = ios_pool[pick_hash % len(ios_pool)]
    return device_info


@memoize
def gmaps_reverse_geolocate(gmaps_key, locale, location):
    # Find the reverse geolocation
    geolocator = GoogleV3(api_key=gmaps_key)

    player_locale = {
        'country': 'US',
        'language': locale,
        'timezone': 'America/Denver'
    }

    try:
        reverse = geolocator.reverse(location)
        address = reverse[-1].raw['address_components']
        country_code = 'US'

        # Find country component.
        for component in address:
            # Look for country.
            component_is_country = any([t == 'country'
                                        for t in component.get('types', [])])

            if component_is_country:
                country_code = component['short_name']
                break

        try:
            timezone = geolocator.timezone(location)
            player_locale.update({
                'country': country_code,
                'timezone': str(timezone)
            })
        except Exception as e:
            log.exception('Exception on Google Timezone API. '
                          + 'Please check that you have Google Timezone API'
                          + ' enabled for your API key'
                          + ' (https://developers.google.com/maps/'
                          + 'documentation/timezone/intro): %s.', e)
    except Exception as e:
        log.exception('Exception while obtaining player locale: %s.'
                      + ' Using default locale.', e)

    return player_locale


# Get a future_requests FuturesSession that supports asynchronous workers
# and retrying requests on failure.
# Setting up a persistent session that is re-used by multiple requests can
# speed up requests to the same host, as it'll re-use the underlying TCP
# connection.
def get_async_requests_session(num_retries, backoff_factor, pool_size,
                               status_forcelist=None):
    # Use requests & urllib3 to auto-retry.
    # If the backoff_factor is 0.1, then sleep() will sleep for [0.1s, 0.2s,
    # 0.4s, ...] between retries. It will also force a retry if the status
    # code returned is in status_forcelist.
    if status_forcelist is None:
        status_forcelist = [500, 502, 503, 504]
    session = FuturesSession(max_workers=pool_size)

    # If any regular response is generated, no retry is done. Without using
    # the status_forcelist, even a response with status 500 will not be
    # retried.
    retries = Retry(total=num_retries, backoff_factor=backoff_factor,
                    status_forcelist=status_forcelist)

    # Mount handler on both HTTP & HTTPS.
    session.mount('http://', HTTPAdapter(max_retries=retries,
                                         pool_connections=pool_size,
                                         pool_maxsize=pool_size))
    session.mount('https://', HTTPAdapter(max_retries=retries,
                                          pool_connections=pool_size,
                                          pool_maxsize=pool_size))

    return session




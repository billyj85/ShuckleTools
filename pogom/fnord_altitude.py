#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import requests
import random

from argparser import location_parse

log = logging.getLogger(__name__)

# Altitude used when use_altitude_cache is enabled.
fallback_altitude = None


def add_gmaps_altitude(args, locations):
    return [with_gmaps_altitude(location_parse(x), args.gmaps_key) for x in locations.strip().split(' ')]


def with_gmaps_altitude(loc, gmaps_key):
    if len(loc) == 3:
        return loc
    altitude = get_gmaps_altitude(loc[0], loc[1], gmaps_key)
    return loc[0], loc[1], altitude[0] if altitude[0] >= 0 else 0


def with_random_altitude(loc, gmaps_key):
    altitude = random.uniform(0,100)
    return loc[0], loc[1], altitude


def get_gmaps_altitude(lat, lng, gmaps_key):
    try:
        r_session = requests.Session()
        response = r_session.get((
            'https://maps.googleapis.com/maps/api/elevation/json?' +
            'locations={},{}&key={}').format(lat, lng, gmaps_key),
            timeout=5)
        response = response.json()
        status = response['status']
        results = response.get('results', [])
        result = results[0] if results else {}
        altitude = result.get('elevation', None)
    except Exception as e:
        log.exception('Unable to retrieve altitude from Google APIs: %s.', e)
        status = 'UNKNOWN_ERROR'
        altitude = None

    return (altitude, status)


def randomize_altitude(altitude, altitude_variance):
    if altitude_variance > 0:
        altitude = (altitude +
                    random.randrange(-1 * altitude_variance,
                                     altitude_variance) +
                    float(format(random.random(), '.13f')))
    else:
        altitude = altitude + float(format(random.random(), '.13f'))

    return altitude


# Only once fetched altitude
def get_fallback_altitude(args, loc):
    global fallback_altitude

    # Only query if it's not set, and if it didn't fail already.
    if fallback_altitude is None and fallback_altitude != -1:
        (fallback_altitude, status) = get_gmaps_altitude(loc[0], loc[1],
                                                         args.gmaps_key)

    # Failed, don't try again.
    if fallback_altitude is None:
        fallback_altitude = -1

    return fallback_altitude



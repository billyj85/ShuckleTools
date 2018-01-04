import math
import geopy
import geopy.distance
import random

a = 6378245.0
ee = 0.00669342162296594323
pi = 3.14159265358979324


# Returns destination coords given origin coords, distance (Ms) and bearing.
# This version is less precise and almost 1 order of magnitude faster than
# using geopy.
def fast_get_new_coords(origin, distance, bearing):
    R = 6371009  # IUGG mean earth radius in kilometers.

    oLat = math.radians(origin[0])
    oLon = math.radians(origin[1])
    b = math.radians(bearing)

    Lat = math.asin(
        math.sin(oLat) * math.cos(distance / R) +
        math.cos(oLat) * math.sin(distance / R) * math.cos(b))

    Lon = oLon + math.atan2(
        math.sin(bearing) * math.sin(distance / R) * math.cos(oLat),
        math.cos(distance / R) - math.sin(oLat) * math.sin(Lat))

    return math.degrees(Lat), math.degrees(Lon)


# Apply a location jitter.
def jitter_location(location=None, max_meters=5):
    origin = geopy.Point(location[0], location[1])
    bearing = random.randint(0, 360)
    distance = math.sqrt(random.random()) * (float(max_meters))
    destination = fast_get_new_coords(origin, distance, bearing)
    if len(location) > 2:
        return (destination[0], destination[1], location[2])
    else:
        return (destination[0], destination[1])

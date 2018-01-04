import logging

from geopy.distance import vincenty

from gymdbsql import create_or_update_gym, log_gym_change_in_db, gym_names
from scannerutil import as_str

log = logging.getLogger(__name__)


def log_gym_change(g, previousgym):
    latitude_ = g["latitude"]
    longitude_ = g["longitude"]
    modified_ = g["last_modified"]
    kmh = None
    distance = None
    previous_gym = None
    name_ = as_str(g["name"])
    if not previousgym is None:
        previous_latitude = previousgym["latitude"]
        previous_longitude = previousgym["longitude"]
        previous_lastmodified = previousgym["last_modified"]
        previous_gym = as_str(previousgym["name"])

        elapsed_seconds = (modified_  - previous_lastmodified).total_seconds()

        prevgymcoords = (previous_latitude, previous_longitude)
        thisgymccords = (latitude_, longitude_)
        distance = vincenty(prevgymcoords, thisgymccords).m

        print("Distance between " + previous_gym + str(prevgymcoords) + " and "  + name_ + str(thisgymccords) + " is" + str(distance) +", elapsed is " + str(elapsed_seconds))
        if distance == 0:
            distance = None
        elif elapsed_seconds  > 0 and distance  > 0:
            kmh = distance/elapsed_seconds * 3.6
        else:
            previous_gym = None
            distance = None

    log_gym_change_in_db(g, previous_gym, kmh, distance)


def update_gym_from_details(gym):
    state_ = gym.gym_status_and_defenders
    data_ = state_.pokemon_fort_proto
    gym_id = data_.id
    create_or_update_gym(gym_id, gym)


def gym_map(fences):
    result = {}
    for name in gym_names():
        if fences.within_fences(name["latitude"], name["longitude"]):
            result[name["gym_id"]] = as_str(name["name"])
    return result

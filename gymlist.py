import asyncio

import logging

from accounts3 import AsyncAccountManager
from argparser import std_config, add_system_id, setup_default_app, add_use_account_db, add_search_rest
from behaviours import beh_do_process_single_gmo_gym
from geofence import get_geofences
from geography import step_position
from getmapobjects import find_gym, inrange_gyms
from gymdbsql import all_gyms
from mapelements import GymElement
from mapelement_tools import add_altitudes
from pogoservice import TravelTime, TravelTime2
from workers import wrap_account


parser = std_config("gymscanner")
add_search_rest(parser)
add_system_id(parser)
add_use_account_db(parser)
args = parser.parse_args()
args.system_id="dev-test"
loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

queue = []

allgyms = all_gyms()
fences = get_geofences("geofence.txt", ["OsloInnenforRing3"])
filtered = fences.filter_map_elements(allgyms)
add_altitudes(filtered, args.gmaps_key)
elements = GymElement.from_db_rows(filtered)

async def start():
    missing_name = [x for x in elements if not x.name]
    if len(missing_name) > 0:
        account_manager = await AsyncAccountManager.create_standard(args, loop)
        account = await account_manager.get_account()
        worker = wrap_account(account, account_manager)
        travel_time = worker.getlayer(TravelTime2)
        travel_time.use_fast_speed()
        for missing in missing_name:
            gym_pos= step_position(missing.coords, -1, 1)
            map_objects = worker.do_get_map_objects(gym_pos)
            gyms = inrange_gyms(map_objects, gym_pos)
            fort = find_gym(gyms, missing.id)
            if fort:
                beh_do_process_single_gmo_gym(worker, fort, gym_pos)
            else:
                log.info("Gym {} not found in real map data".format(str(missing)))
        log.info("Gym names updated, re-run")
        exit(-1)

    for elem in elements:
        print("{};{};{};{}".format(elem.name, elem.as_map_link(), elem.coords[0], elem.coords[1]))



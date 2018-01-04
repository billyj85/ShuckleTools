import asyncio

from queue import Queue, PriorityQueue

import logging

from accounts3 import AsyncAccountManager
from argparser import std_config, load_proxies, location, add_geofence, add_search_rest, setup_default_app
from behaviours import beh_safe_do_gym_scan
from geofence import filter_for_geofence
from geography import gym_moves_generator, step_position
from gymdbsql import gymscannercoordinates, set_gymdb_args
from scannerutil import fail_on_forced_update, equi_rect_distance_m
from workers import wrap_account

parser = std_config("gymwatcher")
add_geofence(parser)
add_search_rest(parser)
parser.add_argument('-r', '--radius',
                    help='Radius in meters from location',
                    type=int, default=None)
parser.add_argument('-len', '--length',
                    help='length',
                    type=int, default=40000)
parser.set_defaults(DEBUG=False)
args = parser.parse_args()
loop = asyncio.get_event_loop()
setup_default_app(args, loop)

log = logging.getLogger(__name__)


fail_on_forced_update(args)

queue = PriorityQueue()
dbqueue = Queue()

args.system_id="gymwatcher"

seen_gyms = {}

running = True

MAX_LEN = args.length


def find_closest(current_list, first):
    shortest_distance = 10000000
    shortest_idx = -1
    coordinates_ = first["coordinates"]
    max_longitude = 1000
    for idx, gym in enumerate(current_list):
        if gym["longitude"] > max_longitude:
            break
        current_distance = equi_rect_distance_m(coordinates_, gym["coordinates"])
        if current_distance < shortest_distance:
            shortest_distance = current_distance
            shortest_idx = idx
            max_longitude = step_position(
                gym["coordinates"], 0, current_distance)[1]
    closes = gym_map[shortest_idx]
    del gym_map[shortest_idx]
    return closes


def length_of_route(current_route):
    length = 0
    prev_gym = None
    for gym in current_route:
        if prev_gym is not None:
            length += equi_rect_distance_m(prev_gym, gym["coordinates"])
        prev_gym = gym["coordinates"]
    return length


gym_map = gymscannercoordinates()
gym_map = filter_for_geofence(gym_map, args.geofence, args.fencename)
log.info(u"There are {} gyms in scan with fence {}".format(str(len(gym_map)), str(args.fencename)))
streams = []

initialPosition = location(args)
if args.radius is not None:
    filtered = [x for x in gym_map if equi_rect_distance_m(initialPosition, x["coordinates"]) < args.radius]
    gym_map = filtered

while len(gym_map) > 0:
    prev = gym_map[0]
    stream = [prev]
    del gym_map[0]
    distance = 0
    while len(gym_map) > 0:
        next_gym = find_closest(gym_map, prev)
        distance += equi_rect_distance_m(prev["coordinates"], next_gym["coordinates"])
        if distance > MAX_LEN:
            streams.append(stream)
            log.info(u"Created stream " + str(len(streams)) + ", with " + str(
                len(stream)) + " gyms, length " + str(
                int(length_of_route(stream))) + " meters")
            stream = []
            distance = 0
        stream.append(next_gym)
        distance += 250  # add 250 m per gym
        prev = next_gym
    log.info(u"Created stream " + str(len(streams)) + ", with " + str(
        len(stream)) + " gyms, length " + str(
        int(length_of_route(stream))) + " meters")
    streams.append(stream)

async def start():
    account_manager = await AsyncAccountManager.create_standard(args, loop)

    scanners = []
    for stream in streams:
        account = await account_manager.get_account()
        scanner = wrap_account(account, account_manager)
        scanners.append(scanner)
        asyncio.ensure_future(beh_safe_do_gym_scan(scanner, gym_moves_generator(stream)))
        asyncio.sleep(2)

    log.info(u"exiting scanner")


asyncio.ensure_future(start())
loop.run_forever()

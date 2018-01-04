import asyncio
from threading import Thread

import logging

from accounts3 import AsyncAccountManager
from argparser import std_config, load_proxies, add_geofence, add_search_rest, setup_default_app
from behaviours import beh_process_single_gmo_gym_no_dups
from geofence import get_geofences
from geography import box_moves_generator
from getmapobjects import parse_gyms
from gymdbsql import set_gymdb_args
from management_errors import GaveUp
from scannerutil import install_thread_excepthook
from workers import wrap_account

parser = std_config("gymscanner")
add_search_rest(parser)
add_geofence(parser)
parser.set_defaults(DEBUG=False)
args = parser.parse_args()
loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

CONST_NUMSCANNERS = args.sweep_workers
args.system_id="gymsweeper"


async def create_scanner_acct(account_manager, allsteps, count):
    steps = []
    step = next(allsteps, None)
    while step is not None and len(steps) < count:
        steps.append(step)
        step = next(allsteps, None)

    account = await account_manager.get_account()
    worker = wrap_account(account, account_manager)
    asyncio.ensure_future(safe_do_work(worker, iter(steps)))
    await asyncio.sleep(2)
    return step is not None


def safe_do_work(worker, moves_gen):
    # noinspection PyBroadException
    try:
        do_work(worker, moves_gen)
    except:
        logging.exception("Outer worker catch block caught exception")
    logging.info("Worker complete")


def do_work(worker, moves_gen):
    seen_gyms = set()

    for position in moves_gen:
        try:
            map_objects = worker.do_get_map_objects(position)
        except GaveUp:
            log.warning("Gave up getting map objects at " + str(position))
            continue

        gyms = []
        try:
            if map_objects is None:  # can this ever happen ??
                log.warning(
                    "Did not get any map objects at {}, moving on".format(str(map_objects)))
            else:
                gyms = parse_gyms(map_objects)
        except StopIteration:
            log.warning("Iteration over forts failed " + str(map_objects))  # can this ever happen ?
            pass
        for gym in gyms:
            beh_process_single_gmo_gym_no_dups(worker, seen_gyms, gym, position)


async def start():
    account_manager = await AsyncAccountManager.create_standard(args, loop)

    fences = get_geofences(args.geofence, args.fencename)
    box = fences.box()
    moves = box_moves_generator(box[0], box[1])
    movesToUse = []
    log.info("Filtering for fences")
    for move in moves:
        if fences.within_fences(move[0], move[1]):
            movesToUse.append(move)

    total_steps = len(movesToUse)
    steps_per_scanner = total_steps / CONST_NUMSCANNERS  # todo maybe use time-based target metric instead
    log.info("Fence box is {}".format(str(box)))
    log.info("Steps per scanner account is {}".format(steps_per_scanner))

    i = 0
    move_gen = iter(movesToUse)
    while await create_scanner_acct(move_gen, steps_per_scanner, account_manager):
        log.info("Created scanner {}".format(str(i)))
        i += 1

    print("Done scanning for all scanners")


asyncio.ensure_future(start())
loop.run_forever()

import asyncio

import logging

import math

from accounts3 import AsyncAccountManager
from argparser import std_config, add_geofence, add_webhooks, add_search_rest, parse_unicode, \
    add_threads_per_proxy, add_use_account_db_true, setup_default_app
from async_accountdbsql import set_account_db_args, db_set_system_id
from behaviours import beh_aggressive_bag_cleaning, discard_all_pokemon
from catchmanager import CatchManager, CatchFeed, OneOfEachCatchFeed, Candy12Feed, NoOpFeed, CatchConditions
from common_accountmanager import OutOfAccounts
from getmapobjects import is_discardable, is_starter_pokemon, catchable_pokemon
from levelup_tools import get_pos_to_use, exclusion_pokestops, CountDownLatch
from management_errors import GaveUp
from pogoservice import TravelTime, ApplicationBehaviour
from pokestoproutesv2 import routes_p1, initial_130_stops, routes_p2, xp_p1, xp_p2
from routes.hamburg_xp1 import xp_route_1
from routes.hamburg_xp2 import xp_route_2
from scannerutil import create_forced_update_check, pairwise
from stopmanager import StopManager
from workermanager import WorkerManager, PositionFeeder
from workers import wrap_account_no_replace

parser = std_config("levelup_default")
add_search_rest(parser)
add_use_account_db_true(parser)
parser.add_argument('-system-id', '--system-id',
                    help='Define the name of the node that will be used to identify accounts in the account table',
                    default=None)
parser.add_argument('-fsi', '--final-system-id',
                    help='Define the name of the node where accounts are transferred upon successful botting',
                    default=None)
parser.add_argument('-fasi', '--failed-system-id',
                    help='Define the name of the node where accounts are transferred upon unsuccessful botting',
                    default=None)
parser.add_argument('-fl', '--fail-last', default=0,
                    help='When this number of accounts remain, fail any accounts that are less than 95% done')
parser.add_argument('-locs', '--locations', type=parse_unicode,
                    help='Location, can be an address or coordinates.')
parser.add_argument('-r', '--route', type=parse_unicode,
                    help='Predefined route (locations). Known routes are oslo, copenhagen')
parser.add_argument('-lvl', '--target-level', default=5,
                    help='Target level of the bot')
add_threads_per_proxy(parser)
parser.add_argument('-st', '--max-stops', default=3490,
                    help='Max pokestops for a single session')
parser.add_argument('-tc', '--thread-count', default=5,
                    help='Number of threads to use')
parser.add_argument('-pokemon', '--catch-pokemon', default=3490,
                    help='If the levelup should catch pokemon (not recommended)')
parser.add_argument('-egg', '--use-eggs', default=True,
                    help='True to use lucky eggs')
parser.add_argument('-fs', '--fast-speed', default=25,
                    help='Fast speed in m/s')
parser.add_argument('-fast-levlup', '--fast-levelup', default=False, action='store_true',
                    help='True to use stop-only double XP mode')
parser.add_argument('-iegg', '--use-initial-egg', default=True, action='store_true',
                    help='True to use lucky eggs')
parser.add_argument('-ca', '--catch-all', default=False, action='store_true',
                    help='Catch all eligible')
parser.add_argument('-am', '--alt-mode', default=False, action='store_true',
                    help='Alt mode')
parser.add_argument('-ns', '--non-stop', default=False, action='store_true',
                    help='Run without stop')

add_webhooks(parser)
add_geofence(parser)
args = parser.parse_args()
loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

lock = asyncio.Lock()
num_completed = 0

account_manager = AsyncAccountManager.create_empty(args, loop)
account_manager.reallocate = False

global_catch_feed = CatchFeed()
one_of_each_catch_feed = OneOfEachCatchFeed()
candy_12_feed = Candy12Feed()


async def safe_levelup(thread_num, global_catch_feed_, latch, forced_update_):
    global num_completed
    while True:
        # noinspection PyBroadException
        try:
            worker = await next_worker()
            if worker:
                await levelup(thread_num, worker, global_catch_feed_, latch, forced_update_, fast_25=args.fast_levelup)
        except OutOfAccounts:
            logging.info("No more accounts, exiting worker thread")
            return
        except GaveUp:
            logging.info("Gave UP, exiting")
            return
        except:
            logging.exception("Outer worker catch block caught exception")
        finally:
            pass
            # await latch.count_down()
        if not args.non_stop:  # latch does not work in non-stop mode
            break
    async with lock:
        num_completed += 1


async def next_worker():
    account = await account_manager.get_account()
    worker = wrap_account_no_replace(account, account_manager, int(args.fast_speed))
    return worker


async def process_points(locations, xp_boost_phase, catch_feed, cm, sm, wm, travel_time, worker, phase,
                         catch_condition, first_time=None, receive_broadcasts=True, pos_index=0):
    first_loc = get_pos_to_use(locations[0])
    log.info(u"First lof {}".format(str(first_loc)))
    map_objects = await wm.move_to_with_gmo(first_loc)

    num_pokes = len(worker.account_info().pokemons)
    if num_pokes > 250:
        await discard_all_pokemon(worker)

    excluded_stops = exclusion_pokestops(xp_route_1 + xp_route_2)
    if first_time:
        first_time()
    catch_condition.log_description(phase)
    do_extra_gmo_after_pokestops = False

    for route_element, next_route_element in pairwise(locations):
        if await sm.reached_limits():
            return

        egg_active = await wm.use_egg(cm)
        player_location = get_pos_to_use(route_element)
        next_pos = get_pos_to_use(next_route_element)

        await sm.spin_all_stops(map_objects, player_location, range_m=50 if xp_boost_phase else 39.8, exclusion={} if xp_boost_phase else excluded_stops )

        if pos_index % 10 == 0:
            sm.log_inventory()

        if do_extra_gmo_after_pokestops:
            log.info(u"Wating an extra cycle after fast moves")
            map_objects = await wm.get_map_objects(player_location)

        sm.log_status(egg_active, wm.has_egg, wm.egg_number, pos_index, phase)
        await cm.do_catch_moving(map_objects, player_location, next_pos, pos_index, catch_condition)
        await cm.do_bulk_transfers()

        time_to_location = travel_time.time_to_location(next_pos)
        out_of_eggs = wm.is_out_of_eggs_before_l30()
        if egg_active or out_of_eggs:
            candy_ = worker.account_info()["candy"]
            for evo in range(0, int(math.ceil(time_to_location / 1))):  # todo was 15 but we dont care any more
                await cm.evolve_one(candy_, fast=True)

        if receive_broadcasts:
            while True:
                encs = catch_feed.items[pos_index]
                enc_pos = None
                enc_id = None
                for encounter_id in encs:
                    if encounter_id not in cm.processed_encounters:
                        enc_id = encounter_id
                        enc_pos = encs[enc_id][0]
                if not enc_id:
                    break
                log.info(u"Dealing with nested location {}".format(str(enc_pos)))
                await process_points([encs[enc_id][0], encs[enc_id][0]], xp_boost_phase, NoOpFeed(), cm, sm, wm,
                                     travel_time, worker, phase, catch_condition, receive_broadcasts=False,
                                     pos_index=pos_index)
                # i dont like these heuristics one damn bit
                cm.processed_encounters.add(enc_id)  # this must be done in case there is nothing at the location
                for encounter_id in encs:  # dump all other stuff reported from this location too, we'v been here.
                    if encs[encounter_id][0] == enc_pos:
                        cm.processed_encounters.add(encounter_id)

        slow_time_to_location = travel_time.slow_time_to_location(next_pos)
        use_fast = slow_time_to_location > 20
        travel_time.set_fast_speed( use_fast)

        if use_fast:
            map_objects = await wm.move_to_with_gmo(next_pos,is_fast_speed=use_fast)
            do_extra_gmo_after_pokestops = len(catchable_pokemon(map_objects)) == 0
        else:
            async def catch_moving(po, mo):
                cm.do_catch_moving(mo, po, next_pos, pos_index, catch_condition, broadcast=False)
            map_objects = await wm.move_to_with_gmo(next_pos,is_fast_speed=use_fast, at_location=catch_moving )
            do_extra_gmo_after_pokestops = False
        await cm.do_bulk_transfers()
        if time_to_location > 20:
            cm.clear_state()
        pos_index += 1


async def initial_stuff(feeder, wm, cm, worker):
    await wm.move_to_with_gmo(get_pos_to_use(feeder.peek()))
    wm.explain()
    inv_pokemon = worker.account_info().pokemons
    buddy_id=worker.account_info()["buddy"]
    log.info(u"Byddy id is {}".format(str(buddy_id)))
    nonfavs = [(id_,pokemon) for id_,pokemon in inv_pokemon.items() if is_discardable(id_,pokemon, buddy_id) and not is_starter_pokemon(pokemon)]
    log.info(u"Transferring all pokemon that cant be evolved, considering {} pokemons".format(str(len(nonfavs))))
    for p_id,pokemon in nonfavs:
        pokemon_id = pokemon["pokemon_id"]
        cm.process_evolve_transfer_item(p_id, pokemon_id)
    log.info(u"Evolve-map {}".format(str(cm.evolve_map)))
    await cm.do_transfers()


async def levelup(thread_num, worker, global_catch_feed_, latch, is_forced_update, use_eggs=True, fast_25=False):
    travel_time = worker.getlayer(TravelTime)

    wm = WorkerManager(worker, use_eggs, args.target_level)
    wm.fast_egg = fast_25
    cm = CatchManager(worker, args.catch_pokemon, global_catch_feed_)
    sm = StopManager(worker, cm, wm, args.max_stops)

    app_behaviour = worker.getlayer(ApplicationBehaviour)
    app_behaviour.behave_properly = False

    cm.catch_feed = candy_12_feed
    initial_pokestops = initial_130_stops.get(args.route)
    num_items = max(136, len(initial_pokestops) - thread_num)
    feeder = PositionFeeder(list(reversed(initial_pokestops))[:num_items], is_forced_update)

    if wm.player_level() < 8:
        log.info(u"Doing initial pokestops PHASE")

        await process_points(feeder, False, candy_12_feed, cm, sm, wm, travel_time, worker, 1,
                             CatchConditions.initial_condition())

    sm.clear_state()

    #await latch.count_down()
    #log.info(u"Waiting for other workers to join here")
    #await latch.do_await()


    log.info(u"Main grind PHASE 1")
    wm.explain()
    cm.catch_feed = global_catch_feed_
    feeder = PositionFeeder(routes_p1[args.route], is_forced_update)
    xp_feeder = PositionFeeder(xp_p1[args.route], is_forced_update)
    await initial_stuff(feeder, wm, cm, worker)

    #await latch.count_down()
    #log.info(u"Waiting for other workers to join here")
    #await latch.do_await()

    if not fast_25:
        await process_points(feeder, False, global_catch_feed_, cm, sm, wm, travel_time, worker, 2,
                             CatchConditions.grind_condition())
        await beh_aggressive_bag_cleaning(worker)
    await process_points(xp_feeder, True, global_catch_feed_, cm, sm, wm, travel_time, worker, 3,
                         CatchConditions.grind_condition(), receive_broadcasts=False)

    sm.clear_state()
    cm.evolve_requirement = 90
    log.info(u"Main grind PHASE 2")
    wm.explain()
    cm.catch_feed = global_catch_feed_
    feeder = PositionFeeder(routes_p2[args.route], is_forced_update)
    xp_feeder2 = PositionFeeder(xp_p2[args.route], is_forced_update)
    await initial_stuff(feeder, wm, cm, worker)
    await process_points(feeder, False, global_catch_feed_, cm, sm, wm, travel_time, worker, 4,
                         CatchConditions.grind_condition())
    await beh_aggressive_bag_cleaning(worker)
    if not await sm.reached_limits():
        await process_points(xp_feeder2, True, global_catch_feed_, cm, sm, wm, travel_time, worker, 5,
                             CatchConditions.grind_condition(), receive_broadcasts=False)

    if args.final_system_id:
        await db_set_system_id(worker.name(), args.final_system_id)
        log.info(u"Transferred account {} to system-id {}".format(worker.name(), args.final_system_id))

    log.info(u"Reached end of route with {} spins, going to rest".format(str(len(sm.spun_stops))))


async def startup():
    await account_manager.initialize(args.accountcsv, ())
    forced_update = create_forced_update_check(args)
    nthreads = int(args.thread_count)
    log.info(u"Bot using {} threads".format(str(nthreads)))
    latch = CountDownLatch(nthreads)
    for i in range(nthreads):
        asyncio.ensure_future(safe_levelup(i, global_catch_feed, latch, forced_update))
        if args.proxy and i % len(args.proxy) == 0:
            await asyncio.sleep(10)

set_account_db_args(args, loop)
#loop.run_until_complete(startup())
asyncio.ensure_future(startup())
loop.run_forever()

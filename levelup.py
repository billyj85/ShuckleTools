import asyncio
import logging
import math

from accounts3 import AsyncAccountManager
from argparser import std_config, add_geofence, add_webhooks, add_search_rest, parse_unicode, \
    add_threads_per_proxy, add_use_account_db_true, setup_default_app
from async_accountdbsql import set_account_db_args, db_set_system_id
from behaviours import beh_aggressive_bag_cleaning, discard_all_pokemon
from catchmanager import CatchManager, CatchConditions
from common_accountmanager import OutOfAccounts
from getmapobjects import is_discardable, is_starter_pokemon, catchable_pokemon
from management_errors import GaveUp
from pogoservice import ApplicationBehaviour, TravelTime2
from pokestoproutesv2 import routes_all
from routes.hamburg_xp1 import xp_route_1
from routes.hamburg_xp2 import xp_route_2
from scannerutil import create_forced_update_check, pairwise, write_monocle_accounts_file
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
parser.add_argument('-aec', '--at-end-command', default=None,
                    help='Command to fork at end')

add_webhooks(parser)
add_geofence(parser)
args = parser.parse_args()
loop = asyncio.get_event_loop()
setup_default_app(args, loop)

lock = asyncio.Lock()
num_completed = 0

account_manager = AsyncAccountManager.create_empty(args, loop)
account_manager.reallocate = False

counter = 0
async def safe_levelup(forced_update_):
    global num_completed
    global counter
    worker = None
    while True:
        # noinspection PyBroadException
        try:
            worker = await next_worker()
            if worker:
                await levelup(worker, forced_update_)
                if args.at_end_command:
                    if worker.account_info()["level"] < int(args.target_level):
                        worker.log.error("Account {} did not reach required level".format(str(worker.name())))
                    else:
                        account_file = args.system_id + "{}.csv".format(str(counter))
                        counter += 1
                        cmd_to_use = args.at_end_command.replace("$1", account_file)
                        cmd_to_use = [
                            "python3",
                            "Monkey/scripts/import_accounts.py",
                            account_file,
                            "--level = 30"
                        ]
                        args.at_end_command.replace("$1", account_file)
                        write_monocle_accounts_file([worker.account_info()], account_file)
                        worker.log.info("Running shell command {}",cmd_to_use)
                        process = asyncio.create_subprocess_exec(*cmd_to_use, loop=loop)
                        await process
        except OutOfAccounts:
            worker.log.info("No more accounts, exiting worker thread")
            return
        except GaveUp:
            worker.log.info("Gave UP, exiting")
            return
        except:
            if worker:
                worker.log.exception("Outer worker catch block caught exception")
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

def get_pos_to_use(route_element):
    if type(route_element) is tuple:
        return route_element
    return route_element.coords


def exclusion_pokestops(list_):
    return {y[1] for x in list_ for y in x[1]}


async def process_points(locations, xp_boost_phase, cm, sm, wm, travel_time, worker, phase, excluded_stops):
    first_loc = get_pos_to_use(locations[0])
    worker.log.info(u"First lof {}".format(str(first_loc)))
    map_objects = await wm.move_to_with_gmo(first_loc)

    num_pokes = len(worker.account_info().pokemons)
    if num_pokes > 250:
        await discard_all_pokemon(worker)

    catch_condition = CatchConditions.grind_condition() if worker.account_info()["level"] >= 9 else CatchConditions.pre_l9_condition()
    catch_condition.log_description(phase)
    do_extra_gmo_after_pokestops = False

    pos_index = 0

    for route_element, next_route_element in pairwise(locations):
        if await sm.reached_limits():
            worker.log.info(u"Reached limits inside processing")
            return

        egg_active = await wm.use_egg(cm, xp_boost_phase)
        player_location = get_pos_to_use(route_element)
        next_pos = get_pos_to_use(next_route_element)

        await sm.spin_all_stops(map_objects, player_location, range_m=50, exclusion={} if xp_boost_phase else excluded_stops )

        if pos_index % 10 == 0:
            sm.log_inventory()

        if do_extra_gmo_after_pokestops:
            worker.log.info(u"Wating an extra cycle after fast moves")
            map_objects = await wm.get_map_objects(player_location)

        sm.log_status(egg_active, wm.has_egg, wm.egg_number, pos_index, phase)
        await cm.do_catch_moving(map_objects, player_location, next_pos, catch_condition, wm.is_any_egg(), greedy=xp_boost_phase)
        await cm.do_bulk_transfers()

        time_to_location = travel_time.time_to_location(next_pos)
        out_of_eggs = wm.is_out_of_eggs_before_l30()
        if egg_active or out_of_eggs:
            candy_ = worker.account_info()["candy"]
            for evo in range(0, int(math.ceil(time_to_location / 1))):  # todo was 15 but we dont care any more
                await cm.evolve_one(candy_, fast=True)

        slow_time_to_location = travel_time.slow_time_to_location(next_pos)
        use_fast = slow_time_to_location > 20
        travel_time.set_fast_speed( use_fast)

        if use_fast:
            map_objects = await wm.move_to_with_gmo(next_pos,is_fast_speed=use_fast)
            do_extra_gmo_after_pokestops = len(catchable_pokemon(map_objects)) == 0
        else:
            async def catch_moving(po, mo):
                cm.do_catch_moving(mo, po, next_pos, catch_condition, wm.is_any_egg(), greedy=xp_boost_phase)
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
    worker.log.info(u"Byddy id is {}".format(str(buddy_id)))
    nonfavs = [(id_,pokemon) for id_,pokemon in inv_pokemon.items() if is_discardable(worker, id_,pokemon, buddy_id) and not is_starter_pokemon(pokemon)]
    worker.log.info(u"Transferring all pokemon that cant be evolved, considering {} pokemons".format(str(len(nonfavs))))
    for p_id,pokemon in nonfavs:
        pokemon_id = pokemon["pokemon_id"]
        cm.process_evolve_transfer_item(p_id, pokemon_id)
    worker.log.info(u"Evolve-map {}".format(str(cm.evolve_map)))
    await cm.do_transfers()


async def levelup(worker, is_forced_update, use_eggs=True):
    travel_time = worker.getlayer(TravelTime2)

    wm = WorkerManager(worker, use_eggs, args.target_level)
    cm = CatchManager(worker, args.catch_pokemon)
    sm = StopManager(worker, cm, wm, args.max_stops)

    app_behaviour = worker.getlayer(ApplicationBehaviour)
    app_behaviour.behave_properly = False

    full_route = routes_all[args.route]
    phase = 0

    excluded_stops = exclusion_pokestops(xp_route_1 + xp_route_2)
    for phaseNo, route_obj in enumerate(full_route):
        grind_feed = PositionFeeder(route_obj["grind"], is_forced_update)
        sm.clear_state()
        worker.log.info(u"Main grind PHASE {}".format(str(phaseNo)))
        wm.explain()
        await initial_stuff(grind_feed, wm, cm, worker)
        phase += 1
        await process_points(grind_feed, False, cm, sm, wm, travel_time, worker, phase, excluded_stops)
        await beh_aggressive_bag_cleaning(worker)
        phase += 1
        if await sm.reached_limits():
            break
        xp_feeder = PositionFeeder(route_obj["xp"], is_forced_update)
        await process_points(xp_feeder, True, cm, sm, wm, travel_time, worker, phase, {})
        if await sm.reached_limits():
            break

    if args.final_system_id:
        await db_set_system_id(worker.name(), args.final_system_id)
        worker.log.info(u"Transferred account {} to system-id {}".format(worker.name(), args.final_system_id))

    worker.log.info(u"Reached end of routes with {} spins, going to rest".format(str(len(sm.spun_stops))))


async def startup():
    await account_manager.initialize(args.accountcsv, ())
    forced_update = create_forced_update_check(args)
    nthreads = int(args.thread_count)
    log = logging.getLogger(__name__)
    log.info(u"Bot using {} threads".format(str(nthreads)))
    for i in range(nthreads):
        asyncio.ensure_future(safe_levelup(forced_update))
        if args.proxy and i % len(args.proxy) == 0:
            await asyncio.sleep(10)

set_account_db_args(args, loop)
#loop.run_until_complete(startup())
asyncio.ensure_future(startup())
loop.run_forever()

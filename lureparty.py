import asyncio
import codecs
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import cycle

from aiohttp import web

from accounts3 import AsyncAccountManager
from apiwrapper import CodenameResult
from argparser import std_config, parse_unicode, add_search_rest, add_webhooks, location_parse, \
    add_geofence, setup_default_app, add_use_account_db_true
from async_accountdbsql import load_accounts_for_lures
from common_accountmanager import OutOfAccounts
from geofence import group_by_geofence
from gymdbsql import pokestops
from luredbsql import set_lure_db_args, lures, db_move_to_levelup, db_move_to_trash
from lureworker import LureWorker, FileLureCounter, DbLureCounter
from pogom.fnord_altitude import with_gmaps_altitude
from scannerutil import chunks, stop_at_datetime, start_at_datetime, is_blank
dirname = os.path.dirname(os.path.realpath(__file__))

parser = std_config("std_lureparty")
add_search_rest(parser)
add_webhooks(parser)
add_geofence(parser)
add_use_account_db_true(parser)
parser.add_argument('-ps', '--pokestops', default=None, action='append',
                    help='Pokestops to lure')
parser.add_argument('-jlo', '--json-locations', type=parse_unicode,
                    help='Json file with luring descriptions')
parser.add_argument('-rl', '--route-length', default=5,
                    help='Length of the luring routes to use')
parser.add_argument('-ow', '--system-id', type=parse_unicode,
                    help='Database owner of lures')
parser.add_argument('-bn', '--base-name', default=None, action='append',
                    help='Base name(s) of accounts for branding')
parser.add_argument('-nl', '--num-lures', default=24,
                    help='Number of lures to place before exiting')
parser.add_argument('-lurdur', '--lure-duration', default=30,
                    help='The number of minutes lures last')
parser.add_argument('-b64', '--base64', default=False,
                    help='Use base64 with number')
parser.add_argument('-stop', '--stop-at', default=None,
                    help='Time of day to stop in 24-hr clock: eg 18:02')
parser.add_argument('-host', '--host', default="127.0.0.1",
                    help='port for lure dump server')
parser.add_argument('-p', '--port', default=None,
                    help='port for lure dump server')
args = parser.parse_args()
loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

set_lure_db_args(args)

db_move_to_levelup(args.system_id, "forlevelup")
db_move_to_trash(args.system_id, "trash")

LURE_COUNT = args.system_id + '_lure_count.txt'
if os.path.isfile(LURE_COUNT):
    with open(LURE_COUNT, 'r') as f:
        for line in f:
            lure_count = int(line)
            break
else:
    lure_count = 0
if lure_count > args.num_lures:
    log.info(u"Target lure count reached, exiting")
    sys.exit(0)

LURE_FILE = 'lure_number.txt'
if os.path.isfile(LURE_FILE):
    with open(LURE_FILE, 'r') as f:
        for line in f:
            idx = int(line)
            break
else:
    idx = 1

log.info(u"Branding sequence number is {}".format(str(idx)))

lock = asyncio.Lock()

account_manager = None

namecycler = None
if args.base_name:
    namecycler = cycle(args.base_name)
else:
    log.warning("No branding configured")

use_b64 = args.base64

stop_at = None
if args.stop_at:
    dur_str = "100:00:00"
    h, m = list(map(int, args.stop_at.split(':')))
    stop_at = datetime.now().replace(hour=h, minute=m)
    msg = "Stopping at {}".format(str(stop_at))
    if stop_at < datetime.now():
        stop_at += timedelta(days=1)
        msg = "Stopping at {} (tomorrow)".format(str(stop_at))
    log.info(msg)


async def fix_branding(worker):
    global idx
    info = worker.account_info()
    codename = info.get("codename", None)
    if info["remaining_codename_claims"] == 0:
        log.info(u"Account has no more name changes, existing trainer name is {}".format(codename))
        return worker

    if not namecycler:
        return worker

    if codename:
        for baseName in args.base_name:
            if codename.startswith(baseName):
                log.info(u"Account already branded to {}, not doing anything".format(worker.account_info()["codename"]))
                return worker

    async with lock:
        s = str(idx)
        b64s = s.encode('base64').replace("=", "").rstrip() if use_b64 else s
        branded_name = next(namecycler) + b64s
        idx += 1
        with open(LURE_FILE, "w") as text_file:
            text_file.write(str(idx))
    res = await worker.do_claim_codename(branded_name)
    result = CodenameResult(res)
    if result.ok():
        log.info(u"Account branded to {}".format(branded_name))
    else:
        log.info(u"Account NOT branded to ->{}<-".format(branded_name))
    return worker


def deploy_more_lures(lure_dropped):
    global lure_count
    if lure_dropped:
        lure_count += 1
    if lure_count > args.num_lures:
        log.info(u"Target lure count reached, exiting")
        return False
    if stop_at and datetime.now() > stop_at:
        log.info(u"Reached stop-at time, exiting")
        return False
    return True


def will_start_now(json_location):
    start = json_location["start"]
    end = json_location["end"]
    days = json_location["days"]
    if is_blank(days):
        return False
    start_at = start_at_datetime(start)
    stop_time = stop_at_datetime(start, end)
    now = datetime.now()
    return start_at < now < stop_time

def after_stop(json_location):
    start = json_location["start"]
    end = json_location["end"]
    stop_time = stop_at_datetime(start, end)
    now = datetime.now()
    return now > stop_time


async def safe_lure_one_json_worker(json_location, route_section, counter):
    global account_manager
    while True:
        start = json_location["start"]
        end = json_location["end"]
        name_ = json_location["name"]
        days = json_location["days"]
        if is_blank(days):
            log.info(u"No days sceheduled for {}, terminating thread".format(name_))
            return
        start_at = start_at_datetime(start)
        stop_time = stop_at_datetime(start, end)
        now = datetime.now()

        await sleep_if_outside_period(json_location)

        weekday = str(datetime.today().weekday())
        if weekday not in days:
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_morning = tomorrow.replace(hour=0, minute=1)
            seel_dur = (tomorrow_morning - now).total_seconds()
            log.info(u"Not today, waiting {} seconds until tomorrow".format(seel_dur))
            await asyncio.sleep(seel_dur)
        else:
            log.info(u"{} running until {}".format(name_, stop_time))
            try:
                ld = LureWorker(account_manager, fix_branding, lambda lure_dropped: datetime.now() < stop_time, counter,  args.lure_duration)
                as_coordinates = [location_parse(x) for x in route_section]
                await ld.lure_json_worker_positions(as_coordinates)
                await asyncio.sleep(60)
            except OutOfAccounts:
                log.warning("No more accounts, exiting")
                return
            except Exception as e:
                log.exception(e)
                await asyncio.sleep(12)


async def sleep_if_outside_period(json_location):
    start_at = json_location["start"]
    stop_time = json_location["end"]
    name_ = json_location["name"]

    now = datetime.now()

    if not will_start_now(json_location):
        if after_stop(json_location):
            sleep_dur = ((start_at_datetime(start_at) + timedelta(days=1)) - now).total_seconds()
        else:
            sleep_dur = (start_at_datetime(start_at) - now).total_seconds()
        if sleep_dur < 0:
            sleep_dur = abs(sleep_dur)
        log.info(
            u"{} outside running period ({}->{}), sleeping {} seconds".format(name_, start_at, stop_time, sleep_dur))
        await asyncio.sleep(sleep_dur)
        return True


# noinspection PyUnusedLocal
async def index(request):
    pokemon = os.path.dirname(os.path.abspath(os.path.realpath(__file__))) + "/static/html/lureparty.html"
    with codecs.open(pokemon, "r", encoding="utf-8") as input_file:
        data = input_file.read()
        return web.Response(body=data, content_type="text/html")

async def post_lure_request(request):
    user = request.match_info['user']
    data = await request.post()
    projectpath = data['Position1']
    return await lure_bomb_do_get( user, projectpath, 120)

async def lure_bomb_radius_get(request):
    user = request.match_info['user']
    position = request.match_info['position']
    minutes = request.match_info['minutes']
    radius = int(request.match_info['radius'])
    return await lure_bomb_dccccccgcdlttgniivveukglrjgttutdrtvthuubutnjg
    o_get(user, position, minutes,radius)

async def lure_bomb_get(request):
    user = request.match_info['user']
    position = request.match_info['position']
    minutes = request.match_info['minutes']
    radius = 50
    return await lure_bomb_do_get(user, position, minutes,radius)


async def lure_bomb_do_get(user, position, minutes, radius=50):
    global account_manager
    parsed = location_parse(position.strip())
    pos = with_gmaps_altitude(parsed, args.gmaps_key)
    log.info(u"Received luring request for {} at {} for {} minutes".format(user, str(pos), str(minutes)))

    lures1 = lures(user)
    if len(lures1) == 0:
        web.Response(status=404)
    if pos is None:
        return "Missing coordinates for luring. Ensure page has location access and use a proper browser (safari/chromet etc, not the facebook browser)"
    max_lures = lures1[0]["max_lures"]
    current_lures = lures1[0].get("lures", 0)
    remaining_lures = max_lures - current_lures
    if max_lures <= current_lures:
        return "All {} lures are spent".format(lures1.max_lures)
    ld = LureWorker(account_manager, fix_branding, should_continue(int(minutes)), DbLureCounter(user), args.lure_duration)
    asyncio.ensure_future(ld.lure_bomb(pos, radius), loop=loop)
    db_move_to_levelup(args.system_id, "forlevelup")
    db_move_to_trash(args.system_id, "trash")

    return web.Response(text="<h2>Luring at {}, be a little patitent. You have {} lures left</h2>".format(str(pos), str(remaining_lures)))

def should_continue(minutes_to_run=120):
    end_at = datetime.now() + timedelta(minutes=minutes_to_run)

    def cont(lure_dropped):
        return datetime.now() < end_at
    return cont



if args.geofence:
    geofence_stops = group_by_geofence(pokestops(), args.geofence, args.fencename)
else:
    geofence_stops = defaultdict(list)

num_proxies = len(args.proxy) if args.proxy else 1


async def lure_one_route(json_loc, routes):
    route_name = json_loc["name"]
    while await sleep_if_outside_period(json_loc):
        log.info("Sleeping again for {}".format(route_name))

    worker_idx = 0
    route_names = json_loc["route"]
    counter = FileLureCounter(json_loc)
    for route_name in route_names.split(","):
        if route_name in geofence_stops:
            worker_route = geofence_stops[route_name]
        else:
            worker_route = routes[route_name]

        for route in chunks(worker_route, int(args.route_length)):
            name = route_name[:14] + "-" + str(worker_idx)
            worker_idx += 1
            asyncio.ensure_future(safe_lure_one_json_worker(json_loc, route, counter))
            if will_start_now(json_loc) and (not args.overflow_hash_key or worker_idx % num_proxies == 0):
                await asyncio.sleep(15)



async def start():
    global account_manager
    account_manager = await AsyncAccountManager.create_standard(args, load_accounts_for_lures)
    account_manager.remove_accounts_without_lures()
    if args.json_locations:
        log.info(u"Geofences are: {}".format(str(geofence_stops.keys())))
        with open(args.json_locations) as data_file:
            try:
                json_config = json.load(data_file)
            except ValueError:
                log.error("Failed to load JSON, malformed file. Use an online JSON validator to check it")
                raise

            routes = json_config["routes"]
            for json_loc in json_config["schedules"]:
                asyncio.ensure_future(lure_one_route(json_loc, routes))


asyncio.ensure_future(start())
if args.port:
    app = web.Application()
    app.router.add_resource('/lurebomb/{user}/').add_route('GET', index)
    app.router.add_resource('/lures/{user}/{position}/{minutes}').add_route('GET', lure_bomb_get)
    app.router.add_resource('/lures/{user}/{position}/{minutes}/{radius}').add_route('GET', lure_bomb_radius_get)
    app.router.add_resource('/lurebomb/{user}/lurebomb').add_route('POST', post_lure_request)
    web.run_app(app, host=args.host, port=int(args.port))
else:
    loop.run_forever()

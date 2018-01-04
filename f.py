import asyncio
from datetime import datetime
from threading import Thread

import logging
from flask import Flask, request

import pokemonhandler
from accounts3 import AsyncAccountManager
from argparser import std_config, location_parse, parse_unicode, add_search_rest, add_webhooks, \
    setup_default_app, add_use_account_db_true
from fw import FeedWorker, safe_berry_one_position
from pogom.fnord_altitude import with_gmaps_altitude, add_gmaps_altitude
from pogom.utils import gmaps_reverse_geolocate
from scannerutil import stop_at_datetime

parser = std_config("generic_feeder")
add_search_rest(parser)
add_webhooks(parser)
add_use_account_db_true(parser)
parser.add_argument('-llocs', '--lowfeed-locations', type=parse_unicode, default=[],
                    help='Location,     can be an address or coordinates.')
parser.add_argument('-locs', '--locations', type=parse_unicode, default=[],
                    help='Location, can be an address or coordinates.')
parser.add_argument('-hlocs', '--heavy-locations', type=parse_unicode, default=[],
                    help='Location, can be an address or coordinates.')
parser.add_argument('-tr', '--trainers', type=parse_unicode,
                    help='Trainers required for feeding.', action='append')
parser.add_argument('-ow', '--system-id', type=parse_unicode,
                    help='Database owner of lures')
parser.add_argument('-hvy', '--heavy-defense', type=parse_unicode,
                    help='heacy defense', default=False)
parser.add_argument('-stop', '--stop-at', default=None,
                    help='Time of day to stop in 24-hr clock: eg 18:02')
parser.add_argument('-s2', '--s2-hook', default=None,
                    help='s2hook')
parser.add_argument('-host', '--host', default="127.0.0.1",
                    help='port for server')
parser.add_argument('-p', '--port', default=None,
                    help='port for server')


app = Flask(__name__, static_url_path='')

args = parser.parse_args()

loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)
pokemonhandler.set_args(args)

account_manager = None
@app.route('/f', methods=['GET'])
def index():
    return app.send_static_file("html/f.html")


@app.route('/fd', methods=['POST'])
def f_post():
    projectpath = request.form['Position1']
    log.info("POST request for {}".format(str(projectpath)))
    if not projectpath:
        return "Did not receive coordinates"
    return f_get(projectpath)


@app.route('/f/<position>', methods=['GET'])
def f_get(position):
    pos = location_parse(position.strip())
    log.info(u"Received request for {}".format(str(pos)))

    if pos is None:
        return "Missing coordinates. Ensure page has location access and use a proper browser (safari/chromet etc, not the facebook browser)"
    asyncio.set_event_loop(loop)
    feed_worker = FeedWorker(account_manager, termination_condition, args.trainers, False, True)
    asyncio.ensure_future(safe_berry_one_position(pos, feed_worker))

    return "Starting at {}, be a little patitent ".format(str(pos))


def run_server():
    app.run(threaded=True, host=args.host, port=int(args.port))


if args.port:
    the_thread = Thread(name="FServer", target=run_server)
    the_thread.start()

locs = [with_gmaps_altitude(location_parse(x), args.gmaps_key) for x in args.locations.strip().split(' ')]
position = locs[0]
args.player_locale = gmaps_reverse_geolocate(
    args.gmaps_key,
    args.locale,
    str(position[0]) + ', ' + str(position[1]))



stop_at = None
if args.stop_at:
    stop_at = stop_at_datetime( args.start_at, args.stop_at)
    msg = "Stopping at {}".format(str(stop_at))
    log.info(msg)


def termination_condition():
    if stop_at and datetime.now() > stop_at:
        log.info(u"Reached stop-at time, exiting")
        return True
    return False

log.info(u"Using locations {}".format(str(args.locations)))

async  def startup():
    global account_manager
    account_manager = await AsyncAccountManager.create_standard(args, loop)
    for loc in locs:
        asyncio.ensure_future(safe_berry_one_position(loc, FeedWorker(account_manager, termination_condition, args.trainers, True, False)))
        await asyncio.sleep(10)

    if args.heavy_locations:
        heavy_locs = add_gmaps_altitude(args, args.heavy_locations)
        for loc in heavy_locs:
            asyncio.ensure_future(safe_berry_one_position(loc, FeedWorker(account_manager, termination_condition, args.trainers, True, True)))
            await asyncio.sleep(5)

    if args.lowfeed_locations:
        for loc in add_gmaps_altitude(args, args.lowfeed_locations):
            asyncio.ensure_future(safe_berry_one_position(loc, FeedWorker(account_manager, termination_condition, args.trainers, False, True)))
            await asyncio.sleep(5)


asyncio.ensure_future(startup())
loop.run_forever()


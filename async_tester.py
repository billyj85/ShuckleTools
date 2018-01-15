import asyncio
import signal
import sys

import logging

from apiwrapper import EncounterPokemon
from async_accountdbsql import set_account_db_args
from accounts3 import AsyncAccountManager
from argparser import std_config, add_system_id, add_use_account_db, setup_proxies
from behaviours import beh_catch_encountered_pokemon
from getmapobjects import inrange_pokstops, catchable_pokemon, \
    inrange_gyms
from gymdbsql import set_gymdb_args
from scannerutil import setup_logging
from workers import wrap_account_no_replace

setup_logging()
log = logging.getLogger(__name__)

parser = std_config("gymscanner")
add_system_id(parser)
add_use_account_db(parser)
args = parser.parse_args()
setup_proxies(args)
set_gymdb_args(args)
loop = asyncio.get_event_loop()
set_account_db_args(args, loop)


args.player_locale = {'country': 'NO', 'language': 'no', 'timezone': 'Europe/Oslo'}

'''
g0g3m3sh89896:&PB&nQ3YH used 31. oc
g0g3m3sh89912:SaH7QKq@C used 9 nov
g0g3m3sh89863:kt#9r&MnG used 20 nov
g0g3m3sh89910:T!2YAMu2k 27 nov
g0g3m3sh89905:uYRST9@Bg
g0g3m3sh89919:MKG#6s!E3
g0g3m3sh89890:#MBYk6uAa
g0g3m3sh89864:3&mjdpE^s
'''


stop_1=(((59.908411, 10.7760670), "1707f1339e454eaba3e69ff443729f9d.16"),((59.910564, 10.7613160), "f3650447ae6048599655b034b478d5f7.16"))
stop_2=(((59.907937, 10.7765390), "07ae3ee4757f4049b13811dabed2fdc0.11"),((59.910775, 10.7607610), "d64de98d135d48bd884fa300c6ba53e4.16"))
stop_3=(((59.907934, 10.7759700), "9f9196aa884949bc88bf7fdb32e4ec5f.16"),((59.911297, 10.7577550), "783677808da1472b8ee1ac9ed02fc65d.11"))
stop_4=(((59.904540, 10.7665610), "787da22ba5e54bf094210927b6716b85.16"),((59.909709, 10.7473550), "49b6c17d820d42a7ab43b7b8075da170.16"))
stop_5=(((59.904737, 10.7671730), "3d903c4baf0a46e3a74821168092cf11.16"),((59.908853, 10.7559040), "04fb2625ff6345ba956d5bb12c557940.16"))
stop_6_3km=(((59.907326, 10.7853680), "09abf40d1abf413990a4ff12f81734fb.16"),((59.912380, 10.7312300), "10e4324fc7684c3594b976a4b114d312.16"))


async def async_sleeper(x):
    asyncio.ensure_future(await asyncio.sleep(x), loop=loop)

def signal_handler(signal, frame):
    loop.stop()
    sys.exit(0)

'''
jENniNE7200097:dqyLZG733_/! used 15 jan
LaToNYA8551181:xzcAZZ472-+?
tAD82591895214:ctjFLW278*_?
DUnCAn47819481:odtMLQ994%!/
TENisHA4676564:cwkMAM955{?*
jaRrEd15227952:fsyHFZ452$}{
Mi250155810631:groZBA964?-%
krySTiNA210758:sfjAWJ955?}!
CarRie35436367:eqrKZH442?%=
g0g3m3sh89896:&PB&nQ3YH used 31. oc
g0g3m3sh89912:SaH7QKq@C used 9 nov
g0g3m3sh89863:kt#9r&MnG used 20 nov
g0g3m3sh89910:T!2YAMu2k 27 nov
g0g3m3sh89905:uYRST9@Bg
g0g3m3sh89919:MKG#6s!E3
g0g3m3sh89890:#MBYk6uAa
g0g3m3sh89864:3&mjdpE^s
'''
async def do_stuff():
    account_manager = AsyncAccountManager.create_empty(args, loop)
    l5account = account_manager.add_account({"username": "LaToNYA8551181", "password": "xzcAZZ472-+?", "provider": "ptc"})
    worker = wrap_account_no_replace(l5account, account_manager, 25)

    pos = (59.934393, 10.718153, 10)
    map_objects = await worker.do_get_map_objects(pos)
    pokestops = inrange_pokstops(map_objects, pos)
    gyms = inrange_gyms(map_objects, pos)

    cp = catchable_pokemon(map_objects)
    to_catch = cp[0]
    encounter_id = to_catch.encounter_id
    spawn_point_id = to_catch.spawn_point_id
    pokemon_id = to_catch.pokemon_id
    encounter_response = await worker.do_encounter_pokemon(encounter_id, spawn_point_id, pos)
    probability = EncounterPokemon(encounter_response, encounter_id).probability()
    if probability and len([x for x in probability.capture_probability if x > 0.38]) > 0:
        caught = await beh_catch_encountered_pokemon(worker, pos, encounter_id, spawn_point_id, probability,
                                                     pokemon_id, False, fast=True)
        print(caught)


    gym = gyms[0]
    await worker.do_spin_pokestop(gym, pos)


signal.signal(signal.SIGINT, signal_handler)
# asyncio.ensure_future(do_stuff())
loop.run_until_complete(do_stuff())



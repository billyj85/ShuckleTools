import asyncio
import signal
import sys

import logging

from async_accountdbsql import set_account_db_args
from accounts3 import AsyncAccountManager
from argparser import std_config, add_system_id, add_use_account_db, setup_proxies
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



async def async_sleeper(x):
    asyncio.ensure_future(await asyncio.sleep(x), loop=loop)

def signal_handler(signal, frame):
    loop.stop()
    sys.exit(0)

'''
jENniNE7200097:dqyLZG733_/!
LaToNYA8551181:xzcAZZ472-+?
tAD82591895214:ctjFLW278*_?
DUnCAn47819481:odtMLQ994%!/
TENisHA4676564:cwkMAM955{?*
jaRrEd15227952:fsyHFZ452$}{
Mi250155810631:groZBA964?-%
krySTiNA210758:sfjAWJ955?}!
CarRie35436367:eqrKZH442?%=
'''
async def do_stuff():
    account_manager = AsyncAccountManager.create_empty(args, loop)
    l5account = account_manager.add_account({"username": "jENniNE7200097", "password": "dqyLZG733_/!", "provider": "ptc"})
    worker = wrap_account_no_replace(l5account, account_manager, 25)

    pos = (59.934393, 10.718153, 10)
    map_objects = await worker.do_get_map_objects(pos)
    pokestops = inrange_pokstops(map_objects, pos)
    gyms = inrange_gyms(map_objects, pos)

    cp = catchable_pokemon(map_objects)
    gym = gyms[0]
    await worker.do_spin_pokestop(gym, pos)


signal.signal(signal.SIGINT, signal_handler)
# asyncio.ensure_future(do_stuff())
loop.run_until_complete(do_stuff())



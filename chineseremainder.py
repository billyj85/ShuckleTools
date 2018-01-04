import asyncio
from itertools import cycle

import logging

from async_accountdbsql import set_account_db_args
from argparser import std_config, load_proxies, setup_default_app
from getmapobjects import wild_pokemon, catchable_pokemon, nearby_pokemon, s2_cell_ids, regular_nonfav, all_pokemon_pokedex_ids
from gymdbsql import set_gymdb_args
from pogoservice import Account2
from scannerutil import install_thread_excepthook


parser = std_config("gymscanner")
args = parser.parse_args()
loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

load_proxies(args)
set_gymdb_args(args)
set_account_db_args(args)

install_thread_excepthook()

queue = []



#Q pos = (59.902942, 10.8763150)
#pos = (59.900179, 10.860831)
#pos= (59.926051, 10.703054)   # frognerparken 4 stop
#pos = (59.935523, 10.719660)   # marienlyst
pos=(59.908326, 10.722739) # akerbrygge
'''
Call 5062448961839693824
59.90692377930243,10.722713849061687
'''

l5account = Account2("AahOuDaNos", "Freedom4@ll", "ptc", args, 7200, 1800, cycle(args.hash_key), None, {}, None)
l5obj = l5account.do_get_map_objects(pos)
print((l5account["level"]))
print((str(catchable_pokemon(l5obj))))

pokemons = all_pokemon_pokedex_ids(l5obj)

pokemon = regular_nonfav(l5obj)
data_ = pokemon[3]["pokemon_data"]
id_ = data_["id"]
l5account.do_set_favourite(id_, True)
for cellid in s2_cell_ids(l5obj):
    print(str(cellid))

l6account = Account2("ActOuDaGum", "Freedom4@ll", "ptc", args, 7200, 1800, cycle(args.hash_key), None, {}, None)
l6obj = l6account.get_map_objects(pos)
print((l5obj["level"]))

scan_wilds = wild_pokemon(l6obj)
scan_catchable = catchable_pokemon(l6obj)
scan_nearby = nearby_pokemon(l6obj)
wild6 = scan_wilds[0]
print(str(wild6))




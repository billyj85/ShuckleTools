import asyncio
import os
import sys
from itertools import cycle

from queue import Queue, PriorityQueue

from async_accountdbsql import set_account_db_args
from accounts3 import AsyncAccountManager
from argparser import std_config, load_proxies, add_geofence
from behaviours import beh_safe_scanner_bot
from gymdbsql import set_gymdb_args, most_recent_trainer_gyms
from scannerutil import *
from workers import wrap_account

logging.basicConfig(
    format='%(asctime)s [%(threadName)12s][%(module)10s][%(levelname)8s] ' +
           '%(message)s', level=logging.INFO)
log = logging.getLogger(__name__)
logging.getLogger("pgoapi").setLevel(logging.WARN)
logging.getLogger("connectionpool").setLevel(logging.WARN)
logging.getLogger("Account").setLevel(logging.INFO)


'''
Schema changes:
alter table gymmember add column first_seen datetime null;
alter table gymmember add column last_no_present datetime null;
'''

parser = std_config("gymwatcher")
add_geofence(parser)
parser.add_argument('-c', '--crooks',
                    help='Crooks',
                    action='append', default=[])

args = parser.parse_args()
loop = asyncio.get_event_loop()
args.system_id="gymwatcher"
load_proxies(args)
set_gymdb_args(args)
set_account_db_args(args, loop)


install_thread_excepthook()

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

fail_on_forced_update(args)

queue = PriorityQueue()
dbqueue = Queue()


seen_gyms = {}

running = True

def find_top_n(gyms, all_scanned_gyms, n):
    result = {}
    for gym in gyms:
        id_ = gym["gym_id"]
        if id_ not in all_scanned_gyms:
            result[id_] = gym
            all_scanned_gyms[id_] = gym
        if len(result) > n:
            break
    return result

async def start():
    account_manager = await AsyncAccountManager.create_standard(args, loop)
    all_scanned_gyms = {}
    for crook in args.crooks:
        crook_gyms = most_recent_trainer_gyms(crook)
        gym_map = find_top_n(crook_gyms, all_scanned_gyms, 30)
        #gym_map = filter_for_geofence(gym_map, args.geofence, args.fencename)
        print("There are {} gyms in scan with fence {}".format(str(len(gym_map)), str(args.fencename)))
        scanners = []
        for idx, stream in gym_map.items():
            account = await account_manager.get_account()
            scanner = wrap_account(account, account_manager)
            scanners.append(scanner)
            asyncio.ensure_future(beh_safe_scanner_bot(scanner, cycle([stream])))
            await asyncio.sleep(2)

    log.info("exiting scanner")
    sys.exit()

asyncio.ensure_future(start())
loop.run_forever()


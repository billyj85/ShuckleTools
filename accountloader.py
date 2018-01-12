import asyncio
import datetime
import logging

from concurrent.futures import ThreadPoolExecutor, as_completed

from async_accountdbsql import db_set_perm_banned, \
    db_set_temp_banned
from accountmanager import args
from accounts3 import AsyncAccountManager
from argparser import location_parse, setup_default_app
from argutils import thread_count
from common_blindcheck import proceed
from inventory import egg_count, lure_count
from pogom.account import LoginSequenceFail, TooManyLoginAttempts
from pogom.apiRequests import AccountBannedException
from workers import wrap_accounts_minimal

loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

def set_account_level_from_args(accounts):
    if args.level and accounts:
        for acc in accounts:
            acc["level"] = args.level

monocle_accounts = AsyncAccountManager.load_accounts(args.accountcsv)
if not args.login:
    set_account_level_from_args(monocle_accounts)
duration = datetime.timedelta(hours=int(args.allocation_duration)) if args.allocation_duration else None

location = location_parse(args.location)
account_manager = AsyncAccountManager.create_empty(args, loop)


async def check_account(delay):
    wrapped = wrap_accounts_minimal(await account_manager.get_account(), account_manager)
    try:
        await asyncio.sleep( delay)
        return await wrapped.login(location, proceed)
    except LoginSequenceFail:
        db_set_perm_banned(wrapped.account_info(), datetime.datetime.now())
    except TooManyLoginAttempts:
        db_set_perm_banned(wrapped.account_info(), datetime.datetime.now())
    except AccountBannedException:
        db_set_temp_banned(wrapped.name(), datetime.datetime.now())
    except Exception:
        log.exception("Something bad happened")

num_proxies = len(args.proxy) if args.proxy else 1

async def start():
    await account_manager.insert_accounts(loop, monocle_accounts, args.system_id, duration, args.force_system_id,
                                    args.skip_assigned, args.overwrite_level)
    print("Inserted accounts")
    await AsyncAccountManager.create_standard(args, loop)
    if args.login:
        with ThreadPoolExecutor(thread_count(args)) as pool:
            futures = []

            # todo: fix asyncio
            for counter in range(0, account_manager.size()):
                # probably terminates too early since using run_until_complete
                await check_account(4 if num_proxies < counter < (num_proxies*2) else 0)

            results = [r.result() for r in as_completed(futures)]
            return results

loop.run_until_complete(start())



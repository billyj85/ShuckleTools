import asyncio
import csv
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from async_accountdbsql import set_account_db_args, db_find_allocatable_by_level, db_roll_allocated_date_forward, \
    db_set_allocated_time, db_set_system_id, update_allocation_end
from accountmanager import args
from accounts3 import AsyncAccountManager
from argparser import location_parse, load_proxies, setup_default_app
from argutils import thread_count
from common_blindcheck import check_worker_for_future
from pogom.apiRequests import set_goman_hash_endpoint
from pogom.proxy import check_proxies
from scannerutil import as_str

loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

account_manager = None


async def find_accounts():
    temp_ban_time = datetime.datetime.now() - datetime.timedelta(days=45)
    warn_time = datetime.datetime.now() - datetime.timedelta(days=45)
    perm_ban_time = datetime.datetime.now() - datetime.timedelta(days=60)
    blind_time = datetime.datetime.now() - datetime.timedelta(days=45)

    allocatable = await db_find_allocatable_by_level(temp_ban_time, perm_ban_time, warn_time, blind_time, datetime.datetime.now(),
                                               args.min_level, args.max_level)

    requred_accounts = int(args.count)
    futures = []

    account_iter = iter(allocatable)

    def next_account():
        return account_manager.add_account(next(account_iter))

    location = location_parse(args.location)
    result = []
    if args.no_login:
        for i in range(0, requred_accounts):
            result.append( next_account())
    else:
        for idx in range(0, requred_accounts):
            futures.append(asyncio.ensure_future(check_worker_for_future(next_account(), account_manager, location, args)))

        future_pos = 0
        while len(result) < requred_accounts:
            if future_pos > len(futures):
                raise AssertionError("This should not happen, maybe previous error is making it happen")
            r = futures[future_pos].result()
            if r[0]:
                result.append(r[1])
                log.info(u"{} of {} found".format(str(len(result)), str(requred_accounts)))
            else:
                db_roll_allocated_date_forward(r[1])
                futures.append(asyncio.ensure_future(check_worker_for_future(next_account(), account_manager, location, args)))
            future_pos += 1
    return result


def write_rocketmap_accounts_file(accounts):
    from collections import OrderedDict
    ordered_fieldnames = OrderedDict(
        [('provider', None), ('username', None), ('password', None)])
    with open(args.accountcsv, 'w') as fou:
        dw = csv.DictWriter(fou, delimiter=',', fieldnames=ordered_fieldnames, extrasaction='ignore')
        for acct in accounts:
            dw.writerow(acct)


def as_map(account):
    res = {"username": as_str(account.name()), "password": as_str(account.password), "provider": account.auth_service}
    return res


def write_monocle_accounts_file(accounts):
    from collections import OrderedDict
    ordered_fieldnames = OrderedDict(
        [ ('username', None), ('password', None), ('provider', None), ('model', None), ('iOS', None), ('id', None)])
    with open(args.accountcsv, 'w') as fou:
        dw = csv.DictWriter(fou, delimiter=',', fieldnames=ordered_fieldnames)
        dw.writeheader()
        for acct in accounts:
            dw.writerow(as_map(acct))

async def start():
    global account_manager
    account_manager = AsyncAccountManager.create_empty(args, loop)
    accts = await find_accounts()
    if args.format == "monocle":
        write_monocle_accounts_file(accts)
    else:
        write_rocketmap_accounts_file(accts)

    now = datetime.datetime.now()
    for acct in accts:
        if args.allocation_duration:
            await update_allocation_end(acct.username, now + datetime.timedelta(hours=int(args.allocation_duration)))
        await db_set_system_id(acct.username, args.system_id)
        await db_set_allocated_time(acct.username, now)


#asyncio.ensure_future(start())
loop.run_until_complete(start())

import datetime
import logging
from threading import Lock

from async_accountdbsql import db_set_warned, db_set_temp_banned, db_set_blinded, db_set_perm_banned, db_set_logged_in_stats
from getmapobjects import NoPokemonFoundPossibleSpeedViolation, match_pokemon_in_result, can_not_be_seen
from inventory import egg_count, lure_count
from pogom.account import TooManyLoginAttempts
from pogom.apiRequests import AccountBannedException
from pogoservice import WarnedAccount
from workers import wrap_accounts_minimal

lock = Lock()
log = logging.getLogger(__name__)

cannot_be_seen_when_shadowbanned = can_not_be_seen()


def proceed(worker):
    info = worker.account_info()
    warning_ = info["warning"]
    level = info["level"]
    eggs = egg_count(worker)
    lures = lure_count(worker)
    db_set_logged_in_stats(info.username, lures, eggs, level)
    log.info(u"{} level {}, {} lures {} eggs".format(worker.name(), level, lures, eggs))
    if warning_:
        db_set_warned(info, datetime.datetime.now())
    return False


def write_to_file(filename, username, password):
    with lock:
        with open(filename, "a") as my_file:
            my_file.write("ptc,{},{}\n".format(username, password))


async def try_a_couple_of_times(worker, location_to_use):
    try:
        return await worker.do_get_map_objects(location_to_use)
    except (TooManyLoginAttempts, NoPokemonFoundPossibleSpeedViolation):
        pass


async def check_worker_for_future(account, account_manager, location_to_use, args):
    wrapped = wrap_accounts_minimal(account, account_manager)
    proceed_hdl = proceed if args.login else lambda: True
    res = check_worker(wrapped, location_to_use, None, True, False, proceed_hdl, args)
    return res, account


async def check_worker(worker, location_to_use, accounts_file, use_account_db, login_only, proceed_, args):
    banned = False

    try:
        await worker.login(location_to_use, proceed_)
        if not int(args.min_level) <= worker.account_info()["level"] <= int(args.max_level):
            log.warning("Account {} was not of appropriate level {}".format(str(worker.name()), str(worker.account_info()["level"])))
            return False

        await db_set_warned(worker.account_info(), None)
    except AccountBannedException:
        await db_set_temp_banned(worker.name(), datetime.datetime.now())
        return False
    except TooManyLoginAttempts:
        await db_set_perm_banned(worker.account_info(), datetime.datetime.now())
        return False
    except WarnedAccount:
        if not worker.account_info()["warning"]:
            await db_set_warned(worker.account_info(), datetime.datetime.now())
        return False
    except Exception:
        log.exception("Unknown exception with account {}".format(worker.name()))
        return False

    if login_only:
        return

    response = None
    try:
        response = try_a_couple_of_times(worker, location_to_use)
    except AccountBannedException:
        banned = True

    if banned or not response:
        log.info("{} is banned".format(worker.name()))
        if use_account_db:
            if not worker.account_info().banned:
                db_set_temp_banned(worker.name(), datetime.datetime.now())
        else:
            write_to_file(accounts_file + "_banned.csv", worker.account_info().username, worker.account_info().password)
    else:
        count = match_pokemon_in_result(response, cannot_be_seen_when_shadowbanned)
        if count > 0:
            log.info("{} is clean".format(worker.name()))
            if use_account_db:
                db_set_temp_banned(worker.name(), None)
                db_set_blinded(worker.name(), None)
            else:
                write_to_file(accounts_file + "_clean.csv", worker.account_info().username,
                              worker.account_info().password)
            return True
        else:
            log.info("{} may be blinded".format(worker.account_info().username))
            if use_account_db:
                db_set_blinded(worker.name(), datetime.datetime.now())
                db_set_temp_banned(worker.name(), None)
            else:
                write_to_file(accounts_file + "_blinded.csv", worker.account_info().username,
                              worker.account_info().password)
    return False

import logging
import aiomysql
from aiomysql import DictCursor


from accountdbsql_statements import load_reallocatable_sql, sql_find_allocatable, sql_find_allocatable_by_level, \
    sql_consume_lures, sql_set_blinded, sql_set_rest_until, sql_set_account_level, sql_set_egg_count, \
    sql_set_lure_count, \
    sql_set_logged_in_stats, sql_set_temp_banned, sql_set_behaviour, sql_load_accounts, sql_load_reallocated_accounts, \
    sql_set_allocated_time, sql_update_account, sql_set_warned, sql_set_perm_banned, sql_roll_allocated_date_forward, \
    sql_account_exists, sql_load_account, sql_set_ios, sql_set_model, sql_set_device_id, sql_set_system_id, \
    sql_account_level, sql_allocated, sql_delete_pokestop, sql_allocation_end, sql_insert_account, \
    upsert_account_select, \
    upsert_account_insert, sql_load_accounts_for_lures, sql_load_accounts_for_blindcheck
from scannerutil import as_str

log = logging.getLogger(__name__)

args = None
loop = None


def set_account_db_args(new_args, loop_):
    global args,loop
    args = new_args
    loop = loop_


async def __account_db_connection():
    return await aiomysql.connect(user=args.db_user, password=args.db_pass, db=args.db_name,
                                  host=args.db_host,
                                  port=args.db_port,
                                  charset='utf8mb4',
                                  cursorclass=DictCursor,
                                  loop=loop)


async def db_load_reallocatable(system_id, ban_time, warn_time, ok_if_blinded_before, now):
    return await do_fetch_all(*load_reallocatable_sql(system_id, ban_time, warn_time, ok_if_blinded_before, now))


async def db_find_allocatable(temp_ban_time, warn_time, blind_time, now):
    return await do_fetch_all(*sql_find_allocatable(temp_ban_time, warn_time, blind_time, now))


async def db_find_allocatable_by_level(temp_ban_time, perm_ban_time, warn_time, blind_time, now, min_level, max_level):
    return await do_fetch_all(
        *sql_find_allocatable_by_level(temp_ban_time, perm_ban_time, warn_time, blind_time, now, min_level, max_level))


async def db_consume_lures(account):
    await do_update(sql_consume_lures, account)


async def db_set_blinded(account, when):
    await do_update(*sql_set_blinded(when, account))


async def db_set_rest_time(account, when):
    await do_update(*sql_set_rest_until(when, account))


async def db_set_account_level(account, level):
    await do_update(*sql_set_account_level(account, level))


async def db_set_egg_count(account, egg_count):
    await do_update(*sql_set_egg_count(account, egg_count))


async def db_set_lure_count(account, lure_count):
    await do_update(*sql_set_lure_count(account, lure_count))


async def db_set_logged_in_stats(account, lure_count, egg_count, level):
    await do_update(*sql_set_logged_in_stats(account, lure_count, egg_count, level))


async def db_set_temp_banned(username, when):
    await do_update(*sql_set_temp_banned(username, when))


async def db_set_behaviour(account, behaviour):
    await do_update(*sql_set_behaviour(account, behaviour))


async def db_load_accounts(system_id):
    return await do_fetch_all(*sql_load_accounts(system_id))


async def db_load_reallocated_accounts(system_id, from_time, to_time):
    return await do_fetch_all(*sql_load_reallocated_accounts(system_id, from_time, to_time))


async def db_set_allocated_time(username, allocated):
    await do_update(*sql_set_allocated_time(username, allocated))


async def db_update_account(account_info):
    await do_update(*sql_update_account(account_info))


async def db_set_warned(account_info, when):
    await do_update(*sql_set_warned(account_info, when))


async def db_set_perm_banned(account_info, when):
    await do_update(*sql_set_perm_banned(account_info, when))


async def db_roll_allocated_date_forward(account_info):
    await do_update(*sql_roll_allocated_date_forward(account_info))


async def load_accounts(system_id, ban_cutoff_date):
    return await do_fetch_all(*sql_load_accounts(system_id, ban_cutoff_date))


async def load_accounts_for_lures(system_id, ban_cutoff_date):
    return await do_fetch_all(*sql_load_accounts_for_lures(system_id, ban_cutoff_date))


async def load_accounts_for_blindcheck(system_id, ban_cutoff_date):
    return await do_fetch_all(*sql_load_accounts_for_blindcheck(system_id, ban_cutoff_date))


async def account_exists(username):
    return len(await do_fetch_all(*sql_account_exists(username))) > 0


async def load_account(username):
    return await do_fetch_one(*sql_load_account(username))


async def db_set_ios(username, ios):
    await do_update(*sql_set_ios(username, ios))


async def db_delete_pokestop(pokestop):
    await do_update(*sql_delete_pokestop(pokestop))


async def db_set_model(username, model):
    await do_update(*sql_set_model(username, model))


async def db_set_device_id(username, deviceid):
    await do_update(*sql_set_device_id(username, deviceid))


async def db_set_system_id(username, system_id):
    await do_update(*sql_set_system_id(username, system_id))


async def update_account_level(username, level):
    await do_update(*sql_account_level(username, level))


async def update_allocated(username, allocated):
    await do_update(*sql_allocated(username, allocated))


async def update_allocation_end(username, allocation_end):
    await do_update(*sql_allocation_end(username, allocation_end))


async def insert_account(account, system_id, allocated, allocation_end):
    await do_update(*sql_insert_account(account, system_id, allocated, allocation_end))
    if "level" in account:
        await update_account_level(account["username"], account["level"])


async def upsert_account(username, password, provider, system_id):
    async with __account_db_connection() as connection:
        async with connection.cursor() as cursor:
            cursor.execute(*upsert_account_select(username))
            fetchone = cursor.fetchone()
            if fetchone is None:
                cursor.execute(*upsert_account_insert(username, password, provider, system_id))
            elif fetchone['system_id'] and fetchone['system_id'] != system_id:
                msg = "Account {} exits in database with other system_id ({}), " \
                      "cannot be created for this system_id".format(username, as_str(fetchone["system_id"]))
                raise ValueError(msg)
        connection.commit()


async def do_update(sql, params):
    async with await __account_db_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(sql, params)
            await connection.commit()

async def do_fetch_one(sql, args):
    async with await __account_db_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(sql, args)
            return await cursor.fetchone()

async def do_fetch_all(sql, args):
    connection = await __account_db_connection()
    async with connection.cursor() as cursor:
        await cursor.execute(sql, args)
        return await cursor.fetchall()

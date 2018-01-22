import asyncio
from queue import Queue

from datetime import datetime, timedelta

import logging

from async_accountdbsql import upsert_account, db_consume_lures, db_set_rest_time, db_set_temp_banned, \
    db_set_account_level, db_set_blinded, db_update_account, db_set_warned, insert_account, \
    load_account, db_set_ios, db_set_model, db_set_device_id, \
    update_account_level, db_set_system_id, update_allocated, update_allocation_end, db_set_perm_banned, load_accounts

from common_accountmanager import CommonAccountManager
from pogoservice import Account3
from scannerutil import auth_service
from simplecaptcha import handle_captcha_url

log = logging.getLogger(__name__)


class AsyncAccountManager(CommonAccountManager):
    def __init__(self, name, using_db, args, account_failures, account_captchas, wh_queue, status, loop):
        super().__init__(name, using_db, args)
        self.usingdb = using_db
        self.captcha_key = args.captcha_key
        self.captcha_dsk = args.captcha_dsk
        self.wh_queue = wh_queue
        self.account_failures = account_failures
        self.status = status
        self.account_captchas = account_captchas
        self.accounts = []
        self.replace_warned = False
        self.loader = load_accounts
        self.loop = loop

    @staticmethod
    def create_empty(args, loop):
        return AsyncAccountManager(args.system_id, args.use_account_db, args, [], [], Queue(), {}, loop)

    @staticmethod
    async def create_standard(args, loop, loader=None):
        account_manager = AsyncAccountManager.create_empty(args, loop)
        if loader:
            account_manager.loader = loader
        await account_manager.initialize(args.accountcsv, ())
        return account_manager

    async def initialize(self, accounts_file, settings_accounts):
        file_accts = self.load_accounts(accounts_file)

        if self.usingdb:
            if file_accts:
                log.info("Upserting database accounts")
                allocation_period = timedelta(days=180)
                await self.insert_accounts(self.loop, file_accts, self.name, allocation_period)
            self.__upsert_commandline_accounts(settings_accounts)
            log.info("Loading database accounts")
            self.accounts = await self.__load_db_account_objects()
        else:
            self.accounts = self.create_account_objects(file_accts)
        self.sort_accounts()
        for acct in self.accounts:
            self.status[acct.username] = acct.status_data()
        if len(self.accounts) > 0:
            log.info("Account pool " + str(self.name) + " active with " + str(len(self.accounts)) + " accounts")

    def add_account(self, account):
        acct = self.create_async_account(account)
        self.accounts.append(acct)
        self.status[acct.username] = acct.status_data()
        return acct

    def create_async_account(self, account):
        username = account["username"]
        password = account["password"]
        auth = auth_service(account)

        created = Account3(username, password, auth, self.args, self.search_interval, self.rest_interval,
                           self.apiHashGenerator, self.apiLoginHashGenerator, self.ptc_proxy_supplier_to_use(),
                           self.niantic_proxy_supplier_to_use(), account,
                           self, self.loop)
        return created


    async def acc_update_account(self, account):
        await db_update_account(account)

    async def acc_set_blinded(self, account_info):
        await db_set_blinded(account_info.username, account_info.blinded)

    async def acc_set_warned(self, account_info):
        await db_set_warned(account_info.username, datetime.now())

    async def acc_set_rest_time(self, account_info, when):
        await db_set_rest_time(account_info.username, when)

    async def acc_set_tempbanned(self, account_info):
        await db_set_temp_banned(account_info.username, datetime.now())

    async def acc_set_permbanned(self, account_info):
        await db_set_perm_banned(account_info, datetime.now())

    async def acc_set_account_level(self, account_info):
        level = account_info["level"]
        if level:
            await db_set_account_level(account_info.username, level)

    async def __load_db_account_objects(self):
        all_accounts = await load_accounts(self.name, self.ban_cutoff_date)
        return [self.create_account2(account) for account in all_accounts]

    async def handle_warned(self, pogoservice):
        if self.usingdb:
            self.acc_set_warned(pogoservice.account_info())
        return await self.replace(pogoservice) if self.replace_warned else pogoservice

    async def update_initial_inventory(self, account_info):
        level = account_info["level"]
        if level and self.usingdb:
            await self.acc_set_account_level(account_info)

    def __upsert_commandline_accounts(self, account_list):
        inserted = False
        if len(account_list) == 0:
            return inserted
        for acct in account_list:
            if not any(acct["username"] in s.username for s in self.accounts):
                upsert_account(acct["username"], acct["password"], acct["auth_service"], self.name)
                inserted = True
        return inserted

    async def solve_captcha(self, account, captcha_url):
        await handle_captcha_url(self.args, self.status[account.status_name()],
                           account.pgoApi,
                           account.as_map(),
                           self.account_failures, self.account_captchas,
                           self.wh_queue, captcha_url,
                           account.most_recent_position())
        await asyncio.sleep(4)  # avoid throttling
        return account

    async def mark_lures_consumed(self, username):
        # account.consumed = True
        if self.usingdb:
            asyncio.ensure_future(db_consume_lures(username), loop=self.loop)
        return await self.get_account()

    async def insert_accounts(self, loop, accounts, system_id, allocation_duration=None, force_system_id=False, skip_assigned=False,
                        overwrite_level=False):
        now = datetime.now()
        allocated = now if allocation_duration else None
        allocation_end = now + allocation_duration if allocation_duration else None
        log.info("Allocation end is {}".format(str(allocation_end)))
        for account in accounts:
            username_ = account["username"]
            existing = await load_account(username_)
            if existing:
                if skip_assigned:
                    log.info("Account {} is assigned to {}, skipping".format(username_, existing["system_id"]))
                    continue
                if existing["system_id"] and system_id and not force_system_id:
                    if not system_id == existing["system_id"]:
                        raise ValueError("Account {} exists but is assigned to {}, cannot be loaded for {}".format(
                            username_, existing["system_id"], system_id))
                if system_id:
                    await db_set_system_id(username_, system_id)
                if account.get("iOS") and not existing.get("iOS"):
                    await db_set_ios(username_, account["iOS"])
                if account.get("model") and not existing.get("model"):
                    await db_set_model(username_, account["model"])
                if account.get("id") and not existing.get("device_id"):
                    await db_set_device_id(username_, account["id"])
                if account.get("level") and (overwrite_level or not existing.get("level")):  # never update
                    await update_account_level(username_, account["level"])
                if not existing["system_id"] or not existing["allocated"]:
                    await update_allocated(username_, allocated)
                if not existing["system_id"] or not existing["allocation_end"]:
                    await update_allocation_end(username_, allocation_end)

            else:
                await insert_account(account, system_id, allocated, allocation_end)



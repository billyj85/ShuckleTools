import asyncio
import logging
import os.path
import sys
from csv import DictReader
from datetime import datetime, timedelta
from itertools import cycle
from future.backports import cmp_to_key

from management_errors import GaveUp
from pogoservice import Account2
from scannerutil import auth_service

log = logging.getLogger(__name__)
logging.LoggerAdapter(logging.getLogger("d.e.f"), {'worker_name': ''})


class CommonAccountManager(object):
    def __init__(self, name, using_db, args):
        self.name = name
        self.accounts = []
        self.args = args
        self.apiHashGenerator = cycle(args.hash_key)
        self.apiLoginHashGenerator = cycle(args.login_hash_key) if args.login_hash_key else None
        if "proxy" in self.args and (self.args.proxy is not None or self.args.niantic_banned_proxy is not None):
            self.current_ptc_proxies = self.args.proxy + self.args.niantic_banned_proxy
            log.info("PTC proxies are {}".format(str(self.current_ptc_proxies)))
            self.current_ptc_cycler = cycle(self.current_ptc_proxies)
        else:
            self.current_ptc_proxies = None
        if "proxy" in self.args and (self.args.proxy is not None or self.args.ptc_banned_proxy is not None):
            self.current_niantic_proxies = self.args.proxy + self.args.ptc_banned_proxy
            log.info("NIANTIC proxies are {}".format(str(self.current_niantic_proxies)))
            self.current_niantic_cycler = cycle(self.current_niantic_proxies)
        else:
            self.current_niantic_proxies = None
        self.search_interval = 7200
        self.rest_interval = 1800
        self.consecutive_failures = 0
        self.failureLock = asyncio.Lock()
        self.lock = asyncio.Lock()
        self.ban_cutoff_date = datetime.now() - timedelta(days=45)
        self.reallocate = True
        self.usingdb = using_db

    def create_account2(self, account):
        username = account["username"]
        password = account["password"]
        auth = auth_service(account)

        created = Account2(username, password, auth, self.args, self.search_interval, self.rest_interval,
                           self.apiHashGenerator, self.apiLoginHashGenerator, self.ptc_proxy_supplier_to_use(),
                           self.niantic_proxy_supplier_to_use(), account,
                           self)
        return created

    def __create_account_objects(self, accts):
        return [self.__create_account_object(account) for account in accts]

    def __create_account_object(self, account):
        return Account2(account["username"], account["password"], auth_service(account), self.args,
                        self.search_interval, self.rest_interval,
                        self.apiHashGenerator, self.apiLoginHashGenerator, self.ptc_proxy_supplier_to_use(),
                        self.niantic_proxy_supplier_to_use(), {},
                        self)

    def ptc_proxy_supplier_to_use(self):
        if self.current_ptc_proxies is None:
            return None
        else:
            return self.ptc_proxy_supplier

    def ptc_proxy_supplier(self, current_proxy):
        if self.current_ptc_proxies is None:
            return None
        if current_proxy not in self.current_ptc_proxies:
            current_proxy = next(self.ptc_proxy_cycler())
        return current_proxy

    def niantic_proxy_supplier_to_use(self):
        if self.current_niantic_proxies is None:
            return None
        else:
            return self.niantic_proxy_supplier

    def niantic_proxy_supplier(self, current_proxy):
        if self.current_niantic_proxies is None:
            return None
        if current_proxy not in self.current_niantic_proxies:
            current_proxy = next(self.niantic_proxy_cycler())
        return current_proxy

    def ptc_proxy_cycler(self):
        # if len(self.args.proxy) != self.current_ptc_proxies:
        #    self.current_ptc_cycler = cycle(self.args.proxy)
        return self.current_ptc_cycler

    def niantic_proxy_cycler(self):
        # if len(self.args.proxy) != self.current_ptc_proxies:
        #    self.current_ptc_cycler = cycle(self.args.proxy)
        return self.current_niantic_cycler

    @staticmethod
    def compare_account_dates(x, y):
        if x.allocated is None and y.allocated is None:
            return 0
        if x.allocated is None:
            return -1
        if y.allocated is None:
            return 1
        if x.allocated < y.allocated:
            return -1
        elif x.allocated == y.allocated:
            return 0
        else:
            return 1

    def sort_accounts(self):
        self.accounts.sort(key=cmp_to_key(CommonAccountManager.compare_account_dates))

    def remove_accounts_without_lures(self):
        initial_length = len(self.accounts)
        self.accounts = [x for x in self.accounts if x.account_info().lures != 0]
        remaining = len(self.accounts)
        log.info(
            "Initial account pool size {}, {} accounts have all lures spent, "
            "{} accounts (probably) have lures left".format(
                initial_length, (initial_length - remaining), remaining))

    async def report_failure(self):
        async with self.failureLock:
            self.consecutive_failures += 1

    async def clear_failure(self):
        async with self.failureLock:
            self.consecutive_failures = 0

    async def is_failing(self):
        async with self.failureLock:
            return self.consecutive_failures > 20

    def has_free(self):
        return any(s.is_available() for s in self.accounts)

    def free_count(self):
        return len([s for s in self.accounts if s.is_available()])

    def size(self):
        return len(self.accounts)

    async def acc_update_account(self, account):
        raise NotImplementedError("This is an abstract method.")

    async def acc_set_blinded(self, account_info):
        raise NotImplementedError("This is an abstract method.")

    async def acc_set_warned(self, account_info):
        raise NotImplementedError("This is an abstract method.")

    async def acc_set_rest_time(self, account_info, when):
        raise NotImplementedError("This is an abstract method.")

    async def acc_set_tempbanned(self, account_info):
        raise NotImplementedError("This is an abstract method.")

    async def acc_set_permbanned(self, account_info):
        raise NotImplementedError("This is an abstract method.")

    async def acc_load_account(self, username_):
        raise NotImplementedError("This is an abstract method.")

    async def free_account(self, account):
        account.free()
        async with self.lock:
            self.sort_accounts()

    async def replace(self, old_pogoservice_to_be_replaced):
        newaccount = await self.get_account()
        newaccount.update_position(old_pogoservice_to_be_replaced.get_position())
        return newaccount

    async def __get_replacement(self):
        if not self.has_free():
            return None
        new_account = await self.get_account()
        if new_account is None:
            raise GaveUp
        return new_account

    async def blinded(self, account_info):
        log.error("Account is blinded " + account_info.name())
        account_info.blinded = datetime.now()
        await self.acc_set_blinded(account_info)
        return await self.__get_replacement()

    async def replace_temp_banned(self, account_info):
        await self.mark_temp_banned(account_info)
        return await self.__get_replacement()

    async def mark_warned(self, account_info):
        log.error("Account is warned " + account_info.name())
        if self.usingdb:
            await self.acc_set_warned(account_info)

    async def mark_temp_banned(self, account_info):
        # self.account_failures.append(account.as_map())
        log.error("Account is temp " + account_info.name())
        account_info.set_banned()
        if self.usingdb:
            await self.acc_set_tempbanned(account_info)

    async def mark_perm_banned(self, account_info):
        # self.account_failures.append(account.as_map())
        log.error("Account is temp " + account_info.name())
        account_info.set_banned()
        if self.usingdb:
            await self.acc_set_permbanned(account_info)

    async def too_much_trouble(self, account_info):
        log.error(
            "Account is having too much trouble {} sending to cool off".format(
                account_info.name()))
        when = datetime.now() + timedelta(0, 0, 0, 0, 120, 0, 0)
        account_info.rest_until(when)
        if self.usingdb:
            self.acc_set_rest_time(account_info.username, when)
        new_account = await self.__get_replacement()
        log.info("{} replaced with {}".format(str(account_info), str(new_account)))
        return new_account

    async def replace_for_sleep(self, pogoservice):
        current_account_info = pogoservice.account_info()
        current_account_info.set_resting()
        new_pogoservice = await self.get_account()
        recent_position = current_account_info.most_recent_position()
        new_pogoservice.update_position(recent_position)
        await self.free_account(current_account_info)
        if self.usingdb:
            await self.acc_set_rest_time(pogoservice, current_account_info.rest_until)
        log.info("{} replaced with {}".format(current_account_info.username, new_pogoservice.name()))
        return new_pogoservice

    async def get_account(self):
        if not self.has_free():
            log.error("No more free accounts. In some use-cases restarting process may help")
            raise OutOfAccounts

        async with self.lock:
            for account in self.accounts:
                if self.reallocate and account.try_reallocate():
                    log.info("Reallocated {}".format(account))
                    await self.acc_update_account(account)
                    return account

            for account in self.accounts:
                if account.tryallocate():
                    if self.usingdb:
                        await self.acc_update_account(account)
                    num_free = self.free_count()
                    if num_free % 10 == 0:
                        log.info("There are {} accounts remaining in pool".format(str(num_free)))
                    return account
        raise OutOfAccounts

    @staticmethod
    def load_accounts(accounts_file):

        if accounts_file is None:
            return None

        if not os.path.isfile(accounts_file):
            raise ValueError("The supplied filename " + accounts_file + " does not exist")

        # Giving num_fields something it would usually not get.
        with open(accounts_file, 'r') as f1:
            first_line = f1.readline()
        if "username" in first_line and "password" in first_line:
            return load_accounts_csv_monocle(accounts_file)

        if not first_line.startswith("ptc") and not first_line.startswith("google"):
            return load_accounts_selly_ptc(accounts_file)

        with open(accounts_file, 'r') as f:
            return CommonAccountManager.__load_accounts_rocketmap(f)

    @staticmethod
    def __load_accounts_rocketmap(f):
        result = []
        num_fields = -1
        for num, line in enumerate(f, 1):
            account = {}
            result.append(account)
            fields = []

            # First time around populate num_fields with current field
            # count.
            if num_fields < 0:
                num_fields = line.count(',') + 1

            csv_input = ['', '<username>', '<username>,<password>',
                         '<ptc/google>,<username>,<password>']

            # If the number of fields is differend this is not a CSV.
            if num_fields != line.count(',') + 1:
                print((sys.argv[0] +
                       ": Error parsing CSV file on line " + str(num) +
                       ". Your file started with the following " +
                       "input, '" + csv_input[num_fields] +
                       "' but now you gave us '" +
                       csv_input[line.count(',') + 1] + "'."))
                sys.exit(1)

            field_error = ''
            line = line.strip()

            # Ignore blank lines and comment lines.
            if len(line) == 0 or line.startswith('#'):
                continue

            # If number of fields is more than 1 split the line into
            # fields and strip them.
            if num_fields > 1:
                fields = line.split(",")
                fields = list(map(str.strip, fields))

            # If the number of fields is one then assume this is
            # "username". As requested.
            if num_fields == 1:
                # Empty lines are already ignored.
                account["username"] = line

            # If the number of fields is two then assume this is
            # "username,password". As requested.
            if num_fields == 2:
                # If field length is not longer than 0 something is
                # wrong!
                if len(fields[0]) > 0:
                    account["username"] = fields[0]
                else:
                    field_error = 'username'

                # If field length is not longer than 0 something is
                # wrong!
                if len(fields[1]) > 0:
                    account["password"] = fields[1]
                else:
                    field_error = 'password'

            # If the number of fields is three then assume this is
            # "ptc,username,password". As requested.
            if num_fields == 3:
                # If field 0 is not ptc or google something is wrong!
                if fields[0].lower() == 'ptc' or fields[0].lower() == 'google':
                    account["auth_service"] = fields[0]
                else:
                    field_error = 'method'

                # If field length is not longer then 0 something is
                # wrong!
                if len(fields[1]) > 0:
                    account["username"] = fields[1]
                else:
                    field_error = 'username'

                # If field length is not longer then 0 something is
                # wrong!
                if len(fields[2]) > 0:
                    account["password"] = fields[2]
                else:
                    field_error = 'password'

            if num_fields > 3:
                print((('Too many fields in accounts file: max ' +
                        'supported are 3 fields. ' +
                        'Found {} fields').format(num_fields)))
                sys.exit(1)

            # If something is wrong display error.
            if field_error != '':
                type_error = 'empty!'
                if field_error == 'method':
                    type_error = (
                        'not ptc or google instead we got \'' +
                        fields[0] + '\'!')
                print((sys.argv[0] +
                       ": Error parsing CSV file on line " + str(num) +
                       ". We found " + str(num_fields) + " fields, " +
                       "so your input should have looked like '" +
                       csv_input[num_fields] + "'\nBut you gave us '" +
                       line + "', your " + field_error +
                       " was " + type_error))
                sys.exit(1)
        return result


def load_accounts_csv_monocle(csv_location):
    with open(csv_location, 'rt') as f:
        accounts = []
        reader = DictReader(f)
        for row in reader:
            accounts.append(dict(row))
    return accounts


def load_accounts_selly_ptc(csv_location):
    with open(csv_location, 'rt') as f:
        accounts = []
        for line in f.readlines():
            if len(line.strip()) == 0:
                continue
            withcomma = line.replace(":", ",")
            if withcomma.startswith(","):
                withcomma = withcomma[1:]
            usrnamepassword = withcomma.split(",")
            accounts.append({"username": usrnamepassword[0].strip(), "password": usrnamepassword[1].strip(),
                             "auth_service": "ptc"})
    return accounts


class OutOfAccounts(BaseException):
    """We tried and we tried, but it's simply not going to work out between us...."""

    def __init__(self):
        pass

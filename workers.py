import logging

from pogoservice import BanChecker, WorkingTimeScheduler, AccountReplacer, BlindChecker, TravelTime, CaptchaChecker, ApiDelay, ApplicationBehaviour

log = logging.getLogger(__name__)

'''
A worker that delegates to an underlying account. The underlying account is
dynamic and may be replaced based on captchas, sleep intervals errors or
similar. Given enough underlying accounts, a worker will normally not fail.

Provide scan method that obey api and KPH speed restrictions, suspending thread
if needed. Client code does not need to know about KPH or 10 second sleep
limits.

Based on distance between previous location, new location and KPH, will
determine earliest legal time scan can be performed and use this.

Transparently handles captchas so clients dont have to see them

'''


class QueueEntry:
    def __init__(self, location, encounter_id):
        self.location = location
        self.encounter_id = encounter_id



def wrap_account(account, account_manager):
    replacer = AccountReplacer(account, account_manager)
    api_delayed = ApiDelay(replacer)
    ban_checker = BanChecker(api_delayed, account_manager, replacer)
    captcha_checker = CaptchaChecker(ban_checker, account_manager)
    blind_checker = BlindChecker(captcha_checker, account_manager, replacer)
    scheduler = WorkingTimeScheduler(blind_checker, account_manager.args.account_search_interval, replacer)
    travel_time = TravelTime(scheduler)
    return travel_time


def wrap_account_no_replace(account, account_manager, fast_speed=25):
    api_delayed = ApiDelay(account)
    ban_checker = BanChecker(api_delayed, account_manager, None)
    captcha_checker = CaptchaChecker(ban_checker, account_manager)
    travel_time = TravelTime(captcha_checker, fast_speed)
    ab = ApplicationBehaviour(travel_time)
    return ab


def wrap_accounts_minimal(account, account_manager):
    api_delayed = ApiDelay(account)
    captcha_checker = CaptchaChecker(api_delayed, account_manager)
    travel_time = TravelTime(captcha_checker)
    ab = ApplicationBehaviour(travel_time)
    return ab

class DummyAccount(object):
    def most_recent_position(self):
        return (2.0, 3.0, 4)


class DummyAccount2(object):
    def most_recent_position(self):
        return ()


class DummyArgs:
    account_search_interval = 299

class DummyAccountManager:
    def __init__(self, account):
        self.account = account
        self.args = DummyArgs()

    async def get_account(self):
        return self.account

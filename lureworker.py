import asyncio
import datetime
import logging
import os
from threading import Lock

from async_accountdbsql import db_consume_lures, db_set_warned, db_set_perm_banned
from getmapobjects import pokstops_within_distance, pokestop_detail
from inventory import egg_count, lure_count
from luredbsql import lures, db_consume_lure
from pogom.account import LoginSequenceFail
from pogoservice import CaptchaRequired
from scannerutil import as_str
from workers import wrap_account_no_replace

log = logging.getLogger(__name__)


class FileLureCounter(object):
    def __init__(self, json_location):
        self.max_lures = int(json_location.get("max_lures", 698919191))
        self.current_count_file = json_location['name'] + '_lure_count.txt'
        self.lure_count = self.load_lure_count()
        self.lock = Lock()

    def load_lure_count(self):
        if os.path.isfile(self.current_count_file):
            with open(self.current_count_file, 'r') as f:
                for line in f:
                    self.lure_count = int(line)
                    return self.lure_count
        return 0

    def write_lure_count(self):
        with open(self.current_count_file, 'w') as f:
            f.write(str(self.lure_count))

    def use_lure(self):
        with self.lock:
            self.lure_count += 1
            self.write_lure_count()

    def has_more_lures(self):
        return self.lure_count < self.max_lures if self.max_lures else True


class DbLureCounter(object):
    def __init__(self, username):
        self.username = username
        lures1 = lures(username)

        self.max_lures = lures1[0].get("max_lures", None)
        self.lure_count = lures1[0].get("lures", 0)
        self.lock = Lock()

    def use_lure(self):
        with self.lock:
            db_consume_lure(self.username)
            self.lure_count += 1

    def has_more_lures(self):
        return self.lure_count < self.max_lures if self.max_lures else True

class LureWorker(object):
    """A lure dropper that drops lures on one or more locations with a single account (worker).
       Use with multiple positions to quickly empty account for lures
    """

    def __init__(self, account_manager, brander, deploy_more_lures, lure_counter, lure_duration):
        self.account_manager = account_manager
        self.brander = brander
        self.collected = {}
        self.deploy_more_lures = deploy_more_lures
        self.worker = None
        self.inventory = None
        self.stop_names = {}
        self.lured_msg = {}
        self.running = True
        self.lure_counter = lure_counter
        self.next_lure_at = {}
        self.location_pokestop = {}
        self.lure_duration_minutes = int(lure_duration)

    def replace_worker(self, new_worker):
        self.worker = new_worker
        self.inventory = None

    async def safe_get_map_objects(self, pos):
        try:
            objects = await self.worker.do_get_map_objects(pos)
            if not self.inventory:
                self.inventory = self.worker.account_info()["items"]
            return objects
        except CaptchaRequired:
            self.replace_worker(await self.account_manager.get_account_with_lures())
            return await self.safe_get_map_objects(pos)

    async def worker_with_map_objects(self, pos):
        await self.get_worker_with_nonzero_lures(pos)

        map_objects = await self.safe_get_map_objects(pos)
        await asyncio.sleep(2)
        if self.worker.name() not in self.collected:
            level = self.worker.account_info()["level"]
            await self.worker.do_collect_level_up(level)
            self.collected[self.worker.name()] = self.worker
            await asyncio.sleep(10)
            map_objects = await self.safe_get_map_objects(pos)

        while self.inventory.get(501, 0) == 0:
            log.info(u"no lures in inventory for worker {}, replacing".format(self.worker.name()))
            await db_consume_lures(self.worker.name())
            self.worker = None
            await self.get_worker_with_nonzero_lures(pos)
            map_objects = await self.safe_get_map_objects(pos)
        return map_objects

    async def proceed(self, worker):
        info = worker.account_info()
        warning_ = info["warning"]
        level = info["level"]
        eggs = egg_count(worker)
        lures = lure_count(worker)
        await db_set_logged_in_stats(info.username, lures, eggs, level)
        if warning_:
            db_set_warned(info,datetime.datetime.now())
        return True

    async def get_account_with_lures(self, pos):
        worker = wrap_account_no_replace(await self.account_manager.get_account(), self.account_manager)
        worker.account_info().update_position(pos)
        retries = 0
        success = False
        while not success:
            try:
                login_result = await worker.login(pos, self.proceed)
                if login_result:
                    success = True
                else:
                    log.info(u"Login not succesful {}".format(str(login_result)))
                    worker = wrap_account_no_replace(await self.account_manager.get_account(), self.account_manager)
                    worker.account_info().update_position(pos)
                    await asyncio.sleep(10)
                    retries += 1
            except Exception as ex:
                log.info(u"Login had exception {}".format(str(type(ex).__name__)))
                worker = wrap_account_no_replace(await self.account_manager.get_account(), self.account_manager)
                worker.account_info().update_position(pos)
                await asyncio.sleep(10)
                retries += 1

        await worker.do_get_map_objects(pos)
        try:
            branded = await self.brander(worker)
        except LoginSequenceFail as e:
            log.warning("LSEIn branding")
            await self.account_manager.report_failure()
            return None
        await self.account_manager.clear_failure()
        return branded

    async def get_worker_with_nonzero_lures(self, pos):
        while self.worker is None or self.worker.account_info().lures == 0:
            if self.worker:
                log.info(u"Skipping {}, lures are spent".format(self.worker.name()))
            else:
                log.info(u"No worker, getting new")
            self.replace_worker(await self.get_account_with_lures(pos))

    def replace_account(self, pos, worker):
        retryer = wrap_account_no_replace(self.account_manager.mark_lures_consumed(worker.name()), self.account_manager)
        retryer.account_info().update_position(pos)
        return retryer

    def sort_by_time(self, route):
        ordered = []
        for parsed_loc in route:
            if parsed_loc in self.next_lure_at:
                ordered.append((self.next_lure_at[parsed_loc], parsed_loc))
            else:
                ordered.append((datetime.datetime.now() + datetime.timedelta(minutes=3), parsed_loc))

        by_time = sorted(ordered, key=lambda tup: tup[0])
        log.debug("Route metrics {}".format(str(by_time)))
        return [x[1] for x in by_time]

    def all_route_elements_are_lured(self, route_to_use):
        for route_item in route_to_use:
            exp= self.next_lure_at.get(route_item, None)
            if exp is None or exp > datetime.datetime.now():
                return False
        return True

    async def lure_json_worker_positions(self, route):
        first_time = True
        self.should_run(False)

        has_more_lures = self.lure_counter.has_more_lures()
        if not has_more_lures:
            log.warning(("No more lures in counter"))
        while self.running and has_more_lures:
            route_to_use = route if first_time else self.sort_by_time(route)

            initial_pos = route_to_use[0]
            pokestop = await self.pokestop_at_coordinate(initial_pos)
            if not pokestop:
                await self.get_worker_with_nonzero_lures(initial_pos)
            else:
                if self.is_lured_by_us(initial_pos) and self.all_route_elements_are_lured(route_to_use):
                    await self.wait_for_lure_to_expire(pokestop, initial_pos)
                else:
                    await self.sleep_for_one_expiration_period(pokestop)

            for pos in route_to_use:
                if not self.should_run(lure_dropped=False):
                    return
                await self.lure_one_position_once(pos, first_time)

            first_time = False

    async def lure_bomb(self, pos, radius=40):
        map_objects = await self.worker_with_map_objects(pos=pos)
        pokestops = await self.pokestops_at_coordinate(pos, map_objects, radius)
        if len(pokestops) == 0:
            log.warning("Could not find pokestops at {}, aborting".format(str(pos)))
            db_set_perm_banned(self.worker.account_info(), datetime.datetime.now())
            return

        as_route = [ (x.latitude, x.longitude) for x in pokestops]
        await self.lure_json_worker_positions(as_route)

    def should_run(self, lure_dropped):
        if not self.deploy_more_lures(lure_dropped):
            self.running = False
            return False
        return True

    async def lure_one_position_once(self, pos, first_time):
        pokestop = await self.pokestop_at_coordinate(pos)

        if not pokestop:
            if self.worker:
                log.info(u"Worker {} not seeing any pokestops at {}, skipping".format(self.worker.name(), str(pos)))
            self.worker = None
            await self.get_worker_with_nonzero_lures(pos)
            return

        if first_time:
            await self.log_first_time_pokestop_info(pokestop)

        if 501 not in pokestop.active_fort_modifier:
            counter = 0
            placed_lure = await self.lure_single_stop(pokestop, pos)
            while self.running and not placed_lure and counter < 5:
                await asyncio.sleep(30)
                placed_lure = await self.lure_single_stop(pokestop, pos)
                counter += 1

    async def pokestop_at_coordinate(self, initial_pos):
        map_objects = await self.worker_with_map_objects(pos=initial_pos)
        pokestops = await self.pokestops_at_coordinate(initial_pos, map_objects, m=40)
        return pokestops[0] if len(pokestops) > 0 else None

    async def pokestops_at_coordinate(self, initial_pos, map_objects, m=40, retry=True):
        pokestops = pokstops_within_distance(map_objects, initial_pos, m)
        if len(pokestops) == 0:
            log.info(u"Not seeing any pokestops at {}, retrying in 10 seconds".format(initial_pos))
            map_objects = await self.worker_with_map_objects(pos=initial_pos)
            pokestops = pokstops_within_distance(map_objects, initial_pos, m)
            if len(pokestops) == 0 and retry:
                log.warning("Still not seeing any pokestops, changing worker")
                self.worker = None
                map_objects = await self.worker_with_map_objects(pos=initial_pos)
                return await self.pokestops_at_coordinate(initial_pos, m, map_objects, retry=False)

        return pokestops

    @staticmethod
    def lowest_date(current, other):
        if other is None:
            return current
        if current is None:
            return other
        return other if other < current else current

    async def lure_single_stop(self, pokestop, pos):
        if not 501 in pokestop.active_fort_modifier:
            while self.inventory.get(501,0) == 0:
                await db_consume_lures(self.worker.name())
                self.worker = None
                await self.worker_with_map_objects(pos=pos)

            lure, pokestop_name = await self.lure_stop(pokestop)
            if lure == 4:
                log.info(u"Replacing worker {} due to code 4, stop {}".format(self.worker.name(), pokestop_name))
                await db_consume_lures(self.worker.name())
                self.worker = None
                await self.worker_with_map_objects(pos=pos)
                if pos in self.next_lure_at:
                    del self.next_lure_at[pos]
            elif lure == 2:  # already luredx
                log.info(u"Pokestop {} is lured(1)".format(str(pokestop)))
                pass
            elif lure == 3:  # already lured
                log.error("Too far away")
                # raise ValueError("Too far away ??")
            else:
                self.inventory[501] -= 1
                log.info(u"Added lure to pokestop {}".format(pokestop_name))
                self.lure_counter.use_lure()
                self.next_lure_at[pos] = datetime.datetime.now() + datetime.timedelta(minutes=self.lure_duration_minutes)

                self.should_run(lure_dropped=True)
                return True
            await asyncio.sleep(10)
        else:
            return False

    def time_of_lure_expiry(self, next_lure_expiry, pokestop):
        expires_at = datetime.datetime.fromtimestamp(self.lure_expiry(pokestop) / 1000)
        thrity_seconds_from_now = (datetime.datetime.now() + datetime.timedelta(seconds=30))
        if expires_at <= thrity_seconds_from_now:
            expires_at = thrity_seconds_from_now
        next_lure_expiry = self.lowest_date(next_lure_expiry, expires_at)
        if self.lured_msg.get(pokestop["id"], None) != expires_at:
            self.lured_msg[pokestop["id"]] = expires_at
            log.info(u"Pokestop {} is lured until {}".format(str(self.stop_names[pokestop["id"]]), str(expires_at)))
        return next_lure_expiry


    def lure_expiry(self, pokestop):
        return pokestop.lure_info.lure_expires_timestamp_ms


    def has_lure(self, pokestop):
        return 501 in pokestop.active_fort_modifier

    def is_lured_by_us(self, pos):
        return pos in self.next_lure_at and datetime.datetime.now() < self.next_lure_at[pos]

    async def wait_for_lure_to_expire(self, first_stop, pos):
        if self.has_lure(first_stop):
            log.info(u"First pokestop in route, waiting for existing lure to expire")
        else:
            return

        while first_stop and self.has_lure(first_stop):
            await self.sleep_for_one_expiration_period(first_stop)
            map_objects = await self.safe_get_map_objects(pos)
            stops = pokstops_within_distance(map_objects, pos, 40)
            first_stop = stops[0] if len(stops) > 0 else None

    async def sleep_for_one_expiration_period(self, first_stop):
        if self.has_lure(first_stop):
            expires_at = datetime.datetime.fromtimestamp(self.lure_expiry(first_stop) / 1000)
            thrity_seconds_from_now = (datetime.datetime.now() + datetime.timedelta(seconds=30))
            exp = max(expires_at, thrity_seconds_from_now)
            seconds = (exp - datetime.datetime.now()).seconds
            log.info(u"Sleeping for {} seconds".format(seconds))
            asyncio.sleep(seconds)

    async def log_first_time_pokestop_info(self, pokestop):
        details = pokestop_detail(await self.worker.do_pokestop_details(pokestop))
        pokestop_name = as_str(details.name)
        self.stop_names[pokestop.id] = pokestop_name
        try:
            log.info(u"Pokestop {} served by {}".format(pokestop_name, self.worker.name()))
        except UnicodeDecodeError:
            log.error("Unicode decode error x")
        await asyncio.sleep(2)

    async def lure_stop(self, pokestop):
        stop_pos = (pokestop.latitude, pokestop.longitude)
        pokestop_details = pokestop_detail(await self.worker.do_pokestop_details(pokestop))
        await asyncio.sleep(3)
        lure = await self.worker.do_add_lure(pokestop, stop_pos)
        pokestop_name = as_str(pokestop_details.name)
        return lure, pokestop_name

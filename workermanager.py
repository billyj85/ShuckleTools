import logging
from datetime import datetime, timedelta

from async_accountdbsql import db_set_egg_count
from behaviours import beh_handle_level_up
from geography import move_towards
from getmapobjects import catchable_pokemon
from inventory import has_lucky_egg, egg_count, has_incense, incense_count
from pogoservice import TravelTime2
from scannerutil import equi_rect_distance_m

log = logging.getLogger(__name__)


class WorkerManager(object):
    def __init__(self, worker, use_eggs, target_level):
        self.worker = worker
        self.travel_time = worker.getlayer(TravelTime2)
        self.use_eggs = use_eggs
        self.next_egg = datetime.now()  # todo fix later
        self.egg_expiration = None
        self.next_incense = datetime.now()
        self.level = None
        self.target_level = target_level
        self.xp_log = {}
        self.next_gmo = datetime.now()
        self.initial_fast_egg = True
        self.egg_number = 0

    def player_level(self):
        level_ = self.worker.account_info()["level"]
        return int(level_) if level_ else 0

    async def move_to_with_gmo(self, next_pos, is_fast_speed=True, seconds_threshold=25, at_location=None):
        player_position = self.travel_time.prev_position
        seconds_between_locations = self.travel_time.time_to_location(next_pos)
        if seconds_between_locations > seconds_threshold:
            self.travel_time.set_fast_speed(is_fast_speed)
            seconds_between_locations = self.travel_time.time_to_location(next_pos)
            self.worker.log.info("{} seconds to next location using fast speed".format(str(seconds_between_locations)))
            map_objects = None
            remaining_distance = equi_rect_distance_m(player_position, next_pos)
            while remaining_distance > 1:
                available = self.travel_time.meters_available_until_gmo()
                player_position = move_towards(player_position, next_pos, available)
                map_objects = await self.get_map_objects(player_position)
                num_pokemons = len(catchable_pokemon(map_objects))
                self.worker.log.info("Remaining distance is {}, {} meters available, {} pokemon at this pos".format(
                    str(remaining_distance), str(available), str(num_pokemons)))
                if at_location:
                    await at_location(player_position, map_objects)
                remaining_distance = equi_rect_distance_m(player_position, next_pos)
            self.travel_time.use_slow_speed()
        else:
            if seconds_between_locations > 0.1:
                self.worker.log.info(
                    "{} seconds to next position {}".format(str(seconds_between_locations), str(next_pos)))
            map_objects = await self.get_map_objects(next_pos)
        return map_objects

    async def get_map_objects(self, player_position):
        map_objects = await self.worker.do_get_map_objects(player_position)
        self.next_gmo = datetime.now() + timedelta(seconds=10)
        return map_objects
        # did_map_objects = True

    def register_xp(self, xp):
        self.xp_log[datetime.now().minute] = xp

    def xp_30_minutes_ago(self):
        before_that = (datetime.now().minute - 30) % 59
        xp_30_min_ago = self.xp_log.get(before_that, 0)
        return xp_30_min_ago

    async def reached_target_level(self):
        self.level = await beh_handle_level_up(self.worker, self.level)
        if self.level >= int(self.target_level):
            self.worker.log.info("Reached target level {}, exiting thread".format(self.level))
            return True
        return False

    def has_active_lucky_egg(self):
        items_ = self.worker.account_info()["applied_items"]
        return 301 in items_ and items_[301] > datetime.now()

    def has_active_incense(self):
        items_ = self.worker.account_info()["applied_items"]
        return 401 in items_ and items_[401] > datetime.now()

    def has_egg(self):
        return has_lucky_egg(self.worker)

    def is_out_of_eggs_before_l30(self):
        return not has_lucky_egg(self.worker) and self.level > 25

    def has_lucky_egg(self):
        return has_lucky_egg(self.worker)

    def is_first_egg(self):
        return self.egg_number == 1 and datetime.now() < self.egg_expiration

    def is_any_egg(self):
        return self.egg_expiration and datetime.now() < self.egg_expiration

    async def use_egg(self, cm, xp_boost_phase):
        has_egg = self.has_lucky_egg()
        egg_active = self.has_active_lucky_egg()
        evolving_possible = not cm or cm.can_start_evolving()
        previous_egg_expired = (datetime.now() > self.next_egg)

        if not egg_active and has_egg and previous_egg_expired:
            if evolving_possible or xp_boost_phase:
                await self.worker.do_use_lucky_egg()
                self.egg_number += 1
                self.next_egg = datetime.now() + timedelta(minutes=90)
                self.egg_expiration = datetime.now() + timedelta(minutes=30)
                await db_set_egg_count(self.worker.account_info().username, egg_count(self.worker))
            elif self.initial_fast_egg:
                self.initial_fast_egg = False
                await self.worker.do_use_lucky_egg()
                self.egg_number += 1
                self.next_egg = datetime.now() + timedelta(minutes=60)
                self.egg_expiration = datetime.now() + timedelta(minutes=30)
                await db_set_egg_count(self.worker.account_info().username, egg_count(self.worker))
        return egg_active

    def explain(self):
        self.worker.log.info(
            "incenses={}, has_active_incense={}, next_incense={}, eggs={}, has_active_egg={}, next_egg={}".format(
                str(incense_count(self.worker)), str(self.has_active_incense()), str(self.next_incense),
                str(egg_count(self.worker)), str(self.has_active_lucky_egg()), str(self.next_egg)))

    def use_incense_if_ready(self):
        if has_incense(
            self.worker) and not self.has_active_incense() and not self.has_active_lucky_egg() \
                and self.next_incense > datetime.now():
            self.next_incense = datetime.now() + timedelta(minutes=30)
            self.worker.do_use_incense()

    def use_incense(self):
        if has_incense(self.worker) and not self.has_active_incense() and self.next_incense > datetime.now():
            self.next_incense = datetime.now() + timedelta(minutes=30)
            self.worker.do_use_incense()


class PositionFeeder(object):
    def __init__(self, route_elements, is_forced_update):
        self.is_forced_update = is_forced_update
        self.route_elements = route_elements
        self.pos = 0

    def index(self):
        return self.pos

    def index_str(self):
        return str(self.pos) + "/" + str(len(self.route_elements))

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def next(self):
        if self.is_forced_update.isSet():
            log.info("Forced update, qutting")
            raise StopIteration

        if self.pos >= len(self.route_elements):
            raise StopIteration

        pos_ = self.route_elements[self.pos]
        self.pos += 1

        return pos_

    def peek(self):
        if self.pos >= len(self.route_elements):
            return None
        pos_ = self.route_elements[self.pos]
        return pos_

    def __getitem__(self, key):
        return self.route_elements[key]

    def __setitem__(self, key, value):
        self.route_elements[key] = value

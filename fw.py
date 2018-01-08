import asyncio
import datetime
import logging
import random
from collections import Counter
from queue import Empty, Queue

from async_accountdbsql import db_set_temp_banned
from behaviours import beh_spin_nearby_pokestops
from common_accountmanager import OutOfAccounts
from getmapobjects import inrange_gyms
from pogom.apiRequests import feed_pokemon, set_player_team, AccountBannedException
from pogoservice import CaptchaRequired
from pokemonhandler import s2msg
from scannerutil import as_str
from workers import wrap_account_no_replace

log = logging.getLogger(__name__)


class BasicFeeder(object):
    def __init__(self, account_manager, termination_condition):
        self.account_manager = account_manager
        self.collected = {}
        self.termination_checker = termination_condition
        self.worker = None
        self.inventory = None
        self.feedings = Counter()
        self.next_battle_helper = datetime.datetime.now()
        self.gym_name = "(unknown gym name)"
        self.running = True
        self.passives = {}
        self.first_berried = {}
        self.slaves = []
        self.replaced = 0
        self.next_spin_at = datetime.datetime.now()


    @staticmethod
    def has_berries(inventory):
        # 701 = razz, 703 = nanab, 705 = pinap, 706 = golden razz
        return inventory.get(701, 0) != 0 or inventory.get(703, 0) != 0 or inventory.get(705, 0) != 0

    @staticmethod
    def pokemon_needing_motivation(g_gym_info):
        info_ = g_gym_info["responses"]["GYM_GET_INFO"]
        defenders = info_.gym_status_and_defenders.gym_defender
        result = [x.motivated_pokemon for x in defenders if
                  x.motivated_pokemon.motivation_now < 0.7]
        return result

    @staticmethod
    def trainers_in_gym(g_gym_info):
        info_ = g_gym_info["responses"]["GYM_GET_INFO"]
        defenders = info_.gym_status_and_defenders.gym_defender
        result = [x.trainer_public_profile.name for x in defenders]
        return result

    @staticmethod
    def berry_to_use(inventory):
        # 701 = razz, 703 = nanab, 705 = pinap, 706 = golden razz
        if inventory.get(701, 0) != 0:
            return 701
        if inventory.get(703, 0) != 0:
            return 703
        if inventory.get(705, 0) != 0:
            return 705
        return None

    async def spin_stops(self, map_objects, pos):
        if datetime.datetime.now() > self.next_spin_at:
            await beh_spin_nearby_pokestops(self.worker, map_objects, pos, 39, None, None, )
            self.next_spin_at = datetime.datetime.now() + datetime.timedelta(minutes=5)

    async def safe_get_map_objects(self, pos):
        try:
            return await self.worker.do_get_map_objects(pos)
        except CaptchaRequired:
            self.worker = await self.account_manager.get_account_with_lures()
            return await self.safe_get_map_objects(pos)

    async def replace_account(self, pos):
        self.replaced += 1
        if self.replaced % 20 == 0:
            log.warning("Sleeping 5 minutes because replaced over 20 account")
            await asyncio.sleep(300)
        worker = wrap_account_no_replace(await self.account_manager.get_account(), self.account_manager)
        worker.account_info().update_position(pos)
        self.worker = worker
        self.inventory = None
        self.feedings = Counter()

        map_objects = await self.safe_get_map_objects(pos)
        if not self.inventory:
            self.inventory = self.worker.account_info()["items"]

        map_objects = await self.check_team(map_objects, pos, team=1)

        return worker

    async def worker_with_map_objects(self, pos, team):
        if self.worker is None:
            await self.replace_account(pos)

        map_objects = await self.safe_get_map_objects(pos)

        await self.spin_stops(map_objects, pos)

        if not self.inventory:
            self.inventory = self.worker.account_info()["items"]

        map_objects = await self.check_team(map_objects, pos, team)

        if self.worker.account_info()["team"] == 0:
            await asyncio.sleep(10)
            await set_player_team(self.worker.get_raw_api(), self.worker.account_info(), 1)  # mystic
            await asyncio.sleep(5)
        await asyncio.sleep(2)
        if self.worker.name() not in self.collected:
            level = self.worker.account_info()["level"]
            await self.worker.do_collect_level_up(level)
            self.collected[self.worker.name()] = self.worker
            await asyncio.sleep(10)
            map_objects = await self.safe_get_map_objects(pos)

        while not self.has_berries(self.inventory):
            log.info(u"No berries in inventory for worker {}, replacing".format(self.worker.name()))
            await self.replace_account(pos)
            map_objects = await self.safe_get_map_objects(pos)
            self.inventory = self.worker.account_info()["items"]
        return map_objects

    async def check_team(self, map_objects, pos, team):
        while self.worker.account_info()["team"] != 0 and self.worker.account_info()["team"] != team:
            if self.worker:
                log.info(u"Skipping {}, wrong team on gym {}".format(self.worker.name(), self.gym_name))
            await self.replace_account(pos)
            map_objects = await self.safe_get_map_objects(pos)
            self.inventory = self.worker.account_info()["items"]
        return map_objects


class FeedWorker(BasicFeeder):
    def __init__(self, account_manager, termination_condition, trainers, defend, heavy):
        BasicFeeder.__init__(self, account_manager, termination_condition)
        self.defend = defend
        self.trainers = trainers
        self.next_battle_helper = datetime.datetime.now()
        self.heavy_defense = heavy
        self.good_pokemon = {242, 143, 208, 149, 80, 199, 197, 131, 134, 232, 181, 36}
        self.bad_pokemon = {10,13,16}
        self.defense_duration = 60 if heavy else 30

    async def berry_positions(self, positions):
        first_time = True
        while self.running:
            seconds = 3600
            for pos in positions:
                if self.termination_checker():
                    return True
                next_seconds = await self.berry_gym(pos, first_time)
                seconds = min(next_seconds, seconds)

            for x in self.feedings:
                if self.feedings[x] == random.choice([2,3]):
                    log.info(u"Acount has been feeding enough, changing account for {}".format(self.gym_name))
                    await self.replace_account(positions[0])
            first_time = False
            await asyncio.sleep(seconds)

    def contains_trainers(self, gym_info):
        trainers_in_gym = self.trainers_in_gym(gym_info)
        for x in self.trainers:
            if x == "*" or x in trainers_in_gym:
                return True
        return False


    def is_night(self):
        return datetime.datetime.now().hour >= 23 or datetime.datetime.now().hour < 7

    async def berry_gym(self, pos, first_time):
        map_objects = await self.worker_with_map_objects(pos=pos, team=1)
        gyms = list(inrange_gyms(map_objects, pos))
        if len(gyms) == 0:
            if self.worker:
                log.info(u"Worker {} not seeing any gyms, skipping".format(self.worker.name()))
            await self.replace_account(pos)
            map_objects = await self.worker_with_map_objects(pos=pos, team=1)
            gyms = list(inrange_gyms(map_objects, pos))

        if len(gyms) == 0:
            log.info(u"Worker {} not seeing any gyms, at this coordinate, exiting".format(self.worker.name()))
            self.running = False
            return 10

        gym = gyms[0]
        id_ = gym.id

        await self.spin_stops(map_objects, pos)

        if id_ in self.passives:
            if gym.last_modified_timestamp_ms == self.passives[id_]:
                log.info(u"No change in gym")
                return 120

        gym_pos = gym.latitude, gym.longitude
        gym_get_info = self.worker.do_gym_get_info(pos, gym_pos, id_)
        gym_get_info_data = gym_get_info["responses"]["GYM_GET_INFO"]
        self.gym_name = as_str(gym_get_info_data.name)

        if gym.owned_by_team != 1:
            if id_ not in self.passives:
                log.info(u"{} is being held by the wrong team. Waiting for the good guys".format(self.gym_name))
                self.passives[id_] = gym.last_modified_timestamp_ms
            return 120

        if first_time:
            log.info(
                u"There are {} gyms in range for {} at {}.".format(str(len(gyms)), self.worker.name(),
                                                                  str(pos)))

        gym_status_and_defenders = gym_get_info_data.gym_status_and_defenders
        pokemon_for_proto = gym_status_and_defenders.pokemon_fort_proto
        raid_info = pokemon_for_proto.raid_info
        raid_battle = datetime.datetime.fromtimestamp(raid_info.raid_battle_ms / 1000)
        raid_end = datetime.datetime.fromtimestamp(raid_info.raid_end_ms / 1000)

        if raid_battle < datetime.datetime.now() < raid_end:
            diff = (raid_end - datetime.datetime.now()).total_seconds()
            if id_ not in self.passives:
                log.info(u"Gym {} is closed for raid until {}, sleeping {}".format(self.gym_name, str(raid_end), diff))
                self.passives[id_] = gym.last_modified_timestamp_ms
            return diff

        if not self.contains_trainers(gym_get_info):
            if id_ not in self.passives:
                log.info(u"Trainers not in gym {}, waiting".format(self.gym_name))
                self.passives[id_] = gym.last_modified_timestamp_ms
            return 1200 + random.uniform(0, 900)
        elif first_time:
            log.info(u"Trainers in gym {}".format(self.gym_name))


        need_motivation = self.pokemon_needing_motivation(gym_get_info)

        if id_ in self.passives:
            del self.passives[id_]

        if len(need_motivation) == 0:
            return 120

        if len(need_motivation) > 0:
            if id_ not in self.first_berried:
                self.first_berried[id_] = datetime.datetime.now()
            await asyncio.sleep(5)

        filtered_needy = self.filter_motivation(id_, need_motivation)

        under_attack = pokemon_for_proto.is_in_battle
        if len(filtered_needy) > 0 or (under_attack and (self.defend or self.is_night())):
            if under_attack:
                s2msg("{} is under attack".format(self.gym_name))
            if datetime.datetime.now() > self.next_battle_helper:
                helper_end = datetime.datetime.now() + datetime.timedelta(minutes=self.defense_duration)
                self.next_battle_helper = helper_end
                self.slaves = []
                log.info(u"STARTING FEEDER SLAVES for {} {}"
                         .format(self.gym_name, "Under ATTACK" if under_attack else ""))
                await self.add_feed_slave(pos, helper_end)
                await self.add_feed_slave(pos, helper_end)
                await self.add_feed_slave(pos, helper_end)
                await self.add_feed_slave(pos, helper_end)
                if self.heavy_defense:
                    log.info(u"Starting additional battle slaves to work with gym {} under attack".format(self.gym_name))
                    await self.add_feed_slave(pos, helper_end)
                    await self.add_feed_slave(pos, helper_end)
                    await self.add_feed_slave(pos, helper_end)
                    await self.add_feed_slave(pos, helper_end)
                    await asyncio.sleep(30)  # extra time for heavy defense

                await asyncio.sleep(70)  # give workers time to start

        for motivated_pokemon in filtered_needy:
            for slave_queue in self.slaves:
                slave_queue.put(motivated_pokemon)

            berry = self.berry_to_use(self.inventory)
            if not berry:
                log.info(u"No more berries on account, replacing")
                await self.replace_account(pos)
            count = self.inventory.get(berry)
            ret = feed_pokemon(self.worker.get_raw_api(), self.worker.account_info(), berry,
                               motivated_pokemon.pokemon.id, id_, pos,
                               count)
            self.inventory[berry] -= 1
            log.info(u"Fed pokemon {}/{} berry {} ({} remaining) on gym {}".format(motivated_pokemon.pokemon.id,
                                                                                  motivated_pokemon.pokemon.pokemon_id,
                                                                                  berry,
                                                                                  self.inventory[berry],
                                                                                  self.gym_name))
            if ret["responses"]["GYM_FEED_POKEMON"].SUCCESS != 1:
                print("Not successful " + (str(ret)))
            else:
                self.feedings[motivated_pokemon.pokemon.id] += 1
            await asyncio.sleep(2)

        return 12 if len(need_motivation) > 0 else 120

    async def add_feed_slave(self, pos, helper_end):
        q = Queue()
        self.slaves.append(q)
        ld = FeedSlave(self.account_manager, lambda: datetime.datetime.now() > helper_end, q)
        ld.next_battle_helper = helper_end
        start_slave(pos, ld)
        await asyncio.sleep(5)
        return ld

    def filter_motivation(self, gym_id_, need_motivation):
        first_fed = self.first_berried[gym_id_]
        hours_in_gym = ((datetime.datetime.now() - first_fed).total_seconds()) / 3600
        return [x for x in need_motivation if self.should_feed(x, hours_in_gym)]

    '''
    pokemon {
      id: 10257802150801254862
      pokemon_id: BLISSEY
      cp: 2208
      stamina: 686
      stamina_max: 686
      move_1: POUND_FAST
      move_2: DAZZLING_GLEAM
      owner_name: "Unlikely2"
      height_m: 1.40167021751
      weight_kg: 30.5573978424
      individual_attack: 15
      individual_defense: 15
      individual_stamina: 15
      cp_multiplier: 0.654532194138
      pokeball: ITEM_ULTRA_BALL
      battles_attacked: 28
      battles_defended: 97
      creation_time_ms: 1491570774325
      num_upgrades: 56
      nickname: "Blissey$"
      pokemon_display {
        gender: FEMALE
      }
    }
    deploy_ms: 1509342268441
    cp_when_deployed: 3219
    motivation_now: 0.607285499573
    cp_now: 2208
    berry_value: 0.15000000596
    food_value {
      motivation_increase: 0.15000000596
      cp_increase: 386
      food_item: ITEM_WEPAR_BERRY
    }
    food_value {
      motivation_increase: 0.392714500427
      cp_increase: 1011
      food_item: ITEM_GOLDEN_RAZZ_BERRY
    }
    food_value {
      motivation_increase: 0.15000000596
      cp_increase: 386
      food_item: ITEM_RAZZ_BERRY
    }
    food_value {
      motivation_increase: 0.15000000596
      cp_increase: 386
      food_item: ITEM_PINAP_BERRY
    }
    food_value {
      motivation_increase: 0.1875
      cp_increase: 483
      food_item: ITEM_NANAB_BERRY
    }
    food_value {
      motivation_increase: 0.15000000596
      cp_increase: 386
      food_item: ITEM_BLUK_BERRY
    }
    '''

    def should_feed(self ,motivated_pokemon, hours_in_gym):
        pokemon = motivated_pokemon.pokemon
        if pokemon.owner_name in self.trainers:
            return random.uniform(0,1) < (5/hours_in_gym)
        if motivated_pokemon.cp_when_deployed < 700 and pokemon.pokemon_id != 213:  # shuckle
            return False
        if pokemon.pokemon_id in self.bad_pokemon:
            return False
        if pokemon.pokemon_id in self.good_pokemon:
            return random.uniform(0,1) < (4/hours_in_gym)
        if pokemon.individual_attack == 15 and pokemon.individual_defense == 15 and pokemon.individual_stamina == 15:
            return random.uniform(0,1) < (3/hours_in_gym)
        return random.uniform(0, 1) < (2 / hours_in_gym)


class FeedSlave(BasicFeeder):
    def __init__(self, account_manager, termination_condition, queue):
        BasicFeeder.__init__(self, account_manager, termination_condition)
        self.queue = queue
        self.log = logging.getLogger("feedslave")

    async def slave_task(self, pos):
        map_objects = await self.worker_with_map_objects(pos=pos, team=1)
        gyms = inrange_gyms(map_objects, pos)
        if len(gyms) == 0:
            if self.worker:
                self.log.info(u"Worker {} not seeing any gyms, skipping".format(self.worker.name()))
            await self.replace_account(pos)
            map_objects = await self.worker_with_map_objects(pos=pos, team=1)
            gyms = inrange_gyms(map_objects, pos)

        if len(gyms) == 0:
            self.log.info(u"Worker {} not seeing any gyms, at this coordinate, exiting".format(self.worker.name()))
            self.running = False
            return 10

        gym = gyms[0]
        id_ = gym.id

        gym_pos = gym.latitude, gym.longitude
        gym_get_info = self.worker.do_gym_get_info(pos, gym_pos, id_)
        gym_get_info_data = gym_get_info["responses"]["GYM_GET_INFO"]
        self.gym_name = as_str(gym_get_info_data.name)

        while self.running:
            try:
                motivated_pokemon = self.queue.get(block=True, timeout=60)

                berry = self.berry_to_use(self.inventory)
                if not berry:
                    self.log.info(u"No more berries on account, replacing")
                    await self.replace_account(pos)
                count = self.inventory.get(berry)
                ret = feed_pokemon(self.worker.get_raw_api(), self.worker.account_info(), berry,
                                   motivated_pokemon.pokemon.id, id_, pos,
                                   count)
                if berry in self.inventory:
                    self.inventory[berry] -= 1
                remaining = self.inventory.get(berry, 0)
                log.info(u"Fed pokemon {} berry {} ({} remaining) on gym {}".format(motivated_pokemon.pokemon.id, berry,
                                                                                   remaining,
                                                                                   self.gym_name))
                if ret["responses"]["GYM_FEED_POKEMON"].SUCCESS != 1:
                    self.log.warning("Not successful " + (str(ret)))
                else:
                    self.feedings[motivated_pokemon.pokemon.id] += 1
                await asyncio.sleep(2)

                self.queue.task_done()

                await asyncio.sleep(10)

                for x in self.feedings:
                    if self.feedings[x] == 2:
                        self.log.info(u"Acount has been feeding enough, changing account for {}".format(self.gym_name))
                        await self.replace_account(pos)
            except Empty:
                if self.termination_checker():
                    self.running = False




async def safe_berry_one_position(pos, worker):
    while True:
        try:
            if await worker.berry_positions([pos]):
                return
            await asyncio.sleep(60)
        except OutOfAccounts:
            log.warning("No more accounts, exiting")
            return
        except AccountBannedException:
            log.warning("Account is temp banned, replacing")
            await db_set_temp_banned(worker.worker.name(), datetime.datetime.now())
            worker.worker = None
            await asyncio.sleep(4)
        except Exception as e:
            log.exception(e)
            await asyncio.sleep(12)


def start_slave(loc, worker):
    asyncio.ensure_future(safe_slave_task(loc, worker))


async def safe_slave_task(pos, worker):
    while True:
        try:
            if await worker.slave_task(pos):
                return
            await asyncio.sleep(60)
        except OutOfAccounts:
            log.warning("No more accounts, exiting")
            return
        except Exception as e:
            log.exception(e)
            await asyncio.sleep(12)

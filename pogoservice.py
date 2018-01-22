import asyncio
import logging
import random
import sys
import time
import unittest
from datetime import datetime, timedelta, datetime as dt
from pogeo import get_cell_ids

from aiopogo import PGoApi
from aiopogo.exceptions import BannedAccountException, \
    ServerSideRequestThrottlingException

from apitimings import api_timings
from apiwrapper import ReleasePokemon
from getmapobjects import cells_with_pokemon_data, can_not_be_seen, nearby_pokemon_from_cell, \
    catchable_pokemon_from_cell
from management_errors import GaveUpApiAction
from pogom.account import check_login, TooManyLoginAttempts, LoginSequenceFail, is_login_required
from pogom.apiRequests import add_lure, claim_codename, fort_details, fort_search, level_up_rewards, release_pokemon, \
    recycle_inventory_item, set_favourite, gym_get_info, encounter, get_map_objects, use_item_xp_boost, \
    AccountBannedException, evolve_pokemon, use_item_incense, catch_pokemon, use_item_encounter
from pogom.utils import generate_device_info
from scannerutil import nice_coordinate_string, nice_number, full_precision_coordinate_string, equi_rect_distance_m, distance_to_fort, fort_as_coordinate

log = logging.getLogger("pogoserv")



class PogoService(object):

    def __init__(self):
        self.log = logging.getLogger("pogoserv")

    async def do_gym_get_info(self, position, gym_position, gym_id):
        raise NotImplementedError("This is an abstract method.")

    async def do_encounter_pokemon(self, encounter_id, spawn_point_id, step_location):
        raise NotImplementedError("This is an abstract method.")

    async def do_get_map_objects(self, position):
        raise NotImplementedError("This is an abstract method.")

    async def login(self, position, proceeed=lambda account: True):
        raise NotImplementedError("This is an abstract method.")

    async def do_spin_pokestop(self, fort, step_location):
        raise NotImplementedError("This is an abstract method.")

    async def do_pokestop_details(self, fort):
        raise NotImplementedError("This is an abstract method.")

    async def do_collect_level_up(self, current_player_level):
        raise NotImplementedError("This is an abstract method.")

    async def do_transfer_pokemon(self, pokemon_ids):
        raise NotImplementedError("This is an abstract method.")

    async def do_evolve_pokemon(self, pokemon_id):
        raise NotImplementedError("This is an abstract method.")

    async def do_use_lucky_egg(self):
        raise NotImplementedError("This is an abstract method.")

    async def do_use_incense(self):
        raise NotImplementedError("This is an abstract method.")

    async def do_add_lure(self, fort, step_location):
        raise NotImplementedError("This is an abstract method.")

    async def do_recycle_inventory_item(self, item_id, count):
        raise NotImplementedError("This is an abstract method.")

    async def do_set_favourite(self, pokemon_uid, favourite):
        raise NotImplementedError("This is an abstract method.")

    async def do_use_item_encounter(self, berry_id, encounter_id, spawn_point_guid):
        raise NotImplementedError("This is an abstract method.")

    async def do_catch_pokemon(self, encounter_id, pokeball, normalized_reticle_size, spawn_point_id, hit_pokemon,
                         spin_modifier, normalized_hit_position):
        raise NotImplementedError("This is an abstract method.")

    def get_raw_api(self):
        raise NotImplementedError("This is an abstract method.")

    def getlayer(self, type):
        raise NotImplementedError("This is an abstract method.")

    def add_log(self, msg):
        raise NotImplementedError("This is an abstract method.")

    def most_recent_position(self):  # prolly shouldnt be here
        raise NotImplementedError("This is an abstract method.")

    def name(self):  # prolly shouldnt be here
        raise NotImplementedError("This is an abstract method.")

    def update_position(self, position):  # prolly shouldnt be here
        raise NotImplementedError("This is an abstract method.")

    def account_info(self):  # prolly shouldnt be here
        raise NotImplementedError("This is an abstract method.")

    async def do_claim_codename(self, name):  # prolly shouldnt be here
        raise NotImplementedError("This is an abstract method.")

    def game_api_log(self, msg, *args, **kwargs):
        log.info(msg, args, kwargs)

    def log_info(self, msg, *args, **kwargs):
        self.log.info(msg, args, kwargs)

    def log_debug(self, msg, *args, **kwargs):
        self.log.debug(msg, args, kwargs)

    def log_error(self, msg, *args, **kwargs):
        self.log.error(msg, args, kwargs)


class DelegatingPogoService(PogoService):
    def do_claim_codename(self, name):
        return self.target.do_claim_codename(name)

    # noinspection PyMissingConstructor
    def __init__(self, target):
        PogoService.__init__(self)
        self.target = target
        self.log = target.log

    def find_account_replacer(self):
        trgt = self.target
        while trgt and not isinstance(trgt, AccountReplacer) and not isinstance(trgt, Account2):
            trgt = trgt.target
        return trgt

    async def do_gym_get_info(self, position, gym_position, gym_id):
        return await self.target.do_gym_get_info(position, gym_position, gym_id)

    async def do_encounter_pokemon(self, encounter_id, spawn_point_id, step_location):
        return await self.target.do_encounter_pokemon(encounter_id, spawn_point_id, step_location)

    async def login(self, position, proceed=lambda x: True):
        return await self.target.login(position, proceed)

    async def do_get_map_objects(self, position):
        return await self.target.do_get_map_objects(position)

    async def do_spin_pokestop(self, fort, step_location):
        return await self.target.do_spin_pokestop(fort, step_location)

    async def do_pokestop_details(self, fort):
        return await self.target.do_pokestop_details(fort)

    async def do_collect_level_up(self, current_player_level):
        return await self.target.do_collect_level_up(current_player_level)

    async def do_use_lucky_egg(self):
        return await self.target.do_use_lucky_egg()

    async def do_use_incense(self):
        return await self.target.do_use_incense()

    async def do_transfer_pokemon(self, pokemon_ids):
        return await self.target.do_transfer_pokemon(pokemon_ids)

    async def do_evolve_pokemon(self, pokemon_id):
        return await self.target.do_evolve_pokemon(pokemon_id)

    async def do_add_lure(self, fort, step_location):
        return await self.target.do_add_lure(fort, step_location)

    async def do_recycle_inventory_item(self, item_id, count):
        return await self.target.do_recycle_inventory_item(item_id, count)

    async def do_set_favourite(self, pokemon_uid, favourite):
        return await self.target.do_set_favourite(pokemon_uid, favourite)

    async def do_catch_pokemon(self, encounter_id, pokeball, normalized_reticle_size, spawn_point_id, hit_pokemon,
                         spin_modifier, normalized_hit_position):
        return await self.target.do_catch_pokemon(encounter_id, pokeball, normalized_reticle_size, spawn_point_id,
                                            hit_pokemon,
                                            spin_modifier, normalized_hit_position)

    async def do_use_item_encounter(self, berry_id, encounter_id, spawn_point_guid):
        return await self.target.do_use_item_encounter(berry_id, encounter_id, spawn_point_guid)

    def getlayer(self, type):
        return self if isinstance(self, type) else self.target.getlayer(type)

    def get_raw_api(self):
        return self.target.get_raw_api()

    def add_log(self, msg):
        return self.target.add_log(msg)

    def most_recent_position(self):
        return self.target.most_recent_position()

    def name(self):
        return self.target.name()

    def update_position(self, position):
        return self.target.update_position(position)

    def account_info(self):
        return self.target.account_info()


'''
Account encapsulates an account, obeying the basic 10 second restrictions and gym
interaction speed restrictions. Clients that come in too fast will block until
acceptable interaction speeds have been achieved.

Non-goal: The account class does not obey speed restrictions for moving the
search area. Clients of this class are responsible for the movement speed.
'''


class Account2(PogoService):
    """An account"""

    def update_position(self, position):
        return self.__update_position(position)

    def account_info(self):
        return self

    def get_raw_api(self):
        return self.pgoApi


    def create_api(self, device_info):
        return PGoApi(device_info=device_info)


    # noinspection PyMissingConstructor
    def __init__(self, username, password, auth_service, args, search_interval,
                 rest_interval, hash_generator, login_hash_generator, ptc_proxy_supplier, niantic_proxy_supplier, db_data, account_manager):
        PogoService.__init__(self)
        self.log = logging.LoggerAdapter(logging.getLogger("pogoserv"), {'worker_name': username})
        self.ptc_proxy_supplier = ptc_proxy_supplier
        self.niantic_proxy_supplier = niantic_proxy_supplier
        self.current_ptc_proxy = None
        self.current_niantic_proxy = None
        self.account_manager = account_manager
        self.most_recent_get_map_objects = None
        self.lures = db_data.get("lures", None)
        self.rest_until = db_data.get("rest_until", None)
        self.allocated_at = db_data.get("allocated", None)
        self.last_login = db_data.get("last_login", None)
        self.banned = db_data.get("banned", None)
        self.blinded = db_data.get("blinded", None)
        self.warned = db_data.get("warned", None)
        self.allocation_end = db_data.get("allocation_end", None)
        self.level = db_data.get("level", None)
        self.allocated = False
        self.username = username
        self.password = password
        self.log = logging.LoggerAdapter(logging.getLogger("pogoserv"), {'worker_name': username})
        self.auth_service = auth_service
        self.args = args
        self.search_interval = search_interval  # todo. use
        self.rest_interval = rest_interval  # todo. use
        self.hash_generator = hash_generator
        self.login_hash_generator = login_hash_generator
        self.failures = 0
        self.consecutive_fails = 0
        identifier = username + password + "fnord"
        self.next_gym_details = self.timestamp_ms()
        self.last_api = dt.now()
        self.first_login = True
        self.last_location = None
        self.first_map_objects = None
        self.positioned_at = None
        self.remote_config = None
        self.captcha = None
        self.last_active = None
        self.last_location = None
        self.start_time = time.time()
        self.warning = None
        self.tutorials = []
        self.items = {}
        self.pokemons = {}
        self.incubators = []
        self.eggs = []
        self.spins = 0
        self.session_spins = 0
        self.walked = 0.0
        self.last_timestamp_ms = 0
        self.remote_config = None
        self.codename = None
        self.team = None
        self.buddy = None
        self.remaining_codename_claims = None
        self.xp = None
        self.fail_eager = self.account_manager.replace_warned
        self.log_items = []
        self.candy = {}
        self.applied_items = {}
        self.pgoApi = self.create_api(generate_device_info(identifier.encode("utf-8")))
        self.travel_time = TravelTime2(self.log)

    def reset_defaults(self):
        self['start_time'] = time.time()
        self['warning'] = None
        self['tutorials'] = []
        self['items'] = {}
        self['pokemons'] = {}
        self['incubators'] = []
        self['eggs'] = []
        self['level'] = 0
        self['spins'] = 0
        self['session_spins'] = 0
        self['walked'] = 0.0
        self['last_timestamp_ms'] = 0

    def getlayer(self, type):
        if isinstance(type, TravelTime2):
            return self.travel_time
        return self if isinstance(self, type) else None

    def rest_until(self, when):
        self.rest_until = when

    def add_log(self, msg):
        self.log_items.append(msg)

    def set_banned(self):
        self.banned = datetime.now()
        self.set_extra_resting()

    def is_resting(self):
        if self.rest_until:
            return self.rest_until > dt.now()

    def is_allocated(self):
        return self.allocated

    def set_resting(self):
        self.log.debug("{} being sent to rest for {} seconds".format(self.username, str(self.rest_interval)))
        self.rest_until = dt.now() + timedelta(seconds=self.rest_interval)

    def set_extra_resting(self):
        to_rest = max(12 * 3600, self.rest_interval)
        self.rest_until = dt.now() + timedelta(seconds=to_rest)

    def is_banned(self):
        return self.banned

    def __setup_proxy(self):
        if self.ptc_proxy_supplier is not None:
            self.current_ptc_proxy = self.ptc_proxy_supplier(None)
        else:
            self.current_ptc_proxy = None
        if self.niantic_proxy_supplier is not None:
            self.current_niantic_proxy = self.niantic_proxy_supplier(None)
        else:
            self.current_niantic_proxy = None
        self.log.info(u"Account {} ptc proxy {} nia proxy {}".format(self.username, self.current_ptc_proxy, self.current_niantic_proxy))

    def tryallocate(self):
        if not self.allocated and not self.is_resting() and not self.is_banned():  # currently this is guarded by the lock in account manager
            self.allocated = True
            self.allocated_at = datetime.now()
            self.__setup_proxy()
            return True

    def try_reallocate(self):
        if not self.allocated and not self.is_banned() and self.is_within_existing_alloc_window():  # currently this is guarded by the lock in account manager
            self.allocated = True
            self.__setup_proxy()
            return True
        return False

    def is_within_existing_alloc_window(self):
        return self.last_login and datetime.now() < (self.last_login + timedelta(seconds=self.search_interval))

    def free(self):
        if not self.allocated:
            raise ValueError("Attempting to release account {} that was not allocated ?".format(self.username))
        self.allocated = False

    def is_available(self):
        return not self.is_resting() and not self.is_allocated()

    async def __proceed(self):
        return True

    async def login(self, position, proceeed=__proceed):
        if not is_login_required(self.pgoApi):
            return True

        self.__update_proxies()
        self.__update_position(position)
        # Activate hashing server
        self.__update_proxies(login=True)
        result = await check_login(self.args, self, self.pgoApi, self.current_ptc_proxy, proceeed)
        if self.warning:
            if self.fail_eager:
                raise WarnedAccount()
        self.__update_proxies(login=False)
        if self.first_login:
            self.first_login = False
            await asyncio.sleep(1)  # avoid throttling
        return result

    async def __login_if_needed(self):
        await self.login(self.most_recent_position())

    STATUS_CODES = {
        0: 'UNKNOWN',
        1: 'OK',
        2: 'OK_RPC_URL_IN_RESPONSE',
        3: 'BAD_REQUEST',
        4: 'INVALID_REQUEST',
        5: 'INVALID_PLATFORM_REQUEST',
        6: 'REDIRECT',
        7: 'SESSION_INVALIDATED',
        8: 'INVALID_AUTH_TOKEN'
    }

    def as_map(self):
        return {"username": self.username, "password": self.password,
                "auth_service": self.auth_service}

    def most_recent_position(self):
        try:
            return self.pgoApi.get_position()
        except AttributeError:
            return self.pgoApi.position

    def time_of_most_recent_position(self):
        return self.positioned_at

    def __update_position(self, position):
        self.set_position(position)
        self.pgoApi.set_position(*position)

    def __update_proxies(self, login=False):
        hash_endpoint = 'http://pokehash.buddyauth.com'
        if login and self.login_hash_generator:
            self.pgoApi.activate_hash_server(next(self.login_hash_generator), hash_endpoint=hash_endpoint)
        else:
            self.pgoApi.activate_hash_server(next(self.hash_generator), hash_endpoint=hash_endpoint)

        if self.ptc_proxy_supplier is not None:
            self.current_ptc_proxy = self.ptc_proxy_supplier(self.current_ptc_proxy)

        if self.niantic_proxy_supplier is not None:
            self.current_niantic_proxy = self.niantic_proxy_supplier(self.current_niantic_proxy)

            if self.current_niantic_proxy is not None:
                self.log.debug(u"Using NIANTIC proxy " + self.current_niantic_proxy)
                self.pgoApi.proxy = self.current_ptc_proxy

    @staticmethod
    def timestamp_ms():
        return time.time() * 1000

    @staticmethod
    def __block_for_get_map_objects(self):
        target = max(self.next_get_map_objects, self.next_gym_details)
        current_timestamp = self.timestamp_ms()
        #if current_timestamp < target:
        #    ms_sleep = target - current_timestamp
        #    to_sleep = math.ceil(ms_sleep / float(1000))
        #    log.info(u"GMO blocker waiting for {}s".format(to_sleep))
        #    time.sleep(to_sleep)

    def __print_gym(self, gym):
        if gym is None:
            print("Gym is None")
            return
        return str(gym)

    @staticmethod
    def __print_gym_name(gym):
        if gym is None:
            return "(No gym found)"
        name_ = None
        if "name" in gym:
            name_ = gym["name"]
        if name_ is None:
            return "(No name)"
        return name_

    async def do_use_item_encounter(self, item_id, encounter_id, spawn_point_guid):
        return await self.game_api_event(
            use_item_encounter(self.pgoApi, self.account_info(), item=item_id,
                               encounter_id=encounter_id,
                               spawn_point_guid=spawn_point_guid),
            "use_item_encounter {}".format(str(item_id)))

    async def do_catch_pokemon(self, encounter_id, pokeball, normalized_reticle_size, spawn_point_id, hit_pokemon,
                         spin_modifier, normalized_hit_position):
        response_dict = await self.game_api_event(
            catch_pokemon(self.pgoApi,  self.account_info(),
                encounter_id=encounter_id,
                pokeball=pokeball,
                normalized_reticle_size=normalized_reticle_size,
                spawn_point_id=spawn_point_id,
                hit_pokemon=hit_pokemon,
                spin_modifier=spin_modifier,
                normalized_hit_position=normalized_hit_position
            ),
            "catch_pokemon {}".format(str(encounter_id)))

        return response_dict

    async def do_set_favourite(self, pokemon_uid, favourite):
        self.__update_proxies()
        x = await self.game_api_event(
            set_favourite(self.pgoApi, self.account_info(), pokemon_uid, favourite),
            "set_favourite {}".format(str(pokemon_uid)))
        return x

    async def do_claim_codename(self, name):
        self.__update_proxies()
        await self.__login_if_needed()
        x = await self.game_api_event(
            claim_codename(self.pgoApi, self.account_info(), name),
            "claim_codename {}".format(str(name)))
        return x

    async def do_gym_get_info(self, position, gym_position, gym_id):
        try:
            self.__update_proxies()
            self.__update_position(position)
            await self.__login_if_needed()
            self.__update_position(self.last_location)  # redundant ?

            gym = {'gym_id': gym_id, 'latitude': gym_position[0], 'longitude': gym_position[1]}
            x = await self.game_api_event(
                gym_get_info(self.pgoApi, self.account_info(), position, gym),
                "gym_get_info {}".format(str(gym_id)))

            return x

        except Exception as e:
            print(('Exception while downloading gym details: %s', repr(e)))
            raise
        finally:
            self.next_get_map_objects = self.timestamp_ms() + 10000

    async def do_encounter_pokemon(self, encounter_id, spawn_point_id, step_location):
        async with self.travel_time.encounter_block(step_location):
            self.__update_proxies()
            self.__update_position(step_location)
            await self.__login_if_needed()

            encounter_result2 = await self.game_api_event(
                encounter(self.pgoApi, self.account_info(), encounter_id, spawn_point_id, step_location),
                "encounter {}".format(str(encounter_id)))


            if encounter_result2 is None:
                return
            return encounter_result2

    async def do_get_map_objects(self, position):
        if position is None:
            sys.exit("need position")
        async with self.travel_time.gmo_block(position):
            self.__update_proxies()
            self.__update_position(position)
            await self.__login_if_needed()

            cell_ids = get_cell_ids((position[0], position[1]))
            cell_ids_ts = {}
            for cid in cell_ids:
                if cid not in cell_ids_ts:
                    cell_ids_ts[cid] = 0
            self.__block_for_get_map_objects(self)

            self.last_api = datetime.now()

            map_objects = await self.game_api_event(get_map_objects(self.pgoApi, self.account_info(), position),
                                              "get_map_objects at {}".format(str(position)))

            if not self.has_captcha(map_objects) and not self.most_recent_get_map_objects and self.account_manager:
                await self.account_manager.update_initial_inventory(self.account_info())
            self.most_recent_get_map_objects = map_objects
            return map_objects

    async def game_api_event(self, the_lambda, msg):
        if is_login_required(self.pgoApi):
            await self.login(self.most_recent_position())
        time1 = time.time()
        try:
            return await the_lambda
        finally:
            time2 = time.time()
            ms_spent = int((time2 - time1) * 1000.0)
            msg = u"API " + msg + ", " + str(ms_spent) + "ms "
            if len(self.log_items) > 0:
                msg += ', '.join(self.log_items)
                self.log_items = []
            self.log.info(msg)

    def has_position(self):
        return self.most_recent_position() and self.most_recent_position()[0]

    def get_position(self):
        return self.last_location

    def set_position(self, position):
        self.positioned_at = datetime.now()
        self.last_location = position

    @staticmethod
    def has_captcha(response_dict):
        responses_ = response_dict
        if 'CHECK_CHALLENGE' not in responses_:
            return False
        captcha_url = responses_['CHECK_CHALLENGE'].challenge_url
        return len(captcha_url) > 1

    def name(self):
        return self.username

    def status_name(self):
        return self.username

    def status_data(self):
        return {
            'type': 'Worker',
            'message': 'Idle',
            'success': 0,
            'fail': 0,
            'noitems': 0,
            'skip': 0,
            'captcha': 0,
            'username': self.username,
            'proxy_display': '',
            'proxy_url': self.current_ptc_proxy,
        }

    def get(self, key, default):
        val = self[key]
        if val:
            return val
        return default

    def __getitem__(self, key):
        if key == 'username' or key == 0:
            return self.username
        if key == 'password' or key == 1:
            return self.password
        if key == 'auth_service' or key == 'provider' or key == 2:
            return self.auth_service
        if key == 'last_active' or key == 3:
            return self.last_active
        elif key == 'last_location' or key == 4:
            return self.last_location
        elif key == 'captcha' or key == 5:
            return self.captcha
        elif key == 'last_timestamp_ms' or key == 6:
            return self.last_timestamp_ms
        elif key == 'warning' or key == 7:
            return self.warning
        elif key == 'remote_config' or key == 8:
            return self.remote_config
        elif key == 'pokemons' or key == 9:
            return self.pokemons
        elif key == 'walked' or key == 10:
            return self.walked
        elif key == 'start_time' or key == 11:
            return self.start_time
        elif key == 'tutorials' or key == 12:
            return self.tutorials
        elif key == 'items' or key == 13:
            return self.items
        elif key == 'incubators' or key == 14:
            return self.incubators
        elif key == 'eggs' or key == 15:
            return self.eggs
        elif key == 'level' or key == 16:
            return self.level
        elif key == 'spins' or key == 17:
            return self.spins
        elif key == 'session_spins' or key == 18:
            return self.session_spins
        elif key == 'remote_config' or key == 19:
            return self.remote_config
        elif key == 'buddy' or key == 20:
            return self.buddy
        elif key == 'codename' or key == 21:
            return self.codename
        elif key == 'team' or key == 22:
            return self.team
        elif key == 'remaining_codename_claims' or key == 23:
            return self.remaining_codename_claims
        elif key == 'xp' or key == 24:
            return self.xp
        elif key == 'candy' or key == 25:
            return self.candy
        elif key == 'applied_items' or key == 26:
            return self.applied_items
        elif key == 27:
            raise StopIteration
        raise ValueError("Unable to get key {}".format(key))

    def __setitem__(self, key, item):
        if key == 'last_active':
            self.last_active = item
        elif key == 'last_location':
            self.last_location = item
        elif key == 'warning':
            self.warning = item
        elif key == 'tutorials':
            self.tutorials = item
        elif key == 'buddy':
            self.buddy = item
        elif key == 'last_timestamp_ms':
            self.last_timestamp_ms = item
        elif key == 'start_time':
            self.start_time = item
        elif key == 'warning':
            self.warning = item
        elif key == 'tutorials':
            self.tutorials = item
        elif key == 'items':
            self.items = item
        elif key == 'pokemons':
            self.pokemons = item
        elif key == 'incubators':
            self.incubators = item
        elif key == 'eggs':
            self.eggs = item
        elif key == 'level':
            self.level = item
        elif key == 'spins':
            self.spins = item
        elif key == 'session_spins':
            self.session_spins = item
        elif key == 'walked':
            self.walked = item
        elif key == 'remote_config':
            self.remote_config = item
        elif key == 'codename':
            self.codename = item
        elif key == 'team':
            self.team = item
        elif key == 'remaining_codename_claims':
            self.remaining_codename_claims = item
        elif key == 'xp':
            self.xp = item
        elif key == 'candy':
            self.candy = item
        elif key == 'applied_items':
            self.applied_items = item
        else:
            raise ValueError("Unable to set key {}".format(key))

    def __str__(self):
        return self.username


    # todo: use ?
    def update_response_failure_state__(self, response_dict):
        if not response_dict:
            self.failures += 1
            self.consecutive_fails += 1
            return True
        else:
            return False

    async def do_pokestop_details(self, fort):
        self.__update_proxies()
        await self.__login_if_needed()
        fd = await self.game_api_event(fort_details(self.pgoApi, self.account_info(), fort),
                                 "fort_details at fort {},{}".format(str(fort.latitude), str(fort.longitude)))
        return fd

    async def do_spin_pokestop(self, fort, step_location):
        async with self.travel_time.fort_search_block(step_location):
            self.__update_proxies()
            self.__update_position(step_location)
            await self.__login_if_needed()

            distance_m = distance_to_fort(step_location, fort)
            spin_response = await self.game_api_event(
                fort_search(self.pgoApi, self.account_info(), fort, step_location),
                "fort_search {} {} player {} {}m".format(str(fort.id), full_precision_coordinate_string(fort_as_coordinate(fort)),
                                                      full_precision_coordinate_string(step_location),
                                                      str(distance_m)))

            if self.has_captcha(spin_response):
                return

            # todo: this class should not be doing this logic
            spin_result = spin_response['FORT_SEARCH'].result
            if spin_result == 1:
                self.log.debug('Successful Pokestop spin.')
                return spin_response
            elif spin_result == 2:
                self.log.warning('Pokestop was not in range to spin.')
                return spin_response
            elif spin_result == 3:
                self.log.warning('Failed to spin Pokestop {}. Has recently been spun.'.format(str(fort.id)))
                return spin_response
            elif spin_result == 4:
                self.log.info('Failed to spin Pokestop. Inventory is full.')
                return spin_response
            elif spin_result == 5:
                self.log.warning('Maximum number of Pokestops spun for this day.')
                raise GaveUpApiAction("Poekstop limit reached")
            elif spin_result == 6:
                self.log.warning('POI_INACCESSIBLE for spin pokestop')
                return spin_response
            else:
                self.log.warning('Failed to spin a Pokestop. Unknown result %d.', spin_result)

    async def do_collect_level_up(self, current_level):
        self.__update_proxies()
        await self.__login_if_needed()
        self.log.debug("Getting level up reward")
        response_dict = await self.game_api_event(
            level_up_rewards(self.pgoApi, self.account_info()),
            "level_up_rewards {}".format(str(self.account_info()['level'])))

        if 'status_code' in response_dict and response_dict['status_code'] == 1:
            data = (response_dict
                    .get('responses', {})
                    .get('LEVEL_UP_REWARDS', {})
                    .get('items_awarded', []))

            for item in data:
                self.log.info('level_up_reward {}'.format(str(item)))
        return "OK"

    error_codes = {
        0: 'UNSET',
        1: 'SUCCESS',
        2: 'POKEMON_DEPLOYED',
        3: 'FAILED',
        4: 'ERROR_POKEMON_IS_EGG',
        5: 'ERROR_POKEMON_IS_BUDDY'
    }

    async def do_transfer_pokemon(self, pokemon_ids):
        if not pokemon_ids:
            return
        pokemon = await self.game_api_event(
            release_pokemon(self.pgoApi, self.account_info(), 0, release_ids=pokemon_ids),
            "release_pokemon {}".format(str(pokemon_ids)))
        rp = ReleasePokemon(pokemon)
        return rp.ok()

    async def do_evolve_pokemon(self, pokemon_id):
        result = await self.game_api_event(
            evolve_pokemon(self.pgoApi, self.account_info(), pokemon_id),
            "evolve_pokemon {}".format(str(pokemon_id)))
        responses = result
        return responses['EVOLVE_POKEMON']

    '''
    0: UNSET
    1: SUCCESS
    2: FAILED_POKEMON_MISSING
    3: FAILED_INSUFFICIENT_RESOURCES
    4: FAILED_POKEMON_CANNOT_EVOLVE
    5: FAILED_POKEMON_IS_DEPLOYED
    '''

    async def do_use_lucky_egg(self):
        items_ = self.applied_items
        if 301 in items_ and items_[301] > datetime.now():
            self.log.warning("Lucky egg already active, ignore request to use another")
            return 3

        self.log.info(u"{} using lucky egg".format(self.username))
        pokemon = await self.game_api_event(
            use_item_xp_boost(self.pgoApi, self.account_info()),
            "use_item_xp_boost")
        responses = pokemon
        res = responses['USE_ITEM_XP_BOOST'].result
        return res

        '''
        0: UNSET
1: SUCCESS
2: ERROR_INVALID_ITEM_TYPE
3: ERROR_XP_BOOST_ALREADY_ACTIVE
4: ERROR_NO_ITEMS_REMAINING
5: ERROR_LOCATION_UNSET'''

    async def do_use_incense(self):
        items_ = self.applied_items
        if 401 in items_ and items_[401] > datetime.now():
            self.log.warning("Incense already active, ignore request to use another")
            return 2
            self.log.info(u"{} using incense".format(self.username))
        pokemon = await self.game_api_event(
            use_item_incense(self.pgoApi, self.account_info()),
            "use_item_incense")
        responses = pokemon
        res = responses['USE_INCENSE'].result
        return res

    async def do_add_lure(self, fort, step_location):
        try:
            self.__update_proxies()
            add_lure_response = await self.game_api_event(
                add_lure(self.pgoApi, self.account_info(), fort, step_location),
                "add_lure {}".format(str(step_location)))
            add_fort_modifier_ = add_lure_response["ADD_FORT_MODIFIER"]
            return add_fort_modifier_.result
        except Exception as e:
            self.log.warning('Exception while adding lure to Pokestop: %s', repr(e))
            return False

    @staticmethod
    async def random_sleep(seconds):
        await asyncio.sleep(seconds + int(random.random() * 3))

    async def do_recycle_inventory_item(self, item_id, count):
        responses = await self.game_api_event(
            recycle_inventory_item(self.pgoApi, self.account_info(), item_id, count),
            "recycle_inventory_item {}, removing {}".format(str(item_id), str(count)))
        try:

            recycle_inventory_item_ = responses['RECYCLE_INVENTORY_ITEM']
            if recycle_inventory_item_.result != 1:
                self.log.warning("Failed to remove item {}, code {}", str(item_id), str(recycle_inventory_item_.result))
            else:
                return count
        except KeyError:  # todo align with error handling in general
            self.log.warning("Failed to remove item {}", item_id)


class Account3(Account2):
    def __init__(self, username, password, auth_service, args, search_interval,
                 rest_interval, hash_generator, login_hash_generator, ptc_proxy_supplier, niantic_proxy_supplier, db_data, account_manager, loop):
        self.loop = loop
        Account2.__init__(self, username, password, auth_service, args, search_interval,
                 rest_interval, hash_generator, login_hash_generator, ptc_proxy_supplier, niantic_proxy_supplier, db_data, account_manager)

    def create_api(self, device_info):
        return PGoApi(device_info=device_info)


class WorkingTimeScheduler(DelegatingPogoService):
    def __init__(self, pogoservice, search_interval, account_replacer):
        DelegatingPogoService.__init__(self, pogoservice)
        self.search_interval = search_interval
        self.account_replacer = account_replacer
        self.replace_at = datetime.now() + timedelta(seconds=self.randomized_search_interval())

    def randomized_search_interval(self):
        return self.search_interval + (100 * random.random())

    async def do_get_map_objects(self, position):
        if datetime.now() > self.replace_at:
            self.account_replacer.replace_for_sleep()
            self.replace_at = datetime.now() + timedelta(seconds=self.randomized_search_interval())

        return await self.target.do_get_map_objects(position)


cannot_be_seen_when_shadowbanned = can_not_be_seen()


class BanChecker(DelegatingPogoService):
    def __init__(self, pogoservice, account_manager, replacer):
        DelegatingPogoService.__init__(self, pogoservice)
        self.account_manager = account_manager
        self.pogoservice = pogoservice
        self.account_replacer = replacer

    @staticmethod
    def is_empty_status_3_response(response_dict):
        envelope_ = response_dict['envelope']
        if not envelope_:
            log.info(u"Malformed response: {}".format(str(envelope_)))
        status_code_ = envelope_.status_code == 3
        return status_code_

    async def __with_check(self, func):
        loginfail = False
        toomanylogins = False
        warned_account = False
        temp_banned = False
        objects = None
        try:
            objects = await func
        except AccountBannedException as e:
            log.warning("EmptyResponse")
            await self.account_manager.mark_temp_banned(self.account_info())
            temp_banned = True
        except TooManyLoginAttempts as e:
            await self.account_manager.mark_perm_banned(self.account_info())
            log.warning("TooManyLoginAttempts")
            toomanylogins = True
        except LoginSequenceFail as e:
            log.warning("LoginSequenceFail")
            loginfail = True
        except WarnedAccount:
            self.account_manager.mark_warned(self.account_info())
            log.warning("WarnedAccount")
            warned_account = True
            if self.account_replacer:
                await self.account_replacer.handle_warned()

        if warned_account:
            if self.account_replacer:
                await self.account_replacer.handle_warned()
                return await func
        elif temp_banned:
            if self.account_replacer:
                await self.account_replacer.replace_temp_banned()
                return await func
            else:
                raise AccountBannedException
        elif loginfail or toomanylogins:
            if self.account_replacer:
                await self.account_replacer.replace_temp_banned()
                return await func
            else:
                raise BannedAccountException
        return objects

    async def do_claim_codename(self, name):
        return await self.__with_check(super(BanChecker, self).do_claim_codename(name))

    async def login(self, position, proceed=lambda account: True):
        return await self.__with_check(super(BanChecker, self).login(position, proceed))

    async def do_get_map_objects(self, position):
        return await self.__with_check(super(BanChecker, self).do_get_map_objects(position))


class CaptchaChecker(DelegatingPogoService):
    def __init__(self, target, account_manager):
        super(CaptchaChecker, self).__init__(target)
        self.account_manager = account_manager

    async def do_get_map_objects(self, position):
        return await self.with_captcha_solve(super(CaptchaChecker, self).do_get_map_objects(position))

    async def do_gym_get_info(self, position, gym_position, gym_id):
        return await self.with_captcha_solve(super(CaptchaChecker, self).do_gym_get_info(position, gym_position, gym_id))

    async def do_spin_pokestop(self, fort, step_location):
        return await self.with_captcha_solve(super(CaptchaChecker, self).do_spin_pokestop(fort, step_location))

    async def do_encounter_pokemon(self, encounter_id, spawn_point_id, step_location):
        return await self.with_captcha_solve(super(CaptchaChecker, self).do_encounter_pokemon(encounter_id, spawn_point_id, step_location))

    async def with_captcha_solve(self, fn):
        objects = await fn
        captcha_uri = self.extract_captcha_uri(objects)
        if captcha_uri:
            await self.account_manager.solve_captcha(self.account_info(), captcha_uri)
            return await fn()
        return objects

    def extract_captcha_uri(self, response_dict):
        responses_ = response_dict
        if 'CHECK_CHALLENGE' not in responses_:
            log.error("{}:Expected CHECK_CHALLENGE not in response {}".format(self.name(), str(response_dict)))
            return
        captcha_url = responses_['CHECK_CHALLENGE'].challenge_url

        if len(captcha_url) > 1:
            return captcha_url


class BlindChecker(DelegatingPogoService):
    def __init__(self, pogoservice, account_manager, replacer):
        DelegatingPogoService.__init__(self, pogoservice)
        self.account_manager = account_manager
        self.pogoservice = pogoservice
        self.account_replacer = replacer
        self.blinded = 0

    async def do_get_map_objects(self, position):
        objects = await super(BlindChecker, self).do_get_map_objects(position)
        if not self.seen_blinded(objects):
            self.blinded += 1
        if self.blinded > 120:
            log.error("Account is blinded {}".format(self.name()))
            if self.account_replacer:
                await self.account_replacer.replace_blinded()
            else:
                raise BlindedAccount
            # retry. Might be better to throw an exception
            return super(BlindChecker, self).do_get_map_objects(position)
        return objects

    @staticmethod
    def seen_blinded(map_objects):
        for cell in cells_with_pokemon_data(map_objects):
            for pkmn in nearby_pokemon_from_cell(cell):
                pokemon_id = pkmn.pokemon_id
                if pokemon_id in cannot_be_seen_when_shadowbanned:
                    return True
            for pkmn in catchable_pokemon_from_cell(cell):
                pokemon_id = pkmn.pokemon_id
                if pokemon_id in cannot_be_seen_when_shadowbanned:
                    return True
        return False


class ApplicationBehaviour(DelegatingPogoService):
    """Handles waiting for animations and other behaviour-related stuff"""
    '''
    New pokemon to pokedex animation: 7.5 seconds, raikou 5.15 paa ny tlf
    Evole animation zubat: 18 sekunder
    Evole animation golbat: 18.5 sekunder
    Evolve animation gastly: 18.5 sek

    '''

    def __init__(self, pogoservice):
        DelegatingPogoService.__init__(self, pogoservice)
        self.pogoservice = pogoservice
        self.new_pokemon_caught = False
        self.behave_properly=True

    async def do_catch_pokemon(self, encounter_id, pokeball, normalized_reticle_size, spawn_point_id, hit_pokemon,
                         spin_modifier, normalized_hit_position):
        pokemon = await super(ApplicationBehaviour, self).do_catch_pokemon(encounter_id, pokeball, normalized_reticle_size,
                                                                     spawn_point_id, hit_pokemon, spin_modifier,
                                                                     normalized_hit_position)
        catch_pokemon = pokemon['CATCH_POKEMON']
        '''
        {'status': 1, 'capture_award': {'xp': [200, 1000, 20, 100], 'stardust': [100, 0, 0, 0], 'candy': [3, 0, 0, 0], 'activity_type': [1, 8, 10, 9]}, 'capture_reason': 1, 'captured_pokemon_id': 3402030586788431655L}
        '''
        xp = catch_pokemon.capture_award.xp
        self.new_pokemon_caught = len(xp) > 2 and (xp[1] == 500 or xp[1] == 1000 or xp[1] == 2000)  # 2000 for double xp
        if self.new_pokemon_caught and self.behave_properly:
            log.info(u"Initial catch animation delay")
            await asyncio.sleep(19)  # pokedex animation 7,5 seconds + catch anim. verify this rly 12 seconds catch
        return pokemon

    def is_new_pokemon_caught(self):
        return self.new_pokemon_caught


class Humanization(DelegatingPogoService):
    """Handles humanization and other time-related api constraints"""

    def __init__(self, pogoservice):
        DelegatingPogoService.__init__(self, pogoservice)
        self.pogoservice = pogoservice

class TravelTime2():
    """Handles travel time related constraint
    """

    def __init__(self, worker, fast_speed=25):
        self.worker = worker
        self.slow_speed = 9 # 32.5kmh
        self.fast_speed = fast_speed
        self.is_fast = False
        self.use_fast = False
        self.prev_position = None
        self.positioned_at = None
        self.latency_ms = None
        self.next_gmo = None

    def use_slow_speed(self):
        self.is_fast = False

    def get_speed(self):
        return self.is_fast

    def use_fast_speed(self):
        self.is_fast = True

    def set_fast_speed(self, is_fast):
        self.is_fast = is_fast

    def set_position(self, location):
        self.prev_position = location
        self.positioned_at = datetime.now()

    async def gmo_block(self, next_position):
        outer_class_self = self

        class ControlledExecution:
            async def __aenter__(self):
                await outer_class_self.sleep_for_account_travel(next_position)
                outer_class_self.set_position(next_position)

            async def __aexit__(self, exc_type, exc, tb):
                outer_class_self.next_gmo = datetime.now() + timedelta(seconds=10)

        return ControlledExecution()

    async def fort_search_block(self, next_position):
        outer_class_self = self
        class ControlledExecution:
            async def __aenter__(self):
                await outer_class_self.sleep_for_account_travel(next_position)
                outer_class_self.set_position(next_position)

            async def __aexit__(self, exc_type, exc, tb):
                pass

        return ControlledExecution()

    async def encounter_block(self, next_position):
        outer_class_self = self

        class ControlledExecution:
            async def __aenter__(self):
                await outer_class_self.sleep_for_account_travel(next_position)
                outer_class_self.set_position(next_position)

            async def __aexit__(self, exc_type, exc, tb):
                pass

        return ControlledExecution()

    def set_next_gmo(self):
        self.next_gmo = datetime.now() + timedelta(seconds=10)

    def must_gmo(self):
        return (dt.now() - self.positioned_at).total_seconds() > 30

    def time_to_location(self, location):
        if not self.prev_position:
            return 0
        return self.__priv_time_to_location(location)[1]

    def speed_to_use(self):
        return self.fast_speed if self.use_fast or self.is_fast else self.slow_speed

    def meters_available_until_gmo(self):
        """The number of meters we can move before violating speed limit"""
        if not self.positioned_at:
            return sys.maxsize
        earliest_next_gmo = self.next_gmo
        now = datetime.now()
        if now < earliest_next_gmo:
            total_seconds = (earliest_next_gmo - self.positioned_at).total_seconds()
        else:
            total_seconds = (now - self.positioned_at).total_seconds()
        return total_seconds * self.speed_to_use()

    def meters_available_right_now(self):
        """The number of meters we can move before violating speed limit"""
        if not self.positioned_at:
            return sys.maxsize
        now = datetime.now()
        total_seconds = (now - self.positioned_at).total_seconds()
        return total_seconds * self.speed_to_use()

    def slow_time_to_location(self, location):
        if not self.prev_position:
            return 0
        distance = equi_rect_distance_m(self.prev_position, location)
        seconds_since_last_use = dt.now() - self.positioned_at
        remaining_m,time_r = self.__calc_time(distance, seconds_since_last_use, self.slow_speed)
        return time_r


    def __priv_time_to_location(self, location):
        if not self.prev_position:
            return 0
        distance = equi_rect_distance_m(self.prev_position, location)
        seconds_since_last_use = dt.now() - self.positioned_at
        fast = False
        remaining_m, time_r = self.__calc_time(distance, seconds_since_last_use, self.slow_speed)
        if (time_r > 15 and self.use_fast) or self.is_fast:
            remaining_m, time_r = self.__calc_time(distance, seconds_since_last_use, self.fast_speed)
            fast = True
        return distance, time_r, fast

    def __calc_time(self, distance, seconds_since_last_use, speed):
        remaining_m = distance - (seconds_since_last_use.total_seconds() * speed)
        time_r = max(float(remaining_m) / speed, 0)
        return remaining_m, time_r

    async def sleep_for_account_travel(self, next_location):
        if not self.prev_position:
            return
        distance, delay, fast = self.__priv_time_to_location(next_location)
        if fast and delay > 0.1:
            self.worker.add_log(("FastMovement {}m, {}s, {} m/s".format(str(distance), str(delay), str(float(distance)/delay))))
            # self.add_log(("FastMovement {}m, {}s, {} m/s, prev={} at {}".format(str(distance), str(delay), str(float(distance)/delay), str(self.prev_position), str(self.positioned_at))))
        elif delay > 0.1:
            # self.add_log(("Movement {}m, {}s, {} m/s, pos={} prev={} at {}".format(str(distance), str(delay), str(float(distance)/delay), str(next_location), str(self.prev_position), str(self.positioned_at))))
            self.worker.add_log(("Movement {}m, {}s, {} m/s, pos={}".format(str(distance), str(delay), str(float(distance) / delay), str(next_location))))
        await asyncio.sleep(delay)


class TravelTime(DelegatingPogoService):
    """Handles travel time related constraint
    """

    def __init__(self, pogoservice, fast_speed=25):
        DelegatingPogoService.__init__(self, pogoservice)
        self.api_delay = self.getlayer(ApiDelay)
        self.slow_speed = 9 # 32.5kmh
        self.fast_speed = fast_speed
        self.is_fast = False
        self.use_fast = False
        self.prev_position = None
        self.positioned_at = None
        self.latency_ms = None

    def use_slow_speed(self):
        self.is_fast = False

    def get_speed(self):
        return self.is_fast

    def use_fast_speed(self):
        self.is_fast = True

    def set_fast_speed(self, is_fast):
        self.is_fast = is_fast

    def __set_position(self, location):
        self.prev_position = location
        self.positioned_at = datetime.now()

    async def do_get_map_objects(self, position):
        await self.__sleep_for_account_travel(position)
        try:
            return await super(TravelTime, self).do_get_map_objects(position)
        finally:
            self.__set_position(position)

    async def do_spin_pokestop(self, fort, step_location):
        await self.__sleep_for_account_travel(step_location)
        try:
            return await super(TravelTime, self).do_spin_pokestop(fort, step_location)
        finally:
            self.__set_position(step_location)

    async def do_encounter_pokemon(self, encounter_id, spawn_point_id, step_location):
        await self.__sleep_for_account_travel(step_location)
        try:
            return await super(TravelTime, self).do_encounter_pokemon(encounter_id, spawn_point_id, step_location)
        finally:
            self.__set_position(step_location)

    def must_gmo(self):
        return (dt.now() - self.positioned_at).total_seconds() > 30

    def time_to_location(self, location):
        if not self.prev_position:
            return 0
        return self.__priv_time_to_location(location)[1]

    def speed_to_use(self):
        return self.fast_speed if self.use_fast or self.is_fast else self.slow_speed

    def meters_available_until_gmo(self):
        """The number of meters we can move before violating speed limit"""
        if not self.positioned_at:
            return sys.maxint
        earliest_next_gmo = self.api_delay.next_gmo
        now = datetime.now()
        if now < earliest_next_gmo:
            total_seconds = (earliest_next_gmo - self.positioned_at).total_seconds()
        else:
            total_seconds = (now - self.positioned_at).total_seconds()
        return total_seconds * self.speed_to_use()

    def meters_available_right_now(self):
        """The number of meters we can move before violating speed limit"""
        if not self.positioned_at:
            return sys.maxint
        now = datetime.now()
        total_seconds = (now - self.positioned_at).total_seconds()
        return total_seconds * self.speed_to_use()

    def slow_time_to_location(self, location):
        if not self.prev_position:
            return 0
        distance = equi_rect_distance_m(self.prev_position, location)
        seconds_since_last_use = dt.now() - self.positioned_at
        remaining_m,time_r = self.__calc_time(distance, seconds_since_last_use, self.slow_speed)
        return time_r


    def __priv_time_to_location(self, location):
        if not self.prev_position:
            return 0
        distance = equi_rect_distance_m(self.prev_position, location)
        seconds_since_last_use = dt.now() - self.positioned_at
        fast = False
        remaining_m, time_r = self.__calc_time(distance, seconds_since_last_use, self.slow_speed)
        if (time_r > 15 and self.use_fast) or self.is_fast:
            remaining_m, time_r = self.__calc_time(distance, seconds_since_last_use, self.fast_speed)
            fast = True
        return distance, time_r, fast

    def __calc_time(self, distance, seconds_since_last_use, speed):
        remaining_m = distance - (seconds_since_last_use.total_seconds() * speed)
        time_r = max(float(remaining_m) / speed, 0)
        return remaining_m, time_r

    def __log_info(self, msg):
        log.info(u"%s:" + msg, self.name())

    '''
    Movement 180.310226106m, 16.0884855674s, 11.2074082642 m/s,
    '''

    def do_pokestop_details(self, fort):
        now = datetime.now()
        try:
            return super(TravelTime, self).do_pokestop_details(fort)
        finally:
            if not self.latency_ms:
                self.latency_ms = ((datetime.now() - now).microseconds) / 2000
                log.info(u"Network latency measured to {}ms".format(self.latency_ms))

    async def __sleep_for_account_travel(self, next_location):
        if not self.prev_position:
            return
        distance, delay, fast = self.__priv_time_to_location(next_location)
        if fast and delay > 0.1:
            self.add_log(("FastMovement {}m, {}s, {} m/s".format(str(distance), str(delay), str(float(distance)/delay))))
            # self.add_log(("FastMovement {}m, {}s, {} m/s, prev={} at {}".format(str(distance), str(delay), str(float(distance)/delay), str(self.prev_position), str(self.positioned_at))))
        elif delay > 0.1:
            # self.add_log(("Movement {}m, {}s, {} m/s, pos={} prev={} at {}".format(str(distance), str(delay), str(float(distance)/delay), str(next_location), str(self.prev_position), str(self.positioned_at))))
            self.add_log(("Movement {}m, {}s, {} m/s, pos={}".format(str(distance), str(delay), str(float(distance) / delay), str(next_location))))
        await asyncio.sleep(delay)


class ApiDelay(DelegatingPogoService):
    """Handles minimum api delay"""

    def __init__(self, pogoservice):
        DelegatingPogoService.__init__(self, pogoservice)
        self.pogoservice = pogoservice
        self.previous_action = None
        self.end_time_of_action = None
        self.start_time_of_action = None
        self.next_gmo = dt.now()

    async def run_delayed(self, action, func):
        if self.previous_action:
            # delay_ms = self.get_api_delay(self.previous_action, action)
            delay_ms = 500
            if delay_ms:
                now_ = dt.now()
                nextaction = self.end_time_of_action + timedelta(milliseconds=delay_ms)
                #nextaction = self.start_time_of_action + timedelta(milliseconds=delay_ms)
                if nextaction > now_:
                    sleep_s = (nextaction - now_).total_seconds()
                    self.add_log("API delay {}s {}->{}".format(str(sleep_s), self.previous_action, action))
                    await asyncio.sleep(sleep_s)
        time_of_request = dt.now()
        self.start_time_of_action = dt.now()
        try:
            return await func
        except ServerSideRequestThrottlingException as e:
            if self.end_time_of_action:
                seconds_since_previous = (time_of_request - self.end_time_of_action).total_seconds()
                log.warning(
                    "THROTTLED Performing api action {} ^^^, previous is {}. Actual seconds since last action {}".format(
                        action, self.previous_action, str(seconds_since_previous)))
            else:
                log.warning("THROTTLED Performing api action {} ^^^, previous is {}.".format(action, self.previous_action))
            raise e
        finally:
            self.previous_action = action
            self.end_time_of_action = dt.now()

    @staticmethod
    def get_api_delay(prev_action, next_action):
        prevaction = api_timings.get(prev_action)
        if prevaction:
            delay_ms = prevaction.get(next_action, None)
            if delay_ms != 0 and not delay_ms:
                log.warning("There is no defined api transition from {} to {}".format(prev_action, next_action))
            return delay_ms
        else:
            log.warning("There are no timings defined for {}".format(prev_action))

    async def do_get_map_objects(self, position):
        now_ = dt.now()
        if now_ < self.next_gmo:
            sleep_s = (self.next_gmo - now_).total_seconds()
            self.add_log("{}s for GMO api delay".format(str(sleep_s)))
            await asyncio.sleep(sleep_s)

        try:
            return await self.run_delayed("get_map_objects", super(ApiDelay, self).do_get_map_objects(position))
        finally:
            self.next_gmo = datetime.now() + timedelta(seconds=10)

    async def do_encounter_pokemon(self, encounter_id, spawn_point_id, step_location):
        return await self.run_delayed("encounter",
                                super(ApiDelay, self).do_encounter_pokemon(encounter_id, spawn_point_id,
                                                                                   step_location))

    async def do_pokestop_details(self, fort):
        return await self.run_delayed("fort_details", super(ApiDelay, self).do_pokestop_details(fort))

    async def do_spin_pokestop(self, fort, step_location):
        return await self.run_delayed("fort_search", super(ApiDelay, self).do_spin_pokestop(fort, step_location))

    async def do_use_lucky_egg(self):
        return await self.run_delayed("use_item_xp_boost", super(ApiDelay, self).do_use_lucky_egg())

    async def do_collect_level_up(self, current_player_level):
        return await self.run_delayed("level_up_rewards",
                                super(ApiDelay, self).do_collect_level_up(current_player_level))

    async def do_recycle_inventory_item(self, item_id, count):
        return await self.run_delayed("recycle_inventory_item",
                                super(ApiDelay, self).do_recycle_inventory_item(item_id, count))

    async def do_use_item_encounter(self, berry_id, encounter_id, spawn_point_guid):
        return await self.run_delayed("use_item_encounter",
                                super(ApiDelay, self).do_use_item_encounter(berry_id, encounter_id,
                                                                                    spawn_point_guid))

    async def do_catch_pokemon(self, encounter_id, pokeball, normalized_reticle_size, spawn_point_id, hit_pokemon,
                         spin_modifier, normalized_hit_position):
        return await self.run_delayed("catch_pokemon",
                                super(ApiDelay, self).do_catch_pokemon(encounter_id, pokeball,
                                                                               normalized_reticle_size, spawn_point_id,
                                                                               hit_pokemon, spin_modifier,
                                                                               normalized_hit_position))

    async def do_set_favourite(self, pokemon_uid, favourite):
        return await self.run_delayed("set_favorite_pokemon",
                                super(ApiDelay, self).do_set_favourite(pokemon_uid, favourite))

    async def do_evolve_pokemon(self, pokemon_id):
        return await self.run_delayed("evolve_pokemon",
                                super(ApiDelay, self).do_evolve_pokemon(pokemon_id))

    async def do_use_incense(self):
        return await self.run_delayed("use_incense",
                                super(ApiDelay, self).do_use_incense())

    async def do_add_lure(self, fort, step_location):
        return await self.run_delayed("add_fort_modifier",
                                super(ApiDelay, self).do_add_lure(fort, step_location))

    async def do_gym_get_info(self, position, gym_position, gym_id):
        return await self.run_delayed("gym_get_info",
                                super(ApiDelay, self).do_gym_get_info(position, gym_position, gym_id))

    async def do_transfer_pokemon(self, pokemon_ids):
        return await self.run_delayed("release_pokemon",
                                super(ApiDelay, self).do_transfer_pokemon(pokemon_ids))

    async def do_claim_codename(self, name):
        return await self.run_delayed("claim_codename",
                                super(ApiDelay, self).do_claim_codename(name))

    def __log_info(self, msg):
        log.info(u"%s:" + msg, self.name())

    async def __sleep_for_account_travel(self, account, next_location):
        if not account.has_position():
            return
        delay = self.time_to_location(next_location)
        if delay > 30:
            self.__log_info("Moving from {} to {}, delaying {} seconds".format(nice_coordinate_string(
                account.get_position()),
                nice_coordinate_string(next_location),
                nice_number(delay)))
        await asyncio.sleep(delay)


class AccountReplacer(DelegatingPogoService):
    def __init__(self, pogo_service, account_manager):
        DelegatingPogoService.__init__(self, pogo_service)
        self.account_manager = account_manager

    async def replace_banned(self):
        self.target = await self.account_manager.replace_temp_banned(self.target)

    async def handle_warned(self):
        self.target = await self.account_manager.handle_warned(self.target)

    async def replace_blinded(self):
        self.target = await self.account_manager.blinded(self.target)

    async def replace_for_sleep(self):
        self.target = await self.account_manager.replace_for_sleep(self.target)


class CaptchaRequired(BaseException):
    """Indicates that the account requires a captcha solve"""

    def __init__(self, captcha_url):
        self.captcha_url = captcha_url


class BooleanResponse(BaseException):
    """Boolean result from API"""

    def __init__(self, api_result):
        self.api_result = api_result


class EmptyResponse(BaseException):
    """Status code 100 and no data"""

    def __init__(self, api_result):
        self.api_result = api_result


class IntermittentError(BaseException):
    """Status code 100 and no data"""

    def __init__(self, api_result):
        self.api_result = api_result


class BlindedAccount(BaseException):
    def __init__(self, api_result):
        self.api_result = api_result


class WarnedAccount(BaseException):
    def __init__(self):
        pass


class TravelTime_meters_available(unittest.TestCase):
    def test(self):
        tt = TravelTime(None, 18)
        tt.positioned_at = datetime.now() - timedelta(seconds=2)
        meters_avail = tt.meters_available_until_gmo()
        self.assertTrue( meters_avail >= 18)
        self.assertTrue( meters_avail < 100)  # cant really do this without timesource

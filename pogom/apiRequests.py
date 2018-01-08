#!/usr/bin/python
# -*- coding: utf-8 -*-
import asyncio
import datetime
import logging

from aiopogo.exceptions import HashingQuotaExceededException, HashingTimeoutException, UnexpectedHashResponseException, \
    NianticOfflineException, InvalidRPCException
from aiopogo.hash_server import BadHashRequestException, HashingOfflineException
from aiopogo.utilities import f2i
from aiopogo import utilities as util

log = logging.getLogger(__name__)


class AccountBannedException(Exception):
    pass

request_sender = None
goman_endpoint = None


def set_goman_hash_endpoint(endpoint):
    global goman_endpoint
    goman_endpoint = endpoint


async def req_call_with_retries(req):
    attempts = 0
    while True:
        try:
            return await req_call_with_hash_retries(req)
        except NianticOfflineException:
            log.warning("NianticOfflineException")
            if attempts > 5:
                raise
            await asyncio.sleep(10 * attempts)
        except InvalidRPCException as e:
            log.warning("InvalidRPCException")
            if attempts > 5:
                raise
            await asyncio.sleep(1.5 * attempts)
        attempts += 1


async def req_call_with_hash_retries(req):
    attempts = 0
    while True:
        try:
            return await req.call()
        except HashingTimeoutException:
            log.warning("HashingTimeoutException")
            if attempts > 5:
                raise
            await asyncio.sleep(10 * attempts)
        except UnexpectedHashResponseException:
            log.warning("UnexpectedHashResponseException")
            if attempts > 5:
                raise
            await asyncio.sleep(1.5 * attempts)
        except HashingOfflineException:
            log.warning("Hashing offline")
            if attempts > 5:
                raise
            await asyncio.sleep(5 * attempts)
        except HashingQuotaExceededException:
            if goman_endpoint:
                log.info("using goman endpoint for this operation")
                req.__parent__.activate_hash_server(goman_endpoint, go_hash=True, gohash_endpoint='http://hash.gomanager.biz')
            else:
                if attempts > 5:
                    raise
                wait_time = 10 * attempts
                log.warning("Hashing quota exceeded, waiting {} seconds".format(wait_time))
                await asyncio.sleep(wait_time)
        attempts += 1



async def send_generic_request(req, account, settings=True, buddy=True, inbox=True):
    req.check_challenge()
    req.get_hatched_eggs()
    req.get_inventory(last_timestamp_ms=account['last_timestamp_ms'])
    req.check_awarded_badges()

    if settings:
        if 'remote_config' in account:
            req.download_settings(hash=account['remote_config']['hash'])
        else:
            req.download_settings()

    if buddy:
        req.get_buddy_walked()

    if inbox:
        req.get_inbox(is_history=True)

    hash_attempts = 0
    while True:
        try:
            resp = await req_call_with_retries(req)
            break
        except HashingOfflineException:  # todo: port logic  properly
            if hash_attempts > 5:
                log.error('Hashing server is unreachable, {} attempts, it might be offline.'.format(str(hash_attempts)))
            hash_attempts += 1
            await asyncio.sleep(min(hash_attempts,120))
            if hash_attempts > 180:  # 6 hours
                raise
        except BadHashRequestException:
            log.error('Invalid or expired hashing key: %s.',
                      req.__parent__.get_hash_server_token())
            raise

    __parse_inventory(account, resp)
    if settings:
        parse_remote_config(account, resp)

    # Clean all unneeded data.
    responses = [
        'GET_HATCHED_EGGS', 'GET_HOLO_INVENTORY', 'CHECK_AWARDED_BADGES',
        'DOWNLOAD_SETTINGS', 'GET_BUDDY_WALKED', 'GET_INBOX'
    ]
    for item in responses:
        if item in resp:
            del resp[item]

    log.log(5, 'Response: \n%s', resp)
    return resp


def parse_remote_config(account, api_response):
    if 'DOWNLOAD_REMOTE_CONFIG_VERSION' not in api_response:
        return

    remote_config = api_response['DOWNLOAD_REMOTE_CONFIG_VERSION']
    if remote_config.result == 0:
        raise AccountBannedException('The account has a temporal ban')

    asset_time = remote_config.asset_digest_timestamp_ms / 1000000
    template_time = remote_config.item_templates_timestamp_ms / 1000

    download_settings = {}
    download_settings['hash'] = api_response[
        'DOWNLOAD_SETTINGS'].hash
    download_settings['asset_time'] = asset_time
    download_settings['template_time'] = template_time

    account['remote_config'] = download_settings

    log.debug('Download settings for account %s: %s.', account['username'],
              download_settings)


# Parse player stats and inventory into account.
def __parse_inventory(account, api_response):
    if 'GET_INVENTORY' not in api_response:
        return
    inventory = api_response['GET_INVENTORY']
    parsed_items = 0
    parsed_pokemons = 0
    parsed_eggs = 0
    parsed_incubators = 0
    account['last_timestamp_ms'] = inventory.inventory_delta.new_timestamp_ms

    for item in inventory.inventory_delta.inventory_items:
        item_data = item.inventory_item_data
        if item_data.HasField('player_stats'):
            stats = item_data.player_stats
            account['level'] = stats.level
            account['spins'] = stats.poke_stop_visits
            account['walked'] = stats.km_walked
            account['xp'] = stats.experience

            log.debug('Parsed %s player stats: level %d, %f km ' +
                      'walked, %d spins.', account['username'],
                      account['level'], account['walked'], account['spins'])
        elif item_data.HasField("applied_items"):
            applied_items = account["applied_items"]
            for aitem in item_data.applied_items.item:
                exp = datetime.datetime.fromtimestamp(aitem.expire_ms / 1000)
                applied = datetime.datetime.fromtimestamp(aitem.applied_ms / 1000)
                id = aitem.item_id

                if id == 401 and applied < datetime.datetime.now() < exp:
                    applied_items[401] = exp
                else:
                    if 401 in applied_items: del applied_items[401]

                if id == 301 and applied < datetime.datetime.now() < exp:
                    applied_items[301] = exp
                else:
                    if 301 in applied_items: del applied_items[301]

        elif item_data.HasField('item'):
            item_id = item_data.item.item_id
            item_count = item_data.item.count
            account['items'][item_id] = item_count
            parsed_items += item_count
        elif item_data.HasField('candy'):
            account['candy'][item_data.candy.family_id] = item_data.candy.candy
        elif item_data.HasField('egg_incubators'):
            incubators = item_data.egg_incubators.egg_incubator
            for incubator in incubators:
                if incubator.pokemon_id != 0:
                    left = (incubator.target_km_walked - account['walked'])
                    log.debug('Egg kms remaining: %.2f', left)
                else:
                    account['incubators'].append({
                        'id': incubator.id,
                        'item_id': incubator.item_id,
                        'uses_remaining': incubator.uses_remaining
                    })
                    parsed_incubators += 1
        elif item_data.HasField('pokemon_data'):
            p_data = item_data.pokemon_data
            p_id = p_data.id
            if not p_data.is_egg:
                account['pokemons'][p_id] = {
                    'pokemon_id': p_data.pokemon_id,
                    'move_1': p_data.move_1,
                    'move_2': p_data.move_2,
                    'height': p_data.height_m,
                    'weight': p_data.weight_kg,
                    'gender': p_data.pokemon_display.gender,
                    'cp': p_data.cp,
                    'cp_multiplier': p_data.cp_multiplier,
                    'favorite' : p_data.favorite,
                    'deployed_fort_id' : p_data.deployed_fort_id,
                    'is_bad': p_data.is_bad
                }
                parsed_pokemons += 1
            else:
                if p_data.egg_incubator_id:
                    # Egg is already incubating.
                    continue
                account['eggs'].append({
                    'id': p_id,
                    'km_target': p_data.egg_km_walked_target
                })
                parsed_eggs += 1
    log.debug(
        'Parsed %s player inventory: %d items, %d pokemons, %d available' +
        ' eggs and %d available incubators.', account['username'],
        parsed_items, parsed_pokemons, parsed_eggs, parsed_incubators)


def catchRequestException(task):

    def _catch(function):

        def wrapper(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception as e:
                # log.exception('Exception while %s with account %s: %s.', task,
                #              kwargs.get('account', args[1])['username'], e)
                raise e

        return wrapper

    return _catch


@catchRequestException('spinning Pokestop')
async def fort_search(api, account, fort, step_location):
    req = api.create_request()
    req.fort_search(
        fort_id=fort.id,
        fort_latitude=fort.latitude,
        fort_longitude=fort.longitude,
        player_latitude=step_location[0],
        player_longitude=step_location[1])
    return await send_generic_request(req, account)


@catchRequestException('feeding pokemon')
async def feed_pokemon(api, account, item, pokemon_id, gym_id, player_location, starting_quantity):
    req = api.create_request()
    req.gym_feed_pokemon(
        item=item,
        starting_quantity=starting_quantity,
        gym_id=gym_id,
        pokemon_id=pokemon_id,
        player_lat_degrees=player_location[0],
        player_lng_degrees=player_location[1])
    return await send_generic_request(req, account)


@catchRequestException('select team pokemon')
async def set_player_team(api, account, team):
    req = api.create_request()
    req.set_player_team(team=team)
    return await send_generic_request(req, account)


@catchRequestException('addLure')
async def add_lure(api, account, fort, step_location):
    req = api.create_request()
    req.add_fort_modifier(
        modifier_type=501,
        fort_id=fort.id,
        player_latitude=step_location[0],
        player_longitude=step_location[1])
    return await send_generic_request(req, account)


@catchRequestException('claim codename')
async def claim_codename(api, account, name):
    req = api.create_request()
    req.claim_codename(codename=name)
    return await send_generic_request(req, account)


@catchRequestException('catch pokemon')
async def catch_pokemon(api, account, encounter_id, pokeball, normalized_reticle_size, spawn_point_id, hit_pokemon, spin_modifier, normalized_hit_position):
    req = api.create_request()
    req.catch_pokemon(
    encounter_id=encounter_id,
    pokeball=pokeball,
    normalized_reticle_size=normalized_reticle_size,
    spawn_point_id=spawn_point_id,
    hit_pokemon=hit_pokemon,
    spin_modifier=spin_modifier,
    normalized_hit_position=normalized_hit_position)
    return await send_generic_request(req, account)

@catchRequestException('set favourite')
async def set_favourite(api, account, pokemon_uid, favourite):
    req = api.create_request()
    req.set_favorite_pokemon(pokemon_id=pokemon_uid, is_favorite=favourite)
    return await send_generic_request(req, account)


@catchRequestException('getting Pokestop details')
async def fort_details(api, account, fort):
    req = api.create_request()
    req.fort_details(
        fort_id=fort.id, latitude=fort.latitude, longitude=fort.longitude)
    return await send_generic_request(req, account)


@catchRequestException('encountering Pokémon')
async def encounter(api, account, encounter_id, spawnpoint_id, scan_location):
    req = api.create_request()
    req.encounter(
        encounter_id=encounter_id,
        spawn_point_id=spawnpoint_id,
        player_latitude=scan_location[0],
        player_longitude=scan_location[1])
    return await send_generic_request(req, account)


@catchRequestException('clearing Inventory')
async def recycle_inventory_item(api, account, item_id, drop_count):
    req = api.create_request()
    req.recycle_inventory_item(item_id=item_id, count=drop_count)
    return await send_generic_request(req, account)


@catchRequestException('putting an egg in incubator')
async def use_item_egg_incubator(api, account, incubator_id, egg_id):
    req = api.create_request()
    req.use_item_egg_incubator(item_id=incubator_id, pokemon_id=egg_id)
    return await send_generic_request(req, account)

@catchRequestException('lycky egg')
async def use_item_xp_boost(api, account):
    req = api.create_request()
    req.use_item_xp_boost(item_id=301)
    return await send_generic_request(req, account)


@catchRequestException('use incense')
async def use_item_incense(api, account):
    req = api.create_request()
    req.use_incense(incense_type=401)
    return await send_generic_request(req, account)


@catchRequestException('releasing Pokemon')
async def release_pokemon(api, account, pokemon_id, release_ids=None):
    if release_ids is None:
        return False

    req = api.create_request()
    req.release_pokemon(pokemon_id=pokemon_id, pokemon_ids=release_ids)
    return await send_generic_request(req, account)

@catchRequestException('evolving Pokemon')
async def evolve_pokemon(api, account, pokemon_id):
    if pokemon_id is None:
        raise ValueError

    req = api.create_request()
    req.evolve_pokemon(pokemon_id=pokemon_id)
    return await send_generic_request(req, account)

@catchRequestException('getting Rewards')
async def level_up_rewards(api, account):
    req = api.create_request()
    req.level_up_rewards(level=account['level'])
    return await send_generic_request(req, account)


from pogeo import get_cell_ids


@catchRequestException('downloading map')
async def get_map_objects(api, account, location):
    cell_ids = get_cell_ids((location[0], location[1]))
    timestamps = [0, ]*len(cell_ids)
    req = api.create_request()
    req.get_map_objects(
        latitude=f2i(location[0]),
        longitude=f2i(location[1]),
        since_timestamp_ms=timestamps,
        cell_id=cell_ids)
    return await send_generic_request(req, account)


@catchRequestException('getting gym details')
async def gym_get_info(api, account, position, gym):
    req = api.create_request()
    req.gym_get_info(
        gym_id=gym['gym_id'],
        player_lat_degrees=f2i(position[0]),
        player_lng_degrees=f2i(position[1]),
        gym_lat_degrees=gym['latitude'],
        gym_lng_degrees=gym['longitude'])
    return await send_generic_request(req, account)

import asyncio
import datetime
import logging
import random

from async_accountdbsql import db_set_account_level, db_set_egg_count, db_set_lure_count
from geography import move_towards
from getmapobjects import inrange_pokstops, inventory_discardable_pokemon, catchable_pokemon, find_pokestop, \
    inrange_pokstops_and_gyms, parse_gyms
from gymdb import update_gym_from_details
from gymdbsql import do_with_backoff_for_deadlock, create_or_update_gym_from_gmo2
from inventory import total_iventory_count, egg_count, lure_count, inventory
from management_errors import GaveUpApiAction
from pogoservice import TravelTime
from pokemon_catch_worker import PokemonCatchWorker, WorkerResult
from pokemon_data import pokemon_name
from scannerutil import distance_to_fort, fort_as_coordinate, equi_rect_distance_m

L20_ITEM_LIMITS = {
    1: 20,  # Poke Ball
    2: 50,  # Great Ball
    3: 170,  # Ultra Ball
    101: 0,  # Potion
    102: 0,  # Super Potion
    103: 0,  # Hyper Potion
    104: 0,  # Max Potion
    201: 0,  # Revive
    202: 0,  # Max Revive
    701: 20,  # Razz Berry
    702: 0,  # Bluk Berry
    703: 0,  # Nanab Berry
    704: 0,  # Wepar Berry
    705: 70,  # Pinap Berry
    1101: 0,  # Sun stone
    1103: 0,  # Metal coat
    1105: 0,  # Upgrade
    1104: 0  # Dragon scale
}

L12_ITEM_LIMITS = {
    1: 20,  # Poke Ball
    2: 150,  # Great Ball
    3: 70,  # Ultra Ball. Ensure that we keep some because we play level 20 with these limits
    101: 0,  # Potion
    102: 0,  # Super Potion
    103: 0,  # Hyper Potion
    104: 0,  # Max Potion
    201: 0,  # Revive
    202: 0,  # Max Revive
    701: 20,  # Razz Berry
    702: 0,  # Bluk Berry
    703: 0,  # Nanab Berry
    704: 0,  # Wepar Berry
    705: 70,  # Pinap Berry
    1101: 0,  # Sun stone
    1103: 0,  # Metal coat
    1105: 0,  # Upgrade
    1104: 0  # Dragon scale
}

PHASE_0_ITEM_LIMITS = {
    1: 200,  # Poke Ball
    2: 50,  # Great Ball. Ensure that we keep some because we play level 12 with these limits
    3: 0,  # Ultra Ball
    101: 0,  # Potion
    102: 0,  # Super Potion
    103: 0,  # Hyper Potion
    104: 0,  # Max Potion
    201: 0,  # Revive
    202: 0,  # Max Revive
    701: 20,  # Razz Berry
    702: 0,  # Bluk Berry
    703: 0,  # Nanab Berry
    704: 0,  # Wepar Berry
    705: 70,  # Pinap Berry
    1101: 0,  # Sun stone
    1103: 0,  # Metal coat
    1105: 0,  # Upgrade
    1104: 0  # Dragon scale
}

F_LIMITS = {
    1: 0,  # Poke Ball
    2: 0,  # Great Ball. Ensure that we keep some because we play level 12 with these limits
    3: 0,  # Ultra Ball
    101: 0,  # Potion
    102: 0,  # Super Potion
    103: 0,  # Hyper Potion
    104: 0,  # Max Potion
    201: 0,  # Revive
    202: 0,  # Max Revive
    701: 90,  # Razz Berry
    702: 0,  # Bluk Berry
    703: 150,  # Nanab Berry
    704: 0,  # Wepar Berry
    705: 90,  # Pinap Berry
    1101: 0,  # Sun stone
    1103: 0,  # Metal coat
    1105: 0,  # Upgrade
    1104: 0  # Dragon scale
}


async def beh_clean_bag_with_limits(worker, limits, aggressive=False):
    rec_items = {}
    for item, count in worker.account_info()["items"].items():
        if item in limits and count > limits[item]:
            discard = count - limits[item]
            if discard > 50 and not aggressive:
                rec_items[item] = int(random.uniform(50, discard))
            else:
                rec_items[item] = discard

    removed = 0
    for item, count in list(rec_items.items()):
        # random_zleep(100, 1000)
        result = await worker.do_recycle_inventory_item(item_id=item, count=count)
        if result:
            removed += count
        worker.log.info(u"Bag cleaning Removed {} items".format(str(removed)))


async def beh_catch_encountered_pokemon(pogoservice, position, encounter_id, spawn_point_id, probablity, pokemon_id,
                                  is_vip=False, fast=False):
    start_catch_at = datetime.datetime.now()

    if probablity:
        name = pokemon_name(pokemon_id)
        catch_rate_by_ball = [0] + list(probablity.capture_probability)
        level = pogoservice.account_info()["level"]

        pogoservice.add_log(name)
        pcw = PokemonCatchWorker(position, spawn_point_id, pogoservice, fast)
        elements = pogoservice.account_info()["items"]
        catch = await pcw.do_catch(encounter_id, catch_rate_by_ball, elements, is_vip)
        if catch == WorkerResult.ERROR_NO_BALLS:
            return catch
        if catch:
            pogoservice.log.info(u"{} level {} caught {} id {} in {}".format(str(pogoservice.name()), str(level), name, str(catch),
                                                                str(datetime.datetime.now() - start_catch_at)))
        return catch
    else:
        pogoservice.log.warning("Encounter did not succeed")


async def random_sleep_z(lower, upper):
    ms = int(random.uniform(lower, upper))
    await asyncio.sleep(float(ms) / 1000)


async def beh_spin_nearby_pokestops(pogoservice, map_objects, position, range_m=39, blacklist=None, exclusions=None,
                              item_limits=None):
    spun = []
    spinning_distance_m = 39
    travel_time = pogoservice.getlayer(TravelTime)
    old_speed = travel_time.get_speed()
    if map_objects:
        pokestops = inrange_pokstops_and_gyms(map_objects, position, range_m)
        for idx, pokestop in enumerate(pokestops):
            if blacklist and pokestop.id in blacklist:
                pass
            if exclusions and pokestop.id in exclusions:
                pass
            elif pokestop.cooldown_complete_timestamp_ms > 0:
                pogoservice.log.debug('Pokestop is in cooldown, ignoring')
            elif pokestop.closed:
                pogoservice.log.debug('Pokestop is closed, ignoring')
            else:
                dist_to_stop = distance_to_fort(position, pokestop)
                if dist_to_stop > spinning_distance_m:
                    m_to_move = dist_to_stop - spinning_distance_m
                    pogoservice.log.info(u"Stop is {}m away, moving {}m closer".format(str(dist_to_stop), str(m_to_move)))
                    travel_time.use_slow_speed()
                    position = move_towards(position, fort_as_coordinate(pokestop), m_to_move)
                elif idx > 0:
                    idx_ = min(idx, 2) * 200
                    # pogoservice.log.info(u"Random sleeping at least {}ms for additional stops".format(idx_))
                    # await random_sleep_z(idx_, idx_ + 100)  # Do not let Niantic throttle
                res = await beh_spin_pokestop_raw(pogoservice, pokestop, position, item_limits=item_limits)
                if res == 1:
                    spun.append(pokestop.id)
    travel_time.set_fast_speed(old_speed)
    return spun


async def beh_spin_pokestop(pogoservice, map_objects, player_position, pokestop_id):
    if map_objects:
        pokestop = find_pokestop(map_objects, pokestop_id)
        if not pokestop:
            pogoservice.log.warning("Could not find pokestop {}, might be removed from game".format(pokestop_id))
            return
        if pokestop.cooldown_complete_timestamp_ms > 0:
            cooldown = datetime.datetime.fromtimestamp(pokestop.cooldown_complete_timestamp_ms / 1000)
            if cooldown > datetime.datetime.now():
                pogoservice.log.info('Pokestop is in cooldown until {}, ignoring'.format(str(cooldown)))
                return
        return await beh_spin_pokestop_raw(pogoservice, pokestop, player_position)
    else:
        pogoservice.log.warning("No mapobjects. learn python please")


async def beh_spin_pokestop_raw(pogoservice, pokestop, player_position, item_limits=None):
    await pogoservice.do_pokestop_details(pokestop)
    spin_response = await pogoservice.do_spin_pokestop(pokestop, player_position)
    result = spin_response['FORT_SEARCH'].result
    attempt = 0
    if result == 6:
        print(str(pokestop))

    if result == 4:
        await beh_aggressive_bag_cleaning(pogoservice, item_limits)
        spin_response = await pogoservice.do_spin_pokestop(pokestop, player_position)
        result = spin_response['FORT_SEARCH'].result

    while result == 2 and attempt < 6:
        stop_pos = (pokestop.latitude, pokestop.longitude)
        dist = equi_rect_distance_m(stop_pos, player_position)
        if dist > 40:
            pogoservice.log.error("Too far away from stop, {}m. this should not happen".format(str(dist)))
            return result  # give up
        if attempt == 0:
            if player_position != stop_pos:
                player_position = move_towards(player_position, stop_pos, 1)
        if attempt == 2:
            objs = await pogoservice.do_get_map_objects(player_position)
            pogoservice.log.info(u"Extra gmo gave catchanble {}".format(str(len(catchable_pokemon(objs)))))
        await asyncio.sleep(1)  # investigate if really needed
        attempt += 1
        spin_response = await pogoservice.do_spin_pokestop(pokestop, player_position)
        result = spin_response['FORT_SEARCH'].result
        pogoservice.log.info(u"{} attempt spinning gave result {}".format(str(attempt), str(result)))

    return result


async def beh_safe_scanner_bot(pogoservice, moves_generator):
    # noinspection PyBroadException
    try:
        await beh_do_scanner_bot(pogoservice, moves_generator, 120)
    except:
        pogoservice.log.exception("Outer worker catch block caught exception")


async def beh_do_scanner_bot(pogoservice, moves_generator, delay):
    last_scanned_position = None
    for move in moves_generator:
        current_position = move['coordinates']
        gym_id = move['gym_id']
        try:
            map_objects = await pogoservice.do_get_map_objects(current_position)
            gyms = parse_gyms(map_objects)
        except GaveUpApiAction:  # this should not really happen
            pogoservice.log.error("Giving up on location {} for gym {}".format(str(current_position), gym_id))
            continue
        if gyms is not None:
            try:
                gmo_gym = next(x for x in gyms if x["id"] == gym_id)
                create_or_update_gym_from_gmo2(gym_id, gmo_gym)
                if gmo_gym is None:
                    pogoservice.log.error("get_map_objects did not give us gym")
            except StopIteration:
                print("gym " + gym_id + "was not found at location " + str(last_scanned_position))

        last_scanned_position = current_position

        await asyncio.sleep(2 + random.random())
        try:
            b = await pogoservice.do_gym_get_info(current_position, current_position, gym_id)
            pogoservice.log.info(pogoservice, "Sending gym {} to db".format(gym_id))
            update_gym_from_details(b)
        except GaveUpApiAction:
            await asyncio.sleep(20)
            pogoservice.log.error(pogoservice, "Gave up on gym " + gym_id + " " + str(current_position))
            pass
        await asyncio.sleep(delay)


# noinspection PyBroadException
async def beh_safe_do_gym_scan(pogoservice, moves_generator):
    try:
        await beh_gym_scan(pogoservice, moves_generator, 0)
    except:
        pogoservice.log.exception("Outer worker catch block caught exception")


async def beh_gym_scan(pogoservice, moves_generator, delay):
    seen_gyms = set()
    last_scanned_position = None
    for move in moves_generator:
        current_position = move['coordinates']
        gym_id = move['gym_id']
        try:
            gyms = parse_gyms(pogoservice.do_get_map_objects(current_position))
        except GaveUpApiAction:  # this should not really happen
            pogoservice.log.error("Giving up on location {} for gym {}".format(str(current_position), gym_id))
            continue
        if gyms is not None:
            try:
                gmo_gym = next(x for x in gyms if x["id"] == gym_id)
                await beh_process_single_gmo_gym_no_dups(pogoservice, seen_gyms, gmo_gym, current_position)
            except StopIteration:
                print("gym " + gym_id + "was not found at location " + str(last_scanned_position))

        last_scanned_position = current_position
        await asyncio.sleep(delay)


async def rnd_sleep(sleep_time):
    random_ = sleep_time + int(random.random() * 2)
    await asyncio.sleep(random_)


async def beh_handle_level_up(worker, previous_level):
    new_level = int(worker.account_info()["level"])

    if previous_level and new_level != previous_level:
        await worker.do_collect_level_up(new_level)

    if new_level != previous_level:
        await db_set_account_level(worker.account_info().username, new_level)
        await db_set_egg_count(worker.account_info().username, egg_count(worker))
        await db_set_lure_count(worker.account_info().username, lure_count(worker))
    return new_level


async def beh_process_single_gmo_gym_no_dups(pogoservice, seen_gyms, gmo_gym, current_position):
    gym_id = gmo_gym["id"]

    if gym_id in seen_gyms:
        pogoservice.log.debug(pogoservice, "Gym {} already processed by this worker".format(gym_id))
        return
    seen_gyms.add(gym_id)

    return await beh_do_process_single_gmo_gym(pogoservice, gmo_gym, current_position)


async def beh_do_process_single_gmo_gym(pogoservice, gmo_gym, current_position):
    gym_id = gmo_gym.id

    modified = create_or_update_gym_from_gmo2(gym_id, gmo_gym)
    if gmo_gym is None:
        pogoservice.log.error(pogoservice, "get_map_objects did not give us gym")
    if not modified:
        pogoservice.log.debug(pogoservice, "Gym {} is not modified since last scan, skippings details".format(gym_id))
        return

    await asyncio.sleep(3 + random.random())
    try:
        gym_pos = gmo_gym.latitude, gmo_gym.longitude

        b = await pogoservice.do_gym_get_info(current_position, gym_pos, gym_id)
        pogoservice.log.info(pogoservice, "Sending gym {} to db".format(gym_id))
        gym_get_info_data = b["responses"]["GYM_GET_INFO"]

        update_gym_from_details(gym_get_info_data)
    except GaveUpApiAction:
        await asyncio.sleep(20)
        pogoservice.log.error(pogoservice, "Gave up on gym " + gym_id + " " + str(current_position))
        pass
    await asyncio.sleep(2 + random.random())


async def beh_random_bag_cleaning(worker, item_limits):
    total = total_iventory_count(worker)
    if total > 310 and random.random() > 0.3:
        await beh_clean_bag_with_limits(worker, item_limits)
    elif total > 320:
        await beh_clean_bag_with_limits(worker, item_limits)


def level_limit(level):
    return PHASE_0_ITEM_LIMITS if level < 12 else L12_ITEM_LIMITS if (12 < level < 21) else L20_ITEM_LIMITS


async def beh_aggressive_bag_cleaning(worker, limits=None):
    item_limits = limits if limits else level_limit(worker.account_info()["level"])

    total = total_iventory_count(worker)
    if total > 300:
        worker.log.info(u"Aggressive bag cleaning with {} items in inventory: {}".format(str(total), str(inventory(worker))))
        await beh_clean_bag_with_limits(worker, item_limits, aggressive=True)


async def discard_random_pokemon(worker):
    nonfavs = inventory_discardable_pokemon(worker)

    maxtrans = int(random.random() * len(nonfavs))
    samples = random.sample(nonfavs, maxtrans)
    transfers = {item["pokemon_data"]["id"] for item in samples}
    if len(transfers) > 0:
        worker.log.info(u"{} is believed to have discardable pokemons {}".format(worker.name(), str(
            [x["pokemon_data"]["id"] for x in nonfavs])))
        await rnd_sleep(10)
        rval = await  worker.do_transfer_pokemon(list(transfers))
        await rnd_sleep(10)
        return rval


async def discard_all_pokemon(worker):
    nonfavs = inventory_discardable_pokemon(worker)

    transfers = set(nonfavs)
    if len(transfers) > 0:
        worker.log.info(u"{} is believed (2)to have discardable pokemons {}".format(worker.name(), str([x for x in nonfavs])))
        await rnd_sleep(2)
        rval = await worker.do_transfer_pokemon(list(transfers))
        await rnd_sleep(2)
        return rval


async def random_sleep(seconds):
    await asyncio.sleep(seconds + int(random.random() * 3))


def is_lowhalf(afl):
    ms = str(afl).split(".")[1]
    return ms.endswith('1') or ms.endswith('2') or ms.endswith('3') or ms.endswith('4') or ms.endswith('5')


def contains_two(afl):
    ms = str(afl).split(".")[1]
    return "2" in ms


candy_rares = {131, 147, 148, 246, 247}
real_rares = {113, 114, 143, 149, 201, 242, 248}
candy12 = {10, 13, 16}


def is_candy_rare(pkmn):
    id_ = pkmn['pokemon_id']
    return id_ in candy_rares


def is_rare(pkmn):
    id_ = pkmn['pokemon_id']
    return id_ in real_rares

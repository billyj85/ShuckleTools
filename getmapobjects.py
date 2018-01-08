import logging
import sys
import unittest

from geopy.distance import vincenty

import pokemon_data
from pokemon_data import pokemon_name
from scannerutil import equi_rect_distance_m

log = logging.getLogger(__name__)

pokemons = pokemon_data.pokemons


def find_id_of_name(name):
    for id_, pokemon in pokemons.items():
        if "Nidoran" in pokemon["name"] and "Nidoran" in name:
            return int(id_)
        if pokemon["name"] == name:
            return int(id_)
    raise ValueError("Could not find {}".format(name))


def names_to_ids(names):
    return {find_id_of_name(name) for name in names}


def can_be_seen():
    seen = ['Pidgey', 'Rattata', 'Ekans', 'Sandshrew', "Nidoran\u2642", 'Zubat', 'Oddish', 'Paras', 'Meowth', 'Psyduck',
            'Poliwag', 'Bellsprout', 'Tentacool', 'Geodude', 'Magnemite', 'Krabby', 'Goldeen', 'Staryu', 'Magikarp',
            'Sentret', 'Ledyba', 'Spinarak', 'Natu', 'Marill', 'Hoppip', 'Sunkern', 'Wooper', 'Murkrow', 'Snubbull',
            'Slugma']
    return names_to_ids(seen)


def starters_with_evolutions():
    seen = ['Bulbasaur', 'Ivysaur', 'Venusaur', 'Squirtle', 'Wartortle', 'Blastoise', 'Charmander', 'Charmeleon',
            'Charizard']
    return names_to_ids(seen)


def can_not_be_seen():
    seen = ['Bulbasaur', 'Ivysaur', 'Venusaur', 'Squirtle', 'Wartortle', 'Blastoise', 'Charmander', 'Charmeleon',
            'Charizard', 'Caterpie', 'Weedle', 'Spearow', 'Clefairy', 'Vulpix', 'Jigglypuff',
            'Venonat', 'Mankey', 'Growlithe', 'Abra',
            'Slowpoke', 'Shellder', 'Gastly', 'Onix', 'Drowzee', 'Voltorb', 'Koffing', 'Chansey', 'Tangela', 'Horsea',
            'Mr. Mime', 'Scyther', 'Magmar', 'Lapras', 'Eevee',
            'Porygon', 'Omanyte', 'Kabuto', 'Aerodactyl', 'Snorlax', 'Dratini', 'Hoothoot', 'Chinchou', 'Mareep',
            'Sudowoodo', 'Aipom', 'Yanma', 'Unown', 'Wobbuffet', 'Girafarig', 'Shuckle', 'Sneasel', 'Teddiursa',
            'Swinub', 'Remoraid', 'Houndour', 'Stantler', 'Larvitar', 'Machop']
    return names_to_ids(seen)


class NoPokemonFoundPossibleSpeedViolation:
    def __init__(self):
        pass


def __has_pokemon_data(cell):
    return len(cell.wild_pokemons) > 0 or len(cell.catchable_pokemons) > 0 or len(cell.nearby_pokemons)


def cells_with_pokemon_data(response):
    return [cell for cell in (__get_map_cells(response)) if __has_pokemon_data(cell)]


def wild_pokemon(response):
    cells = __get_map_cells(response)
    return [wild for cell in cells for wild in cell.get('wild_pokemons', [])]


def catchable_pokemon(response):
    return [item for sublist in (__get_map_cells(response)) for item in sublist.catchable_pokemons]


def catchable_pokemon_by_distance(response, pos):
    wilds = catchable_pokemon(response)
    with_distance = [(vincenty(pos, (x.latitude, x.longitude)).m, x) for x in wilds]
    with_distance.sort(key=lambda tup: tup[0], reverse=True)
    return with_distance


def pokemon_names(catch_list):
    return ", ".join([pokemon_name(x.pokemon_id) for x in catch_list])


def nearby_pokemon(response):
    return nearby_pokemon_from_cells(__get_map_cells(response))


def encounter_capture_probablity(encounter_response):
    resp = encounter_response.get("responses", {}).get("ENCOUNTER", {}).get("capture_probability", None)
    if not resp:
        print(str(encounter_response))
    return resp


def nearby_pokemon_from_cells(cells):
    return [wild for cell in cells for wild in nearby_pokemon_from_cell(cell)]


def nearby_pokemon_from_cell(cell):
    return cell.nearby_pokemons


def catchable_pokemon_from_cell(cell):
    return cell.catchable_pokemons


def all_pokemon_pokedex_ids(map_objects):
    cells = __get_map_cells(map_objects)
    result = [x["pokemon_id"] for cell in cells for x in catchable_pokemon_from_cell(cell)]
    result += [x["pokemon_id"] for cell in cells for x in nearby_pokemon_from_cell(cell)]
    return result


def find_catchable_encounter(map_objects, encounter_id):
    for pokemon in catchable_pokemon(map_objects):
        if encounter_id == pokemon["encounter_id"]:
            return pokemon


def s2_cell_ids(response):
    cells = response["responses"]["GET_MAP_OBJECTS"]["map_cells"]
    return s2_cell_ids_from_cells(cells)


def inventory_item_data(response, type_):
    inv = response["responses"].get("GET_INVENTORY", {})
    resp = inv.get("inventory_delta", {}).get("inventory_items", [])
    return [x['inventory_item_data'] for x in resp if type_ in x['inventory_item_data']]


def inventory_pokemon(response):
    return inventory_item_data(response, "pokemon_data")


def inventory_discardable_pokemon(worker):
    inv_pokemon = worker.account_info().pokemons
    buddy_id = worker.account_info()["buddy"]
    nonfavs = [id_ for id_, pokemon in inv_pokemon.items() if is_discardable(worker, id_, pokemon, buddy_id)]
    return nonfavs


def pokemon_uids(map_objects):
    inv_pokemon = inventory_pokemon(map_objects)
    uids = [x["pokemon_data"]["id"] for x in inv_pokemon]
    return uids


def pokemon_by_uid(map_objects, uid):
    inv_pokemon = inventory_pokemon(map_objects)
    matchin = [x for x in inv_pokemon if x["pokemon_data"]["id"] == uid]
    return matchin


def is_discardable(worker,pokemon_id, pkmn, buddy_id):
    favorite_ = pkmn.get("favorite", 0) != 0
    deployed = has_value(pkmn, "deployed_fort_id")
    buddy = buddy_id == pokemon_id
    worker.log.debug(u"favorite={}, deployed={}, buddy={}, buddy_id={}, pokemon_id={}".format(str(favorite_), str(deployed),
                                                                                     str(buddy_id), str(buddy_id),
                                                                                     str(pokemon_id)))
    return not favorite_ and not deployed and not buddy


def is_starter_pokemon(pokemon):
    return pokemon.get("pokemon_id", 0) in {1, 4, 7}


def has_value(pkmn, fiel):
    return len(pkmn.get(fiel, "")) > 0


def is_keeper(pkmn):
    return pkmn["pokemon_id"] == 64


def regular_nonfav(response):
    inv_pokemon = inventory_pokemon(response)
    nonfavs = [x for x in inv_pokemon if "favourite" not in x["pokemon_data"] and "is_egg" not in x[
        "pokemon_data"] and not has_value(x, "deployed_fort_id")]
    return nonfavs


def pokestop_detail(details_response):
    return details_response["FORT_DETAILS"]


def s2_cell_ids_from_cells(cells):
    return [cell.get("s2_cell_id") for cell in cells if cell.get("s2_cell_id")]


def find_gym(forts, gym_id):
    for fort in forts:
        if fort.id == gym_id:
            return fort

def parse_gyms(map_objects):
    return forts_of_type(map_objects, 0)


def parse_pokestops(map_objects):
    return forts_of_type(map_objects, 1)


def parse_pokestops_and_gyms(map_objects):
    return [item for sublist in (__get_map_cells(map_objects)) for item in sublist.forts]


def forts_of_type(map_dict, type_):
    return [item for sublist in (__get_map_cells(map_dict)) for item in sublist.forts if item.type == type_]


def find_pokestop(map_objects, pokestop_id):
    id_ = [candidate for candidate in forts_of_type(map_objects, 1) if candidate.id == pokestop_id]
    return id_[0] if len(id_) > 0 else None


def nearest_pokstop(map_objects, pos):
    result = None
    closest = sys.maxsize
    for pokestop in parse_pokestops(map_objects):
        distance = equi_rect_distance_m(pos, (pokestop.latitude, pokestop.longitude))
        if distance < closest:
            result = pokestop
            closest = distance
    return closest, result


def raid_gyms(map_objects, pos):
    gyms = inrange_gyms(map_objects, pos)
    return [candidate for candidate in gyms if candidate.raid_info.raid_level > 0]


def inrange_gyms(map_objects, pos):
    return fort_within_distance(parse_gyms(map_objects), pos, 750)


def inrange_pokstops(map_objects, pos, range_m=39):
    return fort_within_distance(parse_pokestops(map_objects), pos, range_m)


def inrange_pokstops_and_gyms(map_objects, pos, range_m=39):
    return fort_within_distance(parse_pokestops_and_gyms(map_objects), pos, range_m)


def pokstops_within_distance(map_objects, pos, m):
    return fort_within_distance(parse_pokestops(map_objects), pos, m)


def fort_within_distance(forts, pos, m):
    with_distance = [(equi_rect_distance_m(pos, (fort.latitude, fort.longitude)), fort) for fort in forts]
    items = [it for it in with_distance if it[0] < m]
    items.sort()
    return [x[1] for x in items]


def __check_speed_violation(cells):
    if sum(len(list(cell.keys())) for cell in cells) == len(cells) * 2:
        raise NoPokemonFoundPossibleSpeedViolation


def match_pokemon_in_result(response, pkmn_ids):
    found = [x.pokemon_id for x in catchable_pokemon(response) if x.pokemon_id in pkmn_ids]
    found += [x.pokemon_id for x in nearby_pokemon(response) if x.pokemon_id in pkmn_ids]
    log.info(u"Found {} of the specified IDs {}".format(len(found), found))
    return len(found)


def __get_map_cells(response):
    try:
        responses_ = response
    except TypeError:
        print(str(response))
        raise
    objects_ = responses_['GET_MAP_OBJECTS']
    return objects_.map_cells


class GMOShadowBans(unittest.TestCase):
    def test(self):
        self.assertEqual(30, len(can_be_seen()))
        not_seen = can_not_be_seen()
        self.assertEqual(57, len(not_seen))
        self.assertTrue(3 in not_seen)

import asyncio
import logging
import numbers

from six import itervalues

import pokemon_data
from apiwrapper import EncounterPokemon
from behaviours import beh_catch_encountered_pokemon, discard_all_pokemon
from geography import move_towards
from getmapobjects import catchable_pokemon_by_distance, pokemon_names
from pogoservice import TravelTime2
from pokemon_data import pokemon_name
from scannerutil import equi_rect_distance_m

# setup_logging()
log = logging.getLogger("catchmgr")
log.setLevel(logging.DEBUG)

class CatchConditions:
    catch_anything = False
    only_unseen = False
    only_candy = False,
    only_candy_12 = False,
    catch_50 = False

    @staticmethod
    def pre_l9_condition():
        result = CatchConditions()
        result.only_unseen = False
        result.only_candy = True
        result.only_candy_12 = True
        return result

    @staticmethod
    def initial_condition():
        result = CatchConditions()
        result.only_unseen = True
        result.only_candy = True
        result.only_candy_12 = True
        return result

    @staticmethod
    def everything_condition():
        result = CatchConditions()
        result.catch_anything = True
        result.only_unseen = True
        result.only_candy = True
        result.only_candy_12 = True
        return result


    @staticmethod
    def grind_condition():
        result = CatchConditions()
        result.only_candy = True
        result.only_candy_12 = True
        result.only_unseen = False
        result.catch_50 = True
        return result

    def is_candy_50_catch(self, pokemon_id):
        return self.catch_50 and pokemon_id in pokemon_data.candy50

    def is_candy_12_catch(self, pokemon_id):
        return self.only_candy_12 and pokemon_id in pokemon_data.candy12

    def is_candy_catch(self, pokemon_id):
        candy_12 = pokemon_id in pokemon_data.candy12
        candy_25 = pokemon_id in pokemon_data.candy25
        return self.only_candy and (candy_12 or candy_25)

    def log_description(self, phase):
        log.info(
            "Catch conditions for phase {}: catch_anything={}, unseen_catch={}, candy_catch={}, candy12_catch={}".format(
                str(phase), str(self.catch_anything), str(self.only_unseen), str(self.only_candy), str(self.only_candy_12)))

class CatchManager(object):
    preferred = {10, 13, 16, 19, 29, 32, 41, 69, 74, 92, 183}
    candy12 = pokemon_data.candy12
    candy12_evolvable = pokemon_data.candy12_evolvable
    candy25 = pokemon_data.candy25
    candy25_evolvable = pokemon_data.candy25_evolvable
    candy50 = pokemon_data.candy50

    def __init__(self, worker, catch_limit, fast=False):
        self.worker = worker
        self.travel_time = worker.getlayer(TravelTime2)

        self.catch_limit = int(catch_limit)
        self.seen_pokemon = {}
        self.transfers = []
        self.evolve_map = {}
        self.caught_pokemon_ids = set()
        self.processed_encounters = set()
        self.pokemon_caught = 0
        self.evolves = 0
        self.evolve_requirement = 180
        self.fast = fast

    def clear_state(self):
        self.processed_encounters = set()

    def is_caught_already(self, route_element):
        if type(route_element) is tuple:
            return False
        encounter_id = route_element.encounter_id
        return self.is_encountered_previously(encounter_id)

    async def do_catch_moving(self, map_objects, player_pos, next_pos, catch_condition, is_egg_active):
        all_caught = {}
        if not self.is_within_catch_limit():
            self.worker.log.info(u"Catch limit {} exceeeded, not catching any more".format(str(self.catch_limit)))
            return
        catch_list = catchable_pokemon_by_distance(map_objects, next_pos)
        names = pokemon_names([x[1] for x in catch_list])
        self.worker.log.info(u"{} pokemon in map_objects: {}".format(str(len(catch_list)), names))
        while len(catch_list) > 0:
            to_catch = catch_list[0][1]
            # print str(to_catch)
            encounter_id = to_catch.encounter_id
            pokemon_id = to_catch.pokemon_id

            unseen_catch = catch_condition.only_unseen and (pokemon_id not in self.caught_pokemon_ids)
            candy_catch = catch_condition.is_candy_catch(pokemon_id)
            candy_12_catch = catch_condition.is_candy_12_catch(pokemon_id)
            encountered_previously = self.is_encountered_previously(encounter_id)
            candy_50_catch = catch_condition.is_candy_50_catch(pokemon_id)

            will_catch = (is_egg_active or catch_condition.catch_anything or unseen_catch or candy_catch or candy_12_catch or candy_50_catch)

            if encountered_previously:
                self.worker.log.info(u"{} {} encountered previously".format(str(pokemon_name(pokemon_id)), str(encounter_id)))
            elif will_catch:
                # log.debug("To_catch={}".format(str(to_catch)))
                pokemon_distance_to_next_position = catch_list[0][0]
                player_distance_to_next_position = equi_rect_distance_m(player_pos, next_pos)
                map_pokemon = catch_list[0][1]
                on_other_side = (player_pos[1] < next_pos[1] < map_pokemon.longitude) or (player_pos[1] > next_pos[1] > map_pokemon.longitude)

                if on_other_side:
                    available_mobility = self.travel_time.meters_available_right_now()
                    actual_meters = min(available_mobility, player_distance_to_next_position)
                    self.worker.log.info(u"Moving closer {} metres. {} meters_available right now".format(str(actual_meters),
                                                                                             str(available_mobility)))
                    player_pos = move_towards(player_pos, next_pos, actual_meters)
                if pokemon_distance_to_next_position < player_distance_to_next_position:
                    m_to_move = player_distance_to_next_position - pokemon_distance_to_next_position
                    available_mobility = self.travel_time.meters_available_right_now()
                    actual_meters = min(available_mobility, m_to_move)
                    self.worker.log.info(u"player_distance_to_next_position={},pokemon_distance_to_next_position={}".format(
                        str(player_distance_to_next_position), str(pokemon_distance_to_next_position)))
                    self.worker.log.info(u"Could move towards next position {} meters. {} meters_available, {}m by pokemon!".format(
                        str(actual_meters), str(available_mobility), str(m_to_move)))
                    player_pos = move_towards(player_pos, next_pos, actual_meters)

                if self.travel_time.must_gmo():
                    await self.worker.do_get_map_objects(player_pos)

                self.processed_encounters.add(encounter_id)  # leaks memory. fix todo
                self.worker.log.info(u"Catching {} because catch_all={} unseen={} candy_catch={} candy_12_catch={}".format(
                    pokemon_name(pokemon_id), str(catch_condition.catch_anything), str(unseen_catch), str(candy_catch),
                    str(candy_12_catch)))
                caught = await self.catch_it(player_pos, to_catch, fast=True)
                if caught:
                    self.caught_pokemon_ids.add(pokemon_id)
                    if isinstance(caught, numbers.Number):
                        all_caught[caught] = pokemon_id
                    else:
                        self.worker.log.warning("Did not caEtch because {}".format(str(caught)))
            else:
                self.worker.log.info(u"{} {} will not catch, is_catch_anything={}, is_unseen_catch={}, is_candy_catch={}, is_candy12_catch={}".format(str(pokemon_name(pokemon_id)), str(encounter_id), str(catch_condition.catch_anything), str(unseen_catch), str(candy_catch), str(candy_12_catch)))
            del catch_list[0]

        self.pokemon_caught += len(all_caught)
        self.process_evolve_transfer_list(all_caught)

        return player_pos

    def is_encountered_previously(self, encounter_id):
        return encounter_id in self.processed_encounters

    def synchronize_pokemon_inventory(self):
        discard_all_pokemon(self.worker)  # really simple algo :)

    def is_within_catch_limit(self):
        return self.pokemon_caught < self.catch_limit

    def evolve_map_element(self):
        return next((key for key in self.evolve_map if len(self.evolve_map[key]) > 0), None)

    def can_start_evolving(self):
        return self.num_evolve_candidates() > self.evolve_requirement

    def num_evolve_candidates(self):
        return sum(len(v) for v in itervalues(self.evolve_map))

    async def do_transfers(self):
        filtered = [x for x in self.transfers if x > 0]
        if len(filtered) > 0:
            await self.worker.do_transfer_pokemon(filtered)
        i = len(filtered)
        self.transfers = []
        return i

    async def do_bulk_transfers(self):
        if len(self.transfers) > 40:
            await self.do_transfers()

    async def evolve_one(self, candy, fast):
        if not self.evolve_map_element():
            return

        pokemon_id, pids = self.evolve_map.popitem()
        if len(pids) > 0:
            pid = pids[0]
            del pids[0]
            to_transfer = await self.do_evolve(candy, pid, pokemon_id, self.worker, fast)
            if to_transfer > 0:
                self.transfers.append(to_transfer)
                self.evolves += 1
            if len(pids) > 0:
                self.evolve_map[pokemon_id] = pids

    def process_evolve_transfer_list(self, caught):
        for pid, pokemon_id in caught.items():
            self.process_evolve_transfer_item(pid, pokemon_id)

    def process_evolve_transfer_item(self, pid, pokemon_id):
        candy_ = self.worker.account_info()["candy"]
        candy = candy_.get(pokemon_id, 0)
        current_items = self.evolve_map.get(pokemon_id, [])
        next_candy = len(current_items) + 1
        if pokemon_id in self.candy12_evolvable and candy >= (11 * next_candy + 1):
            current_items.append(pid)
            self.evolve_map[pokemon_id] = current_items
        elif pokemon_id in self.candy25_evolvable and candy >= (24 * next_candy + 1):
            current_items.append(pid)
            self.evolve_map[pokemon_id] = current_items
        elif pokemon_id in self.candy50 and candy >= (49 * next_candy) + 1:
            current_items.append(pid)
            self.evolve_map[pokemon_id] = current_items
        else:
            self.transfers.append(pid)

    async def do_evolve_transfer(self, worker, caught):
        this_evolves = 0
        candy_ = worker.account_info()["candy"]
        transfers = []
        for pid, pokemon_id in caught.items():
            candy = candy_.get(pokemon_id, 0)
            self.worker.log.info(u"{} candy availble for {}".format(str(candy), str(pokemon_id)))
            if pokemon_id in self.candy12 and candy >= 12:
                this_evolves += self.do_evolve(candy_, pid, pokemon_id, self.worker, self.fast)
            elif pokemon_id in self.candy25 and candy >= 25:
                this_evolves += self.do_evolve(candy_, pid, pokemon_id, self.worker, self.fast)
            elif pokemon_id in self.candy50 and candy >= 50:
                this_evolves += self.do_evolve(candy_, pid, pokemon_id, self.worker, self.fast)
            else:
                transfers.append(pid)
        await self.do_transfers()
        return this_evolves

    @staticmethod
    async def do_evolve(candy_, pid, pokemon_id, worker, fast):
        evo = await worker.do_evolve_pokemon(pid)
        candy = candy_.get(pokemon_id, 0)
        if evo.result != 1:
            worker.log.warning(
                u"Evolve status {}, {}({}) candy post-evolve {}".format(str(evo.result), pokemon_name(pokemon_id),
                                                                        str(pokemon_id), str(candy)))
        worker.log.info("Enqueing evolved {} for transfer, {} candy post-evolve {}".format(evo.evolved_pokemon_data.id,
                                                                                    pokemon_name(pokemon_id),
                                                                                    str(candy)))
        if not fast:
            await asyncio.sleep(17)
        return evo.evolved_pokemon_data.id

    async def catch_it(self, pos, to_catch, fast=False):
        encounter_id = to_catch.encounter_id
        spawn_point_id = to_catch.spawn_point_id
        pokemon_id = to_catch.pokemon_id
        self.worker.add_log(pokemon_name(pokemon_id))
        encounter_response = await self.worker.do_encounter_pokemon(encounter_id, spawn_point_id, pos)
        probability = EncounterPokemon(encounter_response, encounter_id).probability()
        is_vip = pokemon_id in self.candy12 or pokemon_id in self.candy25
        if probability and len([x for x in probability.capture_probability if x > 0.40]) > 0:
            caught = await beh_catch_encountered_pokemon(self.worker, pos, encounter_id, spawn_point_id, probability,
                                                   pokemon_id, is_vip, fast)
            return caught
        else:
            if probability:
                self.worker.log.info(u"Encounter {} is too hard to catch {}, skipping".format(str(encounter_id), str(
                    probability.capture_probability)))
            else:
                self.worker.log.info(u"Encounter {} failed, skipping".format(str(encounter_id)))

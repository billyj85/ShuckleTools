# -*- coding: utf-8 -*-
import asyncio
import logging
import time
from datetime import datetime as dt
from datetime import timedelta
from random import random, randrange, uniform

CATCH_STATUS_SUCCESS = 1
CATCH_STATUS_FAILED = 2
CATCH_STATUS_VANISHED = 3
CATCH_STATUS_MISSED = 4

ENCOUNTER_STATUS_SUCCESS = 1
ENCOUNTER_STATUS_NOT_IN_RANGE = 5
ENCOUNTER_STATUS_POKEMON_INVENTORY_FULL = 7
INCENSE_ENCOUNTER_AVAILABLE = 1
INCENSE_ENCOUNTER_NOT_AVAILABLE = 2

ITEM_POKEBALL = 1
ITEM_GREATBALL = 2
ITEM_ULTRABALL = 3
ITEM_RAZZBERRY = 701
ITEM_PINAPBERRY = 705

DEFAULT_UNSEEN_AS_VIP = True


def default_catch_rate_by_ball():
    return {ITEM_POKEBALL: 0.3, ITEM_GREATBALL: 0.5, ITEM_ULTRABALL: 0.7}

LOGIC_TO_FUNCTION = {
    'or': lambda x, y, z: x or y or z,
    'and': lambda x, y, z: x and y and z,
    'orand': lambda x, y, z: x or y and z,
    'andor': lambda x, y, z: x and y or z
}

log = logging.getLogger(__name__)


DEBUG_ON = False


class PokemonCatchWorker:
    def __init__(self, position, spawn_point_id, pogoservice, fast):
        self.position = position
        self.pogoservice = pogoservice
        self.spawn_point_guid = spawn_point_id
        self.response_key = ''
        self.response_status_key = ''
        self.rest_completed = False
        self.caught_last_24 = 0
        self.softban = False
        self.fast = fast

        # Config
        self.consecutive_vanishes_so_far = 0
        self.min_ultraball_to_keep = 10
        self.berry_threshold = 0.35
        self.vip_berry_threshold = 0.9
        self.treat_unseen_as_vip = DEFAULT_UNSEEN_AS_VIP
        self.daily_catch_limit = 800
        self.use_pinap_on_vip = False
        self.pinap_on_level_below = 0
        self.pinap_operator = "or"
        self.pinap_ignore_threshold = False

        self.vanish_settings = {}
        self.consecutive_vanish_limit = 10
        self.rest_duration_min = getSeconds("02:00:00")
        self.rest_duration_max = getSeconds("04:00:00")

        self.catch_throw_parameters = {}
        self.catch_throw_parameters_spin_success_rate = 0.6
        self.catch_throw_parameters_excellent_rate = 0.1
        self.catch_throw_parameters_great_rate = 0.5
        self.catch_throw_parameters_nice_rate = 0.3
        self.catch_throw_parameters_normal_rate = 0.1
        self.catch_throw_parameters_hit_rate = 0.95

        self.catchsim_config = {}
        self.catchsim_catch_wait_min = 2
        self.catchsim_catch_wait_max = 2.1
        self.catchsim_flee_count = 3
        self.catchsim_flee_duration = 2
        self.catchsim_berry_wait_min = 0,5
        self.catchsim_berry_wait_max = 2.1
        self.catchsim_changeball_wait_min = 0.3  # 2.0
        self.catchsim_changeball_wait_max = 0.3  # 2.1
        self.catchsim_newtodex_wait_min = 20
        self.catchsim_newtodex_wait_max = 21

    def _pct(self, rate_by_ball):
        return '{0:.2f}'.format(rate_by_ball * 100)

    async def _use_berry(self, berry_id, berry_count, encounter_id, catch_rate_by_ball, current_ball):
        # Delay to simulate selecting berry
        if not self.fast:
            await action_delay(self.catchsim_berry_wait_min, self.catchsim_berry_wait_max)
        new_catch_rate_by_ball = []

        response_dict = await self.pogoservice.do_use_item_encounter(
            item_id=berry_id,
            encounter_id=encounter_id,
            spawn_point_guid=self.spawn_point_guid
        )
        responses = response_dict

        # update catch rates using multiplier
        if responses['USE_ITEM_ENCOUNTER'].HasField('capture_probability'):
            for rate in catch_rate_by_ball:
                new_catch_rate_by_ball.append(float(
                    responses['USE_ITEM_ENCOUNTER'].capture_probability.capture_probability[
                        current_ball - 1]))
        # softban?
        else:
            new_catch_rate_by_ball = catch_rate_by_ball
            self.softban = True

        return new_catch_rate_by_ball

    async def do_catch(self, encounter_id, catch_rate_by_ball, inventory, is_vip=False):
        berry_id = ITEM_PINAPBERRY
        # berry_id = ITEM_RAZZBERRY

        maximum_ball = ITEM_ULTRABALL
        berry_count = inventory.get(berry_id, 0)

        ball_count = {}
        for ball_id in [ITEM_POKEBALL, ITEM_GREATBALL, ITEM_ULTRABALL]:
            ball_count[ball_id] = inventory.get(ball_id, 0)

        ideal_catch_rate_before_throw = self.vip_berry_threshold if is_vip else self.berry_threshold

        used_berry = False
        original_catch_rate_by_ball = catch_rate_by_ball

        while True:
            # find lowest available ball
            current_ball = ITEM_POKEBALL
            while ball_count[current_ball] == 0 and current_ball < maximum_ball:
                current_ball += 1
            if ball_count[current_ball] == 0:
                return WorkerResult.ERROR_NO_BALLS

            # check future ball count
            num_next_balls = 0
            next_ball = current_ball
            while next_ball < maximum_ball:
                next_ball += 1
                num_next_balls += ball_count[next_ball]

            # If out of pinap berry , use razz berry
            if berry_count == 0 and berry_id == ITEM_PINAPBERRY:
                berry_id = ITEM_RAZZBERRY
                ideal_catch_rate_before_throw = self.vip_berry_threshold if is_vip else self.berry_threshold
                berry_count = inventory.get(berry_id, 0)

            # check if we've got berries to spare
            try:
                berries_to_spare = berry_count > 0 if is_vip else berry_count > num_next_balls + 30
            except TypeError:
                log.info("{} {}".format(str(berry_count), str(num_next_balls)))
                raise

            changed_ball = False

            # use a berry if we are under our ideal rate and have berries to spare
            if ((catch_rate_by_ball[current_ball] < ideal_catch_rate_before_throw and berries_to_spare) or (is_vip and berry_count > 0)) and not used_berry:
                new_catch_rate_by_ball = await self._use_berry(berry_id, berry_count, encounter_id, catch_rate_by_ball,
                                                         current_ball)
                if new_catch_rate_by_ball != catch_rate_by_ball:
                    catch_rate_by_ball = new_catch_rate_by_ball
                    inventory[berry_id] = inventory.get(berry_id) - 1
                    berry_count -= 1
                    used_berry = True

            # pick the best ball to catch with
            best_ball = current_ball
            while best_ball < maximum_ball:
                best_ball += 1
                if catch_rate_by_ball[current_ball] < ideal_catch_rate_before_throw and ball_count[best_ball] > 0:
                    # if current ball chance to catch is under our ideal rate, and player has better ball - then use it
                    current_ball = best_ball
                    changed_ball = True

            # if the rate is still low and we didn't throw a berry before, throw one
            if ((catch_rate_by_ball[current_ball] < ideal_catch_rate_before_throw and berry_count > 0) or (
                is_vip and berry_count > 0)) and not used_berry:
                new_catch_rate_by_ball = await self._use_berry(berry_id, berry_count, encounter_id, catch_rate_by_ball,
                                                         current_ball)
                if new_catch_rate_by_ball != catch_rate_by_ball:
                    catch_rate_by_ball = new_catch_rate_by_ball
                    inventory[berry_id] = inventory.get(berry_id) - 1
                    berry_count -= 1
                    used_berry = True

            # If we change ball then wait to simulate user selecting it
            if changed_ball and not self.fast:
                await action_delay(self.catchsim_changeball_wait_min, self.catchsim_changeball_wait_max)

            # Randomize the quality of the throw
            # Default structure
            throw_parameters = {'normalized_reticle_size': 1.950,
                                'spin_modifier': 1.0,
                                'normalized_hit_position': 1.0,
                                'throw_type_label': 'Excellent'}
            self.generate_spin_parameter(throw_parameters)
            self.generate_throw_quality_parameters(throw_parameters)

            # try to catch pokemon!
            ball_count[current_ball] -= 1
            inventory[current_ball] = inventory.get(current_ball) - 1

            # Take some time to throw the ball from config options
            if not self.fast:
                await action_delay(self.catchsim_catch_wait_min, self.catchsim_catch_wait_max)

            hit_pokemon = 1
            if random() >= self.catch_throw_parameters_hit_rate and not is_vip:
                hit_pokemon = 0

            response_dict = await self.pogoservice.do_catch_pokemon(
                encounter_id=encounter_id,
                pokeball=current_ball,
                normalized_reticle_size=throw_parameters['normalized_reticle_size'],
                spawn_point_id=self.spawn_point_guid,
                hit_pokemon=hit_pokemon,
                spin_modifier=throw_parameters['spin_modifier'],
                normalized_hit_position=throw_parameters['normalized_hit_position']
            )

            try:
                catch_pokemon_status = response_dict['CATCH_POKEMON'].status
            except KeyError:
                break

            # retry failed pokemon
            if catch_pokemon_status == CATCH_STATUS_FAILED:
                used_berry = False
                catch_rate_by_ball = original_catch_rate_by_ball

                # sleep according to flee_count and flee_duration config settings
                # randomly chooses a number of times to 'show' wobble animation between 1 and flee_count
                # multiplies this by flee_duration to get total sleep
                # if self.catchsim_flee_count:
                #    duration = (randrange(self.catchsim_flee_count) + 1) * self.catchsim_flee_duration
                #    log.info("Catch failed, sleeping {}".format(str(duration)))
                #    sleep(duration)

                continue

            # abandon if pokemon vanished
            elif catch_pokemon_status == CATCH_STATUS_VANISHED:

                self.consecutive_vanishes_so_far += 1

                if self.rest_completed is False and self.consecutive_vanishes_so_far >= self.consecutive_vanish_limit:
                    raise ProbableSoftBan

                if self._pct(catch_rate_by_ball[current_ball]) == 100:
                    raise SoftBan

                return
            # pokemon caught!
            elif catch_pokemon_status == CATCH_STATUS_SUCCESS:
                if self.rest_completed:
                    self.rest_completed = False
                pokemon_unique_id = response_dict['CATCH_POKEMON'].captured_pokemon_id
                return pokemon_unique_id
            elif catch_pokemon_status == CATCH_STATUS_MISSED:
                # Take some time to throw the ball from config options
                if not self.fast:
                    await action_delay(self.catchsim_catch_wait_min, self.catchsim_catch_wait_max)
                continue

            break

    def extract_award(self, awards):
        return sum(awards['xp']), sum(awards['candy']), sum(awards['stardust'])

    def generate_spin_parameter(self, throw_parameters):
        spin_success_rate = self.catch_throw_parameters_spin_success_rate
        if random() <= spin_success_rate:
            throw_parameters['spin_modifier'] = 0.5 + 0.5 * random()
            throw_parameters['spin_label'] = ' Curveball'
        else:
            throw_parameters['spin_modifier'] = 0.499 * random()
            throw_parameters['spin_label'] = ''

    def generate_throw_quality_parameters(self, throw_parameters):
        throw_excellent_chance = self.catch_throw_parameters_excellent_rate
        throw_great_chance = self.catch_throw_parameters_great_rate
        throw_nice_chance = self.catch_throw_parameters_nice_rate
        throw_normal_throw_chance = self.catch_throw_parameters_normal_rate

        # Total every chance types, pick a random number in the range and check what type of throw we got
        total_chances = throw_excellent_chance + throw_great_chance \
                        + throw_nice_chance + throw_normal_throw_chance

        random_throw = random() * total_chances

        if True and random_throw <= throw_excellent_chance:
            throw_parameters['normalized_reticle_size'] = 1.70 + 0.25 * random()
            throw_parameters['normalized_hit_position'] = 1.0
            throw_parameters['throw_type_label'] = 'Excellent'
            return

        random_throw -= throw_excellent_chance
        if random_throw <= throw_great_chance:
            throw_parameters['normalized_reticle_size'] = 1.30 + 0.399 * random()
            throw_parameters['normalized_hit_position'] = 1.0
            throw_parameters['throw_type_label'] = 'Great'
            return

        random_throw -= throw_great_chance
        if random_throw <= throw_nice_chance:
            throw_parameters['normalized_reticle_size'] = 1.00 + 0.299 * random()
            throw_parameters['normalized_hit_position'] = 1.0
            throw_parameters['throw_type_label'] = 'Nice'
            return

        # Not a any kind of special throw, let's throw a normal one
        # Here the reticle size doesn't matter, we scored out of it
        throw_parameters['normalized_reticle_size'] = 1.25 + 0.70 * random()
        throw_parameters['normalized_hit_position'] = 0.0
        throw_parameters['throw_type_label'] = 'OK'


async def action_delay(low, high):
    # Waits for random number of seconds between low & high numbers
    longNum = uniform(low, high)
    shortNum = float("{0:.2f}".format(longNum))
    await asyncio.sleep(shortNum)


async def sleep(seconds, delta=0.3):
    await asyncio.sleep(jitter(seconds, delta))


def jitter(value, delta=0.3):
    dajitter = delta * value
    return uniform(value - dajitter, value + dajitter)


class WorkerResult(object):
    RUNNING = 'RUNNING'
    SUCCESS = 'SUCCESS'
    ERROR = 'ERROR'
    ERROR_NO_BALLS = 'ERROR_NO_BALLS'



def getSeconds(strTime):
    '''
    Return the duration in seconds of a time string
    :param strTime: string time of format %H:%M:%S
    '''
    try:
        x = dt.strptime(strTime, '%H:%M:%S')
        seconds = int(timedelta(hours=x.hour, minutes=x.minute, seconds=x.second).total_seconds())
    except ValueError:
        seconds = 0

    if seconds < 0:
        seconds = 0

    return seconds


class SoftBan:
    def __init__(self):
        pass


class ProbableSoftBan:
    def __init__(self):
        pass

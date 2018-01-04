import logging

log = logging.getLogger(__name__)

error_codes = {
    0: 'UNSET',
    1: 'SUCCESS',
    2: 'POKEMON_DEPLOYED',
    3: 'FAILED',
    4: 'ERROR_POKEMON_IS_EGG',
    5: 'ERROR_POKEMON_IS_BUDDY'
}


class ReleasePokemon:

    def __init__(self, response):
        self.response = response

    def ok(self):
        result = self.response['RELEASE_POKEMON'].result
        if result != 1:
            log.error('Error while transfer pokemon: {}'.format(error_codes[result]))
            return False

        return True


class CodenameResult:
    codename_result_error_codes= {
        0: 'UNSET',
        1: 'SUCCESS',
        2: 'CODENAME_NOT_AVAILABLE',
        3: 'CODENAME_NOT_VALID',
        4: 'CURRENT_OWNER',
        5: 'CODENAME_CHANGE_NOT_ALLOWED'
    }

    def __init__(self, response):
        self.response = response

    def ok(self):
        result = self.response.get("CLAIM_CODENAME", {})
        status = result.status
        if status == 1:
            return True
        log.error('Error while renaming player: {}'.format(self.codename_result_error_codes[status]))
        return False


class EncounterPokemon:
    encounter_error_codes = {
        0: 'ENCOUNTER_ERROR',
        1: 'ENCOUNTER_SUCCESS',
        2: 'ENCOUNTER_NOT_FOUND',
        3: 'ENCOUNTER_CLOSED',
        4: 'ENCOUNTER_POKEMON_FLED',
        5: 'ENCOUNTER_NOT_IN_RANGE',
        6: 'ENCOUNTER_ALREADY_HAPPENED',
        7: 'POKEMON_INVENTORY_FULL'
    }

    def __init__(self, response, encounter_id):
        self.expected_encounter_id = encounter_id
        self.response = response

    def probability(self):
        encounter = self.wild_pokemon()
        status = encounter.status
        if status != 1:
            if status == 4:
                log.info('Pokemon fled from encounter')
            else:
                log.error('Error while encountering pokemon: {}'.format(self.encounter_error_codes[status]))
            return
        resp = encounter.capture_probability
        return resp

    def contains_expected_encounter(self):
        wild = self.wild_pokemon().wild_pokemon
        actual_encounter_id = wild.encounter_id
        return self.expected_encounter_id == actual_encounter_id

    def wild_pokemon(self):
        return self.response.get("ENCOUNTER", {})



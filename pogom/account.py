#!/usr/bin/python
# -*- coding: utf-8 -*-
import asyncio
import logging
import random
import time

from aiopogo.exceptions import AuthException, NianticIPBannedException, BadRPCException

from .apiRequests import (send_generic_request, AccountBannedException,
                          req_call_with_retries)

class OutOfAccountsException:
    """We have run out of accounts and cannot serve more requests"""

    def __init__(self):
        pass


class ForcedApiException(Exception):
    """The API has been forced and we're stopping"""

    def __init__(self):
        pass



class TooManyLoginAttempts(Exception):
    pass


class LoginSequenceFail(Exception):
    pass

class BlindAcount(Exception):
    def __init__(self, account):
        self.account = account


def auth_provider(api):
    try:
        return api._auth_provider
    except AttributeError:
        return api.auth_provider

def is_login_required(api):
    provider = auth_provider(api)
    if provider and provider._access_token:
        remaining_time = provider._access_token_expiry - time.time()

        if remaining_time > 60:
            logging.getLogger(__name__).debug('Credentials remain valid for another %f seconds.', remaining_time)
            return False
    return True



def getproxy(api):
    return api.proxy

def setproxy(api,proxy):
    api.proxy =proxy

# Use API to check the login status, and retry the login if possible.
async def check_login(args, account, api, proxy_url, proceed):
    # Logged in? Enough time left? Cool!
    if not is_login_required(api):
        return True

    log = logging.LoggerAdapter(logging.getLogger(__name__), {'worker_name': account['username']})

    # Try to login. Repeat a few times, but don't get stuck here.
    num_tries = 0

    #if is_forced_version(proxy_url):
    #    raise ForcedApiException()

    current_proxy = getproxy(api)
    if proxy_url:
        log.info("Using PTC proxy {} for login".format(str(proxy_url)))
        api.proxy = proxy_url
    try:
        # One initial try + login_retries.
        while num_tries < (args.login_retries + 1):
            try:
                await api.set_authentication(
                    provider=account['auth_service'],
                    username=account['username'],
                    password=account['password'])
                # Success!
                break
            except AuthException:
                num_tries += 1
                log.warning(
                    ('Failed to login to Pokemon Go with account %s and proxy %s. ' +
                     'Trying again in %g seconds.'),
                    account['username'], str(proxy_url), args.login_delay)
                await asyncio.sleep(args.login_delay)

        if num_tries > args.login_retries:
            log.error(
                ('Failed to login to Pokemon Go with account %s in ' +
                 '%d tries with proxy %s. Giving up.'),
                account['username'], num_tries, str(proxy_url))
            raise TooManyLoginAttempts('Exceeded login attempts.')
    finally:
        setproxy(api, current_proxy)

    await asyncio.sleep(random.uniform(2, 4))

    # Simulate login sequence.
    try:
        return await rpc_login_sequence(args, api, account, proceed)
    except NianticIPBannedException:
        log.info("IP seems to be NIANTIC banned {}".format(str(current_proxy)))
        raise



# Simulate real app via login sequence.
async def rpc_login_sequence(args, api, account, proceed):
    total_req = 0
    app_version = 8700

    log = logging.LoggerAdapter(logging.getLogger(__name__), {'worker_name': account['username']})

    # 1 - Make an empty request to mimick real app behavior.
    log.debug('Starting RPC login sequence...')

    try:
        req = api.create_request()
        await req_call_with_retries(req, log)

        total_req += 1
        await asyncio.sleep(random.uniform(.43, .97))
    except Exception as e:
        log.exception('Login for account %s failed.'
                      + ' Exception in call request: %s.',
                      account['username'],
                      e)
        raise LoginSequenceFail('Failed during empty request in login'
                                + ' sequence for account {}.'.format(
                                    account['username']))

    # 2 - Get player information.
    log.debug('Fetching player information...')

    try:
        req = api.create_request()
        req.get_player(player_locale=args.player_locale)
        resp = await req_call_with_retries(req, log)
        parse_get_player(account, resp)
        warning_ = account['warning']

        total_req += 1
        await asyncio.sleep(random.uniform(.53, 1.1))
        if warning_:
            log.warning('Account %s has received a warning.',
                        account['username'])
    except Exception as e:
        log.exception('Login for account %s failed. Exception in ' +
                      'player request: %s.',
                      account['username'],
                      e)
        raise LoginSequenceFail('Failed while retrieving player information in'
                                + ' login sequence for account {}.'.format(
                                    account['username']))

    # 3 - Get remote config version.
    log.debug('Downloading remote config version...')
    old_config = account.get('remote_config', {})

    try:
        req = api.create_request()
        req.download_remote_config_version(platform=1,
                                           app_version=app_version)
        await send_generic_request(req, account, settings=True, buddy=False,
                             inbox=False)

        total_req += 1
        await asyncio.sleep(random.uniform(.53, 1.1))
    except BadRPCException as bre:
        raise AccountBannedException
    except AccountBannedException as abe:
        raise abe
    except Exception as e:
        log.exception('Error while downloading remote config: %s.', e)
        raise LoginSequenceFail('Failed while getting remote config version in'
                                + ' login sequence for account {}.'.format(
                                    account['username']))

    if not await proceed(account):
        log.info('Told not to proceed with login sequence for %s', account['username'])
        return False

    # 4 - Get asset digest.
    log.debug('Fetching asset digest...')
    config = account.get('remote_config', {})

    if config.get('asset_time', 0) > old_config.get('asset_time', 0):
        i = random.randint(0, 3)
        req_count = 0
        result = 2
        page_offset = 0
        page_timestamp = 0

        await asyncio.sleep(random.uniform(.7, 1.2))

        while result == 2:
            req = api.create_request()
            req.get_asset_digest(
                platform=1,
                app_version=app_version,
                paginate=True,
                page_offset=page_offset,
                page_timestamp=page_timestamp)
            resp = await send_generic_request(req, account, settings=True,
                                        buddy=False, inbox=False)

            req_count += 1
            total_req += 1

            if i > 2:
                await asyncio.sleep(random.uniform(1.4, 1.6))
                i = 0
            else:
                i += 1
                await asyncio.sleep(random.uniform(.3, .5))

            try:
                # Re-use variable name. Also helps GC.
                resp = resp['GET_ASSET_DIGEST']
            except KeyError:
                break

            result = resp.result
            page_offset = resp.page_offset
            page_timestamp = resp.timestamp_ms
            log.debug('Completed %d requests to get asset digest.',
                      req_count)

    # 5 - Get item templates.
    log.debug('Fetching item templates...')

    if config.get('template_time', 0) > old_config.get('template_time', 0):
        i = random.randint(0, 3)
        req_count = 0
        result = 2
        page_offset = 0
        page_timestamp = 0

        while result == 2:
            req = api.create_request()
            req.download_item_templates(
                paginate=True,
                page_offset=page_offset,
                page_timestamp=page_timestamp)
            resp = await send_generic_request(req, account, settings=True,
                                        buddy=False, inbox=False)

            req_count += 1
            total_req += 1

            if i > 2:
                await asyncio.sleep(random.uniform(1.4, 1.6))
                i = 0
            else:
                i += 1
                await asyncio.sleep(random.uniform(.25, .5))

            try:
                # Re-use variable name. Also helps GC.
                resp = resp['responses']['DOWNLOAD_ITEM_TEMPLATES']
            except KeyError:
                break

            result = resp.result
            page_offset = resp.page_offset
            page_timestamp = resp.timestamp_ms
            log.debug('Completed %d requests to download'
                      + ' item templates.', req_count)

    # Check tutorial completion.
    if not all(x in account['tutorials'] for x in (0, 1, 3, 4, 7)):
        log.info('Completing tutorial steps for %s.', account['username'])
        await complete_tutorial(args, api, account, log)
    else:
        log.debug('Account %s already did the tutorials.', account['username'])
        # 6 - Get player profile.
        log.debug('Fetching player profile...')
        try:
            req = api.create_request()
            req.get_player_profile()
            await send_generic_request(req, account, settings=True, inbox=False)
            total_req += 1
            await asyncio.sleep(random.uniform(.2, .3))
        except Exception as e:
            log.exception('Login for account %s failed. Exception occurred ' +
                          'while fetching player profile: %s.',
                          account['username'],
                          e)
            raise LoginSequenceFail('Failed while getting player profile in'
                                    + ' login sequence for account {}.'.format(
                                        account['username']))

    log.debug('Retrieving Store Items...')
    try:  # 7 - Make an empty request to retrieve store items.
        req = api.create_request()
        req.get_store_items()
        await req_call_with_retries(req, log)

        total_req += 1
        await asyncio.sleep(random.uniform(.6, 1.1))
    except Exception as e:
        log.exception('Login for account %s failed. Exception in ' +
                      'retrieving Store Items: %s.', account['username'],
                      e)
        raise LoginSequenceFail('Failed during login sequence.')

    # 8 - Check if there are level up rewards to claim.
    log.debug('Checking if there are level up rewards to claim...')

    try:
        req = api.create_request()
        req.level_up_rewards(level=account['level'])
        await send_generic_request(req, account, settings=True)

        total_req += 1
        await asyncio.sleep(random.uniform(.45, .7))
    except Exception as e:
        log.exception('Login for account %s failed. Exception occurred ' +
                      'while fetching level-up rewards: %s.',
                      account['username'],
                      e)
        raise LoginSequenceFail('Failed while getting level-up rewards in'
                                + ' login sequence for account {}.'.format(
                                    account['username']))

    log.info('RPC login sequence for account %s successful with %s requests.',
             account['username'],
             total_req)

    await asyncio.sleep(random.uniform(3, 5))

    if account['buddy'] == 0 and len(account['pokemons']) > 0:
        poke_id = random.choice(list(account['pokemons'].keys()))
        req = api.create_request()
        req.set_buddy_pokemon(pokemon_id=poke_id)
        log.debug('Setting buddy pokemon for %s.', account['username'])
        await send_generic_request(req, account)

        await asyncio.sleep(random.uniform(10, 20))
    return True


# Complete minimal tutorial steps.
# API argument needs to be a logged in API instance.
# TODO: Check if game client bundles these requests, or does them separately.
async def complete_tutorial(args, api, account, log):
    tutorial_state = account['tutorials']
    if 0 not in tutorial_state:
        await asyncio.sleep(random.uniform(1, 5))
        req = api.create_request()
        req.mark_tutorial_complete(tutorials_completed=(0,))
        log.debug('Sending 0 tutorials_completed for %s.', account['username'])
        await send_generic_request(req, account, buddy=False, inbox=False)

        await asyncio.sleep(random.uniform(0.5, 0.6))
        req = api.create_request()
        req.get_player(player_locale=args.player_locale)
        await send_generic_request(req, account, buddy=False, inbox=False)

    if 1 not in tutorial_state:
        await asyncio.sleep(random.uniform(5, 12))
        req = api.create_request()
        req.set_avatar(player_avatar={
            'hair': random.randint(1, 5),
            'shirt': random.randint(1, 3),
            'pants': random.randint(1, 2),
            'shoes': random.randint(1, 6),
            'avatar': random.randint(0, 1),
            'eyes': random.randint(1, 4),
            'backpack': random.randint(1, 5)
        })
        log.debug('Sending set random player character request for %s.',
                  account['username'])
        await send_generic_request(req, account, buddy=False, inbox=False)

        await asyncio.sleep(random.uniform(0.3, 0.5))
        req = api.create_request()
        req.mark_tutorial_complete(tutorials_completed=(1,))
        log.debug('Sending 1 tutorials_completed for %s.', account['username'])
        await send_generic_request(req, account, buddy=False, inbox=False)

        await asyncio.sleep(random.uniform(0.5, 0.6))
        req = api.create_request()
        req.get_player_profile()
        log.debug('Fetching player profile for %s...', account['username'])
        await send_generic_request(req, account, inbox=False)

    if 3 not in tutorial_state:
        await asyncio.sleep(random.uniform(1, 1.5))
        req = api.create_request()
        req.get_download_urls(asset_id=[
            '1a3c2816-65fa-4b97-90eb-0b301c064b7a/1477084786906000',
            'aa8f7687-a022-4773-b900-3a8c170e9aea/1477084794890000',
            'e89109b0-9a54-40fe-8431-12f7826c8194/1477084802881000'])
        log.debug('Grabbing some game assets.')
        await send_generic_request(req, account, inbox=False)

        await asyncio.sleep(random.uniform(6, 13))
        req = api.create_request()
        starter = random.choice((1, 4, 7))
        req.encounter_tutorial_complete(pokemon_id=starter)
        log.debug('Catching the starter for %s.', account['username'])
        await send_generic_request(req, account, inbox=False)

        await asyncio.sleep(random.uniform(0.5, 0.6))
        req = api.create_request()
        req.get_player(player_locale=args.player_locale)
        await send_generic_request(req, account, inbox=False)

    if 4 not in tutorial_state:
        await asyncio.sleep(random.uniform(5, 12))
        req = api.create_request()
        req.claim_codename(codename=account['username'])
        log.debug('Claiming codename for %s.', account['username'])
        await send_generic_request(req, account, inbox=False)

        await asyncio.sleep(0.1)
        req = api.create_request()
        req.get_player(player_locale=args.player_locale)
        await send_generic_request(req, account, inbox=False)

        await asyncio.sleep(random.uniform(1, 1.3))
        req = api.create_request()
        req.mark_tutorial_complete(tutorials_completed=(4,))
        log.debug('Sending 4 tutorials_completed for %s.', account['username'])
        await send_generic_request(req, account, inbox=False)

    if 7 not in tutorial_state:
        await asyncio.sleep(random.uniform(4, 10))
        req = api.create_request()
        req.mark_tutorial_complete(tutorials_completed=(7,))
        log.debug('Sending 7 tutorials_completed for %s.', account['username'])
        await send_generic_request(req, account, inbox=False)

    # Sleeping before we start scanning to avoid Niantic throttling.
    log.debug('And %s is done. Wait for a second, to avoid throttle.',
              account['username'])
    await asyncio.sleep(random.uniform(2, 4))
    return True


def parse_get_player(account, api_response):
    if 'GET_PLAYER' in api_response:
        player_ = api_response['GET_PLAYER']
        player_data = player_.player_data

        account['warning'] = player_.warn
        account['tutorials'] = player_data.tutorial_state
        account['buddy'] = player_data.buddy_pokemon.id
        account['codename'] = player_data.username
        account['remaining_codename_claims'] = player_data.remaining_codename_claims
        account['team'] = player_data.team



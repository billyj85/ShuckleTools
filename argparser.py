import sys
import os
import unittest
from _signal import SIGINT

import configargparse
import logging
import re

from async_accountdbsql import set_account_db_args
from gymdbsql import set_gymdb_args
from pogom.apiRequests import set_goman_hash_endpoint
from pogom.proxy import check_proxies
from scannerutil import setup_logging, install_thread_excepthook

log = logging.getLogger(__name__)


def __parse_unicode(bytestring):
    decoded_string = bytestring.decode(sys.getfilesystemencoding())
    return decoded_string


def std_config(name):
    parser = std_pogo_api_config(name)
    parser.add_argument('--api-version', default='0.89.1',
                        help=('API version currently in use.'))
    parser.add_argument('-novc', '--no-version-check', action='store_true',
                        help='Disable API version check.',
                        default=False)
    parser.add_argument('-k', '--gmaps-key',
                        help='Google Maps Javascript API Key.',
                        required=False)
    parser.add_argument('-ra', '--reverse-accounts',
                        help='Reverse allocation order of accounts',
                        default=False
                        )
    parser.add_argument('-L', '--locale',
                        help=('Locale for Pokemon names (default: {}, check ' +
                              '{} for more).').format("en",
                                                      "static/dist/locales"),
                        default='en')
    parser.add_argument('-l', '--location', type=parse_unicode,
                        help='Location, can be an address or coordinates.')
    parser.add_argument('-px', '--proxy',
                        help='Proxy url (e.g. socks5://127.0.0.1:9050)',
                        action='append')
    parser.add_argument('-pxsc', '--proxy-skip-check',
                        help='Disable checking of proxies before start.',
                        action='store_true', default=False)
    parser.add_argument('-pxt', '--proxy-test-timeout',
                        help='Timeout settings for proxy checker in seconds.',
                        type=int, default=5)
    parser.add_argument('-pxc', '--proxy-test-concurrency',
                        help=('Async requests pool size.'), type=int,
                        default=0)
    parser.add_argument('-pxre', '--proxy-test-retries',
                        help=('Number of times to retry sending proxy ' +
                              'test requests on failure.'),
                        type=int, default=0)
    parser.add_argument('-pxbf', '--proxy-test-backoff-factor',
                        help=('Factor (in seconds) by which the delay ' +
                              'until next retry will increase.'),
                        type=float, default=0.25)
    parser.add_argument('-pxf', '--proxy-file',
                        help=('Load proxy list from text file (one proxy ' +
                              'per line), overrides -px/--proxy.'))
    parser.add_argument('-xx', '--login_retries',
                        help='Proxy url (e.g. socks5://127.0.0.1:9050)',
                        default=1,
                        action='append')
    parser.add_argument('-ld', '--login-delay',
                        help='Time delay between each login attempt.',
                        type=float, default=6)
    parser.add_argument('-sw', '--sweep-workers',
                        help='The number of scaners width',
                        type=int, default=100)
    parser.add_argument('-tut', '--complete-tutorial', action='store_true',
                        help=("Complete ToS and tutorial steps on accounts " +
                              "if they haven't already."),
                        default=True)
    return parser


def add_geofence(parser):
    parser.add_argument('-gf', '--geofence',
                        help='Fence file',
                        default=None)
    parser.add_argument('-fn', '--fencename',
                        help='Fence within file (or all fences if lef tout',
                        action='append', default=[])


def add_search_rest(parser):
    parser.add_argument('-asi', '--account-search-interval', type=int,
                        default=3600,
                        help=('Seconds for accounts to search before ' +
                              'switching to a new account. 0 to disable.'))
    parser.add_argument('-ari', '--account-rest-interval', type=int,
                        default=3600,
                        help=('Seconds for accounts to rest when they fail ' +
                              'or are switched out.'))


def add_use_account_db(parser):
    parser.add_argument('-uad', '--use-account-db',
                        help='Indicates if the application wil enter accounts into account database',
                        action='store_true', default=False)


def add_use_account_db_true(parser):
    parser.add_argument('-uad', '--use-account-db',
                        help='Indicates if the application wil enter accounts into account database',
                        action='store_true', default=True)


def add_system_id(parser):
    parser.add_argument('-system-id', '--system-id',
                        help='Define the name of the node that will be used to identify accounts in the account table',
                        default=None)


def add_threads_per_proxy(parser, ndefault=5):
    parser.add_argument('-t', '--threads-per-proxy',
                        help='threads-per-proxy',
                        type=int, default=ndefault)


def add_webhooks(parser):
    parser.add_argument('-wh', '--webhook',
                        help='Define URL(s) to POST webhook information to.',
                        default=None, dest='webhooks', action='append')
    parser.add_argument('-whr', '--wh-retries',
                        help=('Number of times to retry sending webhook ' +
                              'data on failure.'),
                        type=int, default=3)
    parser.add_argument('-wht', '--wh-timeout',
                        help='Timeout (in seconds) for webhook requests.',
                        type=float, default=1.0)
    parser.add_argument('-whbf', '--wh-backoff-factor',
                        help=('Factor (in seconds) by which the delay ' +
                              'until next retry will increase.'),
                        type=float, default=0.25)
    parser.add_argument('-whc', '--wh-concurrency',
                        help=('Async requests pool size.'), type=int,
                        default=25)
    parser.add_argument('--wh-threads',
                        help=('Number of webhook threads; increase if the ' +
                              'webhook queue falls behind.'),
                        type=int, default=1)
    parser.add_argument('-whlfu', '--wh-lfu-size',
                        help='Webhook LFU cache max size.', type=int,
                        default=2500)
    parser.add_argument('-wblk', '--webhook-blacklist',
                        action='append', default=[],
                        help=('List of Pokemon NOT to send to '
                              'webhooks. Specified as Pokemon ID.'))


def std_pogo_api_config(name):
    parser = basic_std_parser(name)
    parser.add_argument('-hk', '--hash-key', default=None, action='append',
                        help='Key for hash server. May be on the form http://endpoint/key')
    parser.add_argument('-ohk', '--overflow-hash-key', default=None,
                        help='Key for hash server to use when capacity on first is exceeded. May be on the form http://endpoint/key')
    parser.add_argument('-lhk', '--login-hash-key', default=None, action='append',
                        help='Key for hash server during login. May be on the form http://endpoint/key')
    parser.add_argument('-cs', '--captcha-solving',
                        help='Enables captcha solving.',
                        action='store_true', default=True)
    parser.add_argument('-mcd', '--manual-captcha-domain',
                        help='Domain to where captcha tokens will be sent.',
                        default="http://127.0.0.1:5000")
    parser.add_argument('-mcr', '--manual-captcha-refresh',
                        help='Time available before captcha page refreshes.',
                        type=int, default=30)
    parser.add_argument('-mct', '--manual-captcha-timeout',
                        help='Maximum time captchas will wait for manual ' +
                             'captcha solving. On timeout, if enabled, 2Captcha ' +
                             'will be used to solve captcha. Default is 0.',
                        type=int, default=0)
    parser.add_argument('-ck', '--captcha-key',
                        help='2Captcha API key.')
    parser.add_argument('-cds', '--captcha-dsk',
                        help='Pokemon Go captcha data-sitekey.',
                        default="6LeeTScTAAAAADqvhqVMhPpr_vB9D364Ia-1dSgK")
    parser.add_argument('-ac', '--accountcsv',
                        help=('Load accounts from CSV file containing ' +
                              '"auth_service,username,passwd" lines.'))
    return parser


def basic_std_parser(name):
    defaultconfigfiles = [name + ".ini"]
    if '-cf' not in sys.argv and '--config' not in sys.argv:
        defaultconfigfiles = [os.getenv(name.upper() + '_CONFIG',
                                        os.path.join(os.path.dirname(__file__),
                                                     name + '.ini'))]
    parser = configargparse.ArgParser(default_config_files=defaultconfigfiles,
                                      auto_env_var_prefix='PGO_')
    parser.add_argument('-cf', '--config',
                        is_config_file=True, help='Set configuration file')
    parser.add_argument('--db-type',
                        help='Type of database to be used (default: sqlite).',
                        default='sqlite')
    parser.add_argument('--db-name', help='Name of the database to be used.')
    parser.add_argument('--db-user', help='Username for the database.')
    parser.add_argument('--db-pass', help='Password for the database.')
    parser.add_argument('--db-host', help='IP or hostname for the database.')
    parser.add_argument(
        '--db-port', help='Port for the database.', type=int, default=3306)
    return parser





def setup_default_app(args, loop):
    def signal_handler():
        loop.stop()
        sys.exit(0)

    loop.add_signal_handler(SIGINT, signal_handler)
    setup_logging(args.system_id)
    logging.getLogger("pogoservice").setLevel(logging.DEBUG)
    logging.getLogger("pogoserv").setLevel(logging.DEBUG)
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    args.player_locale = {'country': 'DE', 'language': 'de', 'timezone': 'Europe/Berlin'}
    args.status_name = args.system_id
    setup_proxies(args)
    set_account_db_args(args, loop)
    set_gymdb_args(args)

    if "overflow_hash_key" in args and args.overflow_hash_key:
        set_goman_hash_endpoint(args.overflow_hash_key)
    install_thread_excepthook()
    # sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)


def setup_proxies(args):
    load_proxies(args)
    if "proxy" in args and args.proxy and not args.proxy_skip_check:
        fully_ok, ptc_banned_proxies, niantic_banned_proxies = check_proxies(args, args.proxy)
        args.proxy = fully_ok
        args.ptc_banned_proxy = ptc_banned_proxies
        args.niantic_banned_proxy = niantic_banned_proxies
    else:
        args.ptc_banned_proxy = None
        args.niantic_banned_proxy = None


def load_proxies(args):
    source_proxies = []
    if "proxy_file" in args and args.proxy_file is not None:

        with open(args.proxy_file) as f:
            for line in f:
                # Ignore blank lines and comment lines.
                if len(line.strip()) == 0 or line.startswith('#'):
                    continue
                source_proxies.append(line.strip())

        log.info('Loaded %d proxies.', len(source_proxies))

        if len(source_proxies) == 0:
            log.error('Proxy file was configured but ' +
                      'no proxies were loaded. Aborting.')
            sys.exit(1)
        for i, proxy in enumerate(source_proxies):
            if proxy == "localhost":
                source_proxies[i] = None
    if len(source_proxies) > 0:
        args.proxy = source_proxies


def parse_unicode(bytestring):
    return bytestring


def location(args):
    if args.location is None:
        return None
    # Use lat/lng directly if matches such a pattern.
    prog = re.compile("^(\-?\d+\.\d+),?\s?(\-?\d+\.\d+)$")
    res = prog.match(args.location)
    if res:
        return float(res.group(1)), float(res.group(2)), 0
    else:
        raise ValueError("need numeric gps coordinates")


triple_coord = re.compile("^(\-?\d+\.\d+),?\s?(\-?\d+\.\d+),?\s?(\-?\d+\.\d+)$")


def location_parse(loc):
    if loc is None:
        return None
    # Use lat/lng directly if matches such a pattern.
    res = triple_coord.match(loc)
    if res:
        return float(res.group(1)), float(res.group(2)), float(res.group(3))
    prog = re.compile("^(\-?\d+\.\d+)?\s?,?\s?(\-?\d+\.\d+)$")
    res = prog.match(loc)
    if res:
        return float(res.group(1)), float(res.group(2)), 0
    else:
        raise ValueError("need numeric gps coordinates")


class LocationParse(unittest.TestCase):
    def testVariousSpaces(self):
        self.assertEqual((12.2, 10.1, 0), location_parse("12.2,10.1"))
        self.assertEqual((12.2, 10.2, 0), location_parse("12.2 , 10.2"))
        # self.assertEqual((12.3,10.2,0), location_parse(" 12.3 , 10.2"))
        # self.assertEqual((12.4,10.2,0), location_parse("12.4 , 10.2 "))

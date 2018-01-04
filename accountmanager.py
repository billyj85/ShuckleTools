from argparser import std_config, add_threads_per_proxy, add_webhooks, add_search_rest, add_system_id, \
    add_use_account_db

parser = std_config("accountmanager")
add_threads_per_proxy(parser, 2)
add_webhooks(parser)
add_search_rest(parser)
add_system_id(parser)
add_use_account_db(parser)
parser.add_argument('-force', '--force-system-id',
                    help='Force the accounts to the system id regardless of previous value',
                    default=False)
parser.add_argument('-sa', '--skip-assigned',action='store_true', default=False,
                    help='Skip loading account that already exist')
parser.add_argument('-lg', '--login', action='store_true', default=False,
                    help='Login enough to find level and inventory (but not shadowban)')
parser.add_argument('-nlg', '--no-login', action='store_true', default=False,
                    help='Dont login, only allocate')

parser.add_argument('-lvl', '--level', default=30,
                    help='Level of the loaded accounts  (meaningless with --login)')
parser.add_argument('-owlvl', '--overwrite-level', default=False,
                    help='Force accounts to the supplied level')
parser.add_argument('-ad', '--allocation-duration', default=None,
                    help='If set, the accounts will be allocated from now() and the specified number of hours')
parser.add_argument('-mlvl', '--min-level', default=20,
                    help='Level of the loaded accounts')
parser.add_argument('-minl', '--max-level', default=40,
                    help='Level of the loaded accounts')
parser.add_argument('-n', '--count', default=3,
                    help='The number of accounts')
parser.add_argument('-f', '--format', default="monocle",
                    help='monocle or rocketmap')
args = parser.parse_args()
args.player_locale = {'country': 'NO', 'language': 'no', 'timezone': 'Europe/Oslo'}


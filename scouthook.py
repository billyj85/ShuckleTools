from aiohttp import web
import aiohttp
import asyncio
import async_timeout
from argparser import std_config, add_use_account_db_true, add_webhooks
parser = std_config("scouthook")
add_use_account_db_true(parser)
parser.add_argument('-system-id', '--system-id',
                    help='Define the name of the node that will be used to identify accounts in the account table',
                    default=None)
add_webhooks(parser)
args = parser.parse_args()
target = args.webhooks

async def handle_post(request):
    data = await request.json()
    scouted = do_scout(data)
    update_data(data, scouted)
    respose_text = await send_to_pa(scouted)
    return web.Response(text=respose_text)

async def post(session, url, data):
    with async_timeout.timeout(10):
        async with session.post(url, data=data) as response:
            return await response.text()

async def get(session, url):
    with async_timeout.timeout(10):
        async with session.get(url) as response:
            return await response.text()

async def send_to_pa(content):
    async with aiohttp.ClientSession() as session:
        html = await post(session, target, content)
        return html

async def do_scout(pokemon):
    msg = pokemon["message"]
    pokemon_id=msg["pokemon_id"]
    encounter_id=msg["encounter_id"]
    spawn_point_id=msg["spawnpoint_id"]
    latitude=msg["latitude"]
    longitude= msg["longitude"]
    return scout_it(pokemon_id, encounter_id, spawn_point_id, latitude, longitude)

async def scout_it(pokemon_id, encounter_id, spawn_point_id, latitude, longitude):
    return "yo"


def update_data(data,scouted):
    msg = data["message"]
    msg["cp"] = scouted["cp"]
    msg["cp_multiplier"] = scouted["cp_multiplier"]
    msg["individual_attack"] = scouted["iv_attack"]
    msg["individual_defense"] = scouted["iv_defense"]
    msg["individual_stamina"] = scouted["iv_stamina"]
    msg["height"] = scouted["height"]
    msg["weight"] = scouted["weight"]

app = web.Application()
app.router.add_post('/', handle_post)
web.run_app(app, host='0.0.0.0', port=4002)

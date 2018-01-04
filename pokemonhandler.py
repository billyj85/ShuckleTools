import calendar
from threading import Thread

import logging
import requests
import json
from queue import Queue
from datetime import datetime as dt, datetime, timedelta

from pogom.fnord_webhook import wh_updater
from pokemon_data import pmdata

args = None
queue = []
threads = []

log = logging.getLogger(__name__)


pokemon_data = pmdata()
wh_key_cache = {}
wh_updates_queue = Queue()

headers = {
    'User-Agent': 'discord-simple-webhook (0.0.1)',
    'Content-Type': 'application/json'
}


def pms2(pokemon_id, cell_id):
    name = pokemon_data[str(pokemon_id)]["name"]
    uri = "http://s2map.com/#order=latlng&mode=polygon&s2=false&points="
    s2msg("{} funnet kl {} i sone {}{}".format(name, dt.now().strftime('%H:%M'), uri, cell_id))


def s2msg(msg_to_send):
    if args.s2_hook:
        d = json.dumps({'content': msg_to_send})
        requests.post(args.s2_hook, headers=headers, data=d)


def send_to_webhook(pkmn):
    wh_poke = pkmn
    if "latitude" not in pkmn:
        return
    if "disappear_time" not in pkmn:
        now = datetime.utcnow()
        hardcoded_disappear = now + timedelta(hours=4, minutes=20, seconds=1)
        pkmn["disappear_time"] = hardcoded_disappear.timetuple()

        # pkmn["atitude"] = 42.0
    if "longitude" not in pkmn:
        pkmn["longitude"] = 43.0

    wh_poke.update({
        'disappear_time': calendar.timegm(pkmn["disappear_time"]),
        #                'disappear_time': int(time.mktime(now_plus_10.timetuple()) * 1000),
        'last_modified_time': "",  # pkmn['last_modified_timestamp_ms'],
        'time_until_hidden_ms': "",  # p['time_till_hidden_ms'],
        'verified': "",  # SpawnPoint.tth_found(sp),
        'seconds_until_despawn': "",  # seconds_until_despawn,
        'spawn_start': "",  # start_end[0],
        'spawn_end': "",  # start_end[1],
        'player_level': "",  # encounter_level
    })
    wh_updates_queue.put(('pokemon', wh_poke))


def set_args(args_in):
    global args
    args = args_in

    # Thread to process webhook updates.
    for i in range(args.wh_threads):
        log.debug('Starting wh-updater worker thread %d', i)
        t = Thread(target=wh_updater, name='wh-updater-{}'.format(i),
                   args=(args, wh_updates_queue, wh_key_cache))
        t.daemon = True
        t.start()


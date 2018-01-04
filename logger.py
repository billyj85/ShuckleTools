#!/usr/bin/python
import asyncio

import requests
import json
import time
from geopy.distance import vincenty
import logging

from async_accountdbsql import set_account_db_args
from argparser import basic_std_parser,load_proxies
from gymdbsql import set_gymdb_args, make_gym_map, member_list, defender_list, make_gym_map_v2
from scannerutil import install_thread_excepthook, as_str
from gymdb import log_gym_change
from gymdbsql import member_map,previous_gym,get_bad_guys,defender_map as get_gym_defenders

import pymysql.cursors
from pymysql import IntegrityError

'''
ALTER TABLE badguys ALTER column kind enum('BOT','SPOOFER','SUSPECT') NOT NULL;
 aalter table gym add previous_scan datetime;
 delimiter $$
 CREATE TRIGGER GymUpdate BEFORE UPDATE ON  gym
  FOR EACH ROW BEGIN SET NEW.previous_scan = OLD.last_scanned; END$$
  delimiter ;

create view gymoverview as select g.gym_id,g.team_id,gd.name, trainer_name,gp.pokemon_id,gp.cp,gp.iv_attack,gp.iv_defense, gp.iv_stamina,g.latitude,g.longitude,g.last_modified,g.last_scanned,gd.last_scanned as gd_last_scanned,gm.last_scanned as gm_last_scanned, gp.pokemon_uid from gympokemon gp, gymdetails gd, gym g, gymmember gm where gp.pokemon_uid=gm.pokemon_uid and gm.gym_id=g.gym_id and gd.gym_id=g.gym_id;

SELECT  gym_id, MAX(ts) as TIME, count(*) group by site_id

create table if not exists gymlog (
	gym_id VARCHAR(50),
    name VARCHAR(255),
	latitude double,
	longitude double,
	gym_points int,
	team_id smallint,
	last_modified datetime,
	last_scanned DATETIME,
	previous_scan datetime,
	gym_member_last_scanned datetime,
	trainer_name VARCHAR(255),
	pokemon_id smallint(6),
    pokemon_uid varchar(50),
	cp smallint(6),
	`iv_attack` smallint(6),
	`iv_defense` smallint(6),
         iv_stamina` smallint(6),
         kmh float,
         distance int,
        previous_gym VARCHAR(255),
	PRIMARY KEY (gym_id,trainer_name,last_modified)

);

ALTER TABLE `gymlog` ADD `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY

create view logview as select trainer_name,CONCAT(CONCAT(latitude, ','), longitude) as coords, CONVERT_TZ( last_modified, '+00:00', '+02:00' ) as last_modified_CET, CONVERT_TZ( last_scanned, '+00:00', '+02:00' ) as last_scanned_CET, gym_points,name, kmh, distance, previous_gym from gymlog order by last_modified_CET;

Find by logged pokemon (alias change)
select * from gymoverview,gymlog where gymlog.pokemon_uid=gymoverview.pokemon_uid and gymlog.trainer_name LIKE '%Rhy%';

Previous gym for trainer:
select last_modified,latitude,longitude from( select * from gymlog where trainer_name like '%JANH%' order by last_modified desc limit 2) as xv order by last_modified limit 1;

create table specialgyms (  gym_id VARCHAR(50), kind VARCHAR(50) );
'''


logging.basicConfig(
    format='%(asctime)s [%(threadName)12s][%(module)10s][%(levelname)8s] ' +
           '%(message)s', level=logging.INFO)
log = logging.getLogger(__name__)
logging.getLogger("pgoapi").setLevel(logging.WARN)
logging.getLogger("connectionpool").setLevel(logging.WARN)
logging.getLogger("Account").setLevel(logging.INFO)

'''
Schema changes:
alter table gymmember add column first_seen datetime null;
alter table gymmember add column last_no_present datetime null;
alter table gym add column gymscanner smallint null;
'''
parser = basic_std_parser("gymanalyzer")
parser.add_argument('-boh', '--bot-hook', default=None,
                    help='bot discord hook')
parser.add_argument('-sph', '--spoofer-hook', default=None,
                    help='spoofer discord hook')
parser.add_argument('-suh', '--suspect-hook', default=None,
                    help='spoofersuspect discord hook')

args = parser.parse_args()
set_gymdb_args(args)
set_account_db_args(args)


install_thread_excepthook()

headers = {
    'User-Agent': 'discord-simple-webhook (0.0.1)',
    'Content-Type': 'application/json'
}

def suspectmsg(msgToSend):
    d = json.dumps({'content': msgToSend})
    requests.post(args.suspect_hook, headers=headers, data=d)


def spoofermsg(msgToSend):
    d = json.dumps({'content': msgToSend})
    requests.post(args.spoofer_hook, headers=headers, data=d)

def bubblemsg(msgToSend):
    d = json.dumps({'content': msgToSend})
    requests.post(args.spoofer_hook, headers=headers, data=d)


def botmsg(msgToSend):
    d = json.dumps({'content': msgToSend})
    requests.post(args.bot_hook, headers=headers, data=d)


def asString(gymparticipant):
  first = as_str(gymparticipant["trainer_name"]) + ", " + str(gymparticipant["last_modified"]) + ", "
  second = str(gymparticipant["latitude"]) + ", " + str(gymparticipant["longitude"]) + ", "
  gym_name = as_str(gymparticipant["name"])
  return first + second + gym_name


def getDiff( old, new):
  diff = []
  for gymname in new:
    newgym = new[gymname]
    if gymname in old:
      oldgym = old[gymname]
      for defender in newgym['defenders']:
        trainerName = defender['trainer_name']
        existsInPrevious = next((i for i in oldgym['defenders'] if i['trainer_name'] == trainerName), None)
        if existsInPrevious is None:
          diff.append( defender)
  return diff


def bubble_log(old, new):
  for gym_id in new:
    newgym = new[gym_id]
    defenders = newgym['defenders']
    if len(defenders) > 0:
        lowest = defenders[0]
        if lowest["pokemon_id"] == 92 and lowest.get("move_1") == 263:
            oldgym = old.get(gym_id)
            if not oldgym is None:
                old_defenders = oldgym['defenders']
                if len(old_defenders) == 0:
                    bubblemsg(str( lowest))
                else:
                    lowest_old = old_defenders[0]
                    if lowest_old["pokemon_uid"] != lowest["pokemon_uid"]:
                        try:
                            msg = "Bubble insertion at {} from trainer {} (team{}) {} {}".format(
                                lowest["name"],
                                lowest["trainer_name"],
                                team_name(lowest["team_id"]),
                                str(lowest["latitude"]),
                                str(lowest["longitude"])
                            )
                            bubblemsg(msg)
                        except UnicodeEncodeError:
                            pass


def team_name(id):
    if id == 3:
        return "Instinct"
    return "Team" + str(id)


def logall( new):
  for gymname in new:
      for member in new[gymname]:
            log_gym_change(new[gymname][member])

def checkDiff( old, new):
    spoofers = get_bad_guys("SPOOFER")
    suspects = get_bad_guys("SUSPECT")
    known_bad = get_bad_guys("BOT")

    for diff in getDiff( old, new):
        trainer_name = diff['trainer_name']
        log_gym_change(diff, previous_gym( trainer_name))

        if trainer_name in known_bad:
            tetxt = "SPOOFER KNOWN " + asString(diff)
            print(tetxt)
            botmsg(tetxt)
        elif trainer_name in spoofers:
            tetxt = "SPOOFER " + asString(diff)
            print(tetxt)
            spoofermsg(tetxt)
        elif trainer_name in suspects:
            tetxt = "SPOOFER SUSPECT " + asString(diff)
            print(tetxt)
            suspectmsg(tetxt)
        else:
            print("OK" + asString(diff))

    bubble_log(old, new)


async def start_analyzer():

    gyms = make_gym_map_v2(member_list())
    gym_defenders = make_gym_map_v2(defender_list())
    #logall(gyms)
    suspectmsg("Gym logger started")
    while True:
        try:
            # rcoketmap model
            newgyms = make_gym_map_v2(member_list())
            checkDiff(gyms, newgyms)
            gyms = newgyms

            # Gymscanner model
            new_gym_defenders = make_gym_map_v2(defender_list())
            checkDiff(gym_defenders, new_gym_defenders)
            gym_defenders = new_gym_defenders
        except KeyboardInterrupt:
            print ("Interrupt ?")
        else:
            await asyncio.sleep(60)


start_analyzer()

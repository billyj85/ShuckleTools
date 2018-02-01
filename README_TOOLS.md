ShuckleTools Tools
===================

These tools do not require that you run rocketmap, but are based on rocketmap code. The overall api compliance
of these tools should be fairly similar to RocketMap since it uses actual RocketMap code. 

You might put the "bin" subfolder of your checkout in your path. If your checkout is /home/username/RocketMap you can add /home/username/RocketMap/bin to your path.

Levelup docs are here Database schema is located at https://github.com/ShuckleHQ/ShuckleTools/README_LEVELUP.md

Large scale lure dumper
===========

Loures predefined routes that are described in a json file. In run-time each route is split into route-segments 
of no more than 6 pokestops. A route should typically be constrained to a geographic area.

See config/lureparty.ini.example and config/locations_sample.json

Requires mysql with "account" table described below.

Database schema is located at https://github.com/ShuckleHQ/RocketMap/blob/develop/database_scripts.md

** One pokestop per coordinate in the routes section. Pokestop closest to coordinate will be lured.

```
python3 lureparty.py -cf lureparty.ini --json-locations=locations.json --owner=lureparty --proxy-file=proxies.txt --accountcsv=accts_rocketmap_format.txt --base-name=BrandednName --base-name=Bname2 
```

When adding more lure accounts you can just change file. The accounts accumulate in the database.

Commands you can run in the database:
-------
See how many accounts have not yet been emptied of lures. (Actually the DB value is always NULL or 0 with lureParty.py)
```
select count(*) from account where owner='lureparty' and Coalesce(lures,1)<>0;
```

Other useful sql:
```
select count(*) from account where owner="lureparty"; -- show number of accounts in database
select count(*) from account where owner = 'lureparty' and lures is null; --accounts with unknown lure status
delete from account where owner="lureparty"; -- unload from database
update account set owner=null;  -- Disassociate all accounts from a named process    
```

Geofence + RocketMap/Monocle support
---------------
If your database has a table called pokestops with the rocketmap format of data, you can add 
a geofence file to your config.
```
geofence=geofence.txt
#fencename=asinglefence
```

Adding a geofence called "CentralPark" to the geofence file will introduce a ROUTE called CentralPark that can
be used in the regular json file. If the geofence file contains multiple overlapping geofences, each pokestop will
 be assigned to the first matching geofence.  The fencename parameter will contstrain the fence matching to the 
 single named fence (effectively ignoring the rest of the fences in the geofence file
 
If your rocketmap database is in a different database from the account database, you can create a view of the
 pockestops table in your account database. The lureparty module does not connect directly to your rocketmap database.
```
FOR ROCKETMAP:
CREATE VIEW `AccountDb`.`pokestop` AS SELECT * FROM `RocketMapDB`.`pokestop`;
```

On a similar note, if your monocle supports pokestop scanning you should be able to do the same.
```
FOR MONOCLE:
CREATE VIEW `AccountDb`.`pokestop` AS SELECT external_id as pokestop_id,lat as latitude, lon as longitude FROM `MonocleDB`.`forts`;
```

(AccountDB, RocketMapDB and MonocleDB in the above statements need to be replaced with actual database names)


On-demand luring
-----
If you set the host/port argument in the lureparty.ini file, you can expose the on-demaind lure service. You need to 
the "lures" database table (described at the bottom of document)..

There is no admin gui for the lures, to create a user and give her lures, do the following:

```
insert into lures(username, max_lures) values('laracroft', 500);
```

Now by accessing 
```
http://localhost:8701/lures/laracroft/55.662427,12.562064/60
```

You will lure for 60 minutes at fisketorget in copenhangen. Once "laracroft" runs out of lures, you will
need to assign more lures to the user.

Lara can also use 
```
http://localhost:8701/laracroft/
```


--Need clarification on Radious & see if GPS Position can be truncated ---

'/lurebomb/{user}/
'/lures/{user}/{position}/{minutes}')
'/lures/{user}/{position}/{minutes}/{radius} in Meters 
'/lurebomb/{user}/lurebomb').add_route('POST', post_lure_request)


to lure from her current location. Please note that trailing slash.

There is no "security" in the solution other than knowing the URL and the username. Hence it might make sense
to add a few digits or similar to user's real in-game nics, e.g. "laracroft17"

Tips/Notes
-----
* Lures are dropped in routes or subsets of a route. Routes are chopped into sections of 6 pokestops or less, 
  which each gets its own worker.
* A single account is bound to a single route-segment for the duration of a luring process. If you restart the process
  it may move around.
* If you are luring a specific grinding route that people walk in a single direction, it's smart to declare the route 
  in the opposite direction.
* Users should be discouraged from luring manually in the routes, it makes the bot work less well.
* The bot typcally uses 1 extra minute per hour. For long runs (>3 hours) I recommend setting and end time that resembles
  when you want the last lure to expire. 09:00-01:29 will typically have the last lure activated at 01:16.
  Using 07.00-09.00 will typically have the last lure expire at 09:04 (and set 4 lures per stop). Setting time to 
  07.00-09.05 will normally give you 5 lures ending at 09:35-ish. But an end-time of 09:30 is far preferable if
  this is what you want.
* Captchas, account-bans, hashing failurs or other intermittent problems delay luring. Impatient users might have 
  a segment without lures for a few minutes while things are being automatically fixed.
* As long as you lure in a single city, softban issues while restarting are minimal. If you lure multiple cities
  you can start two different processes (with the same database) but with different "owner" flag: --owner=NewYork on one
  and --owne=LA on the other. These will need distinct account files, but each process will stay within its own account
  pool.
* Intermittent technical issues or bugs can lead the process to terminate with "no more accounts in pool". In these cases you can simply restart. In general, accounts with lures=0 are empty, all others are either unused or banned. When approaching the end of the account pool (for real), you should probably restart a few times anyway. Or maybe just add more accounts. You can keep the old ones in.


Hashing requirements: In theory, it only uses 3-4 RPM on average. In practice, it seems that about 4 route-parts can 
be started concurrently on a 150RPM key. This application does *not* degrade gracefully if you run over hash key limits.

Rocketmap with improved account manager
==========
Standard rocketmap with proper databse backed account manager. 
Also more sophisticated L30 account handling, including rest intervals.

How to use:

1. Create database table account as decribed below
2. Rocketmap parameter "status-name" *must* be set, this will be the "owner" in the account table. (name and name_CP).
   Upon first starting with a text/csv file, all accounts will be written to db. After that file can be emptied
   or left as-is. If any accounts are added to this file, they will be added to the database.
   When the "banned" flag in the database passes 10 the account is considered truly dead.
   Only "banned" and "allocated" are populated for regular accounts, L30 account pool get more information.
3. To use the sophisticated L30 manager, the *filename* of the accounts file must START with accounts30 (e.g.) accounts30.csv
   accounts30.txt or accounts30foobar.txt



pokestops
===========

Identifies pokestop clusters with 3-4 reachable pokestops or more. Copy config/pokestops.ini.example to RocketMap folder.

Usage: pokestops

blindCheck
============

Usage blindCheck accountfile

Also uses a location from the blindcheck.ini file (in RocketMap folder - use config/blindcheck.ini.example as starter start)

Uses the ACTUAL rocketmap code to check for blindbess. If this breaks your accounts, so will rocketmap.

The location should probably point at some local nest 

Once the blindcheck has completed you will get three new files with additional suffixes.


Please note if ALL your accounts are blinded you may want to double check that the location actually HAS pokemons in the 
"blided" category.


Database schema is located at https://github.com/ShuckleHQ/RocketMap/blob/develop/database_scripts.md

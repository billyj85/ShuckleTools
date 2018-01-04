Account database
======

The account datavbase requires mysql, and is a precondition for running ANY of these tools. No mysql, no tools.

It's probably easiest to put this table inside your rocketmap database if you use rocketmap. It will not
interfere with rocketmap. Or you can make a separate database.

Full database schema as of Oct 17
===============

You can "drop table account" to delete old table and recreate new table. Subsequent releases will
incrementally patch this database schema for any further changes.

```
CREATE TABLE `account` (
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `provider` varchar(6) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `model` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `iOS` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `device_id` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `behaviour` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `level` int(11) DEFAULT NULL,
  `allocated` datetime DEFAULT NULL,
  `allocation_end` datetime DEFAULT NULL,
  `last_login` datetime DEFAULT NULL,
  `blinded` datetime DEFAULT NULL,
  `warned` datetime DEFAULT NULL,
  `temp_banned` datetime DEFAULT NULL,
  `perm_banned` datetime DEFAULT NULL,
  `system_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `rest_until` datetime DEFAULT NULL,
  `lures` int(11) DEFAULT NULL,
  `eggs` int(11) DEFAULT NULL,
  PRIMARY KEY (`username`)
)
```

On-demand lure dumper also requires this table:
===============
```
CREATE TABLE lures
(
    username VARCHAR(50) PRIMARY KEY NOT NULL,
    lures int default 0,
    max_lures int
);
```

Practical view (not needed)
```
create view av as select username,model,level,lures,eggs,allocated,allocation_end,blinded,system_id,temp_banned,warned,rest_until,perm_banned,last_login from account;
```

Some of the gym features in the library might need this: 
```
CREATE VIEW gymview AS select g.gym_id AS gym_id,g.team_id AS team_id,g.guard_pokemon_id AS guard_pokemon_id,g.enabled AS enabled,g.latitude AS latitude,g.longitude AS longitude,g.last_modified AS last_modified,g.last_scanned AS last_scanned,g.previous_scan AS previous_scan,g.gymscanner AS gymscanner,gd.name AS name,gd.description AS description,gd.url AS url,gd.last_scanned AS gd_last_scanned from (gym g left join gymdetails gd on(g.gym_id = gd.gym_id));
```

changes 14-oct:
=======
If you are VERY adventurous, some of these statements should upgrade an older version

```
alter table account drop column created;
alter table account drop column template_time;
alter table account drop column asset_time;
alter table account drop column inventory_timestamp;
alter table account drop column auth;
alter table account drop column expiry;
ALTER TABLE account CHANGE COLUMN `last_allocated` `allocated` datetime NULL;
ALTER TABLE account CHANGE COLUMN `id` `device_id` VARCHAR(40) NULL;
alter table account drop column blindchecked;
ALTER TABLE account CHANGE COLUMN `owner` `system_id` VARCHAR(20) NULL;
ALTER TABLE account CHANGE COLUMN `ios` `iOS` VARCHAR(10) NULL;
alter table account drop column items;
alter table account add column allocation_end datetime null;
ALTER TABLE account CHANGE COLUMN `banned` `temp_banned` datetime NULL;
alter table account add column perm_banned datetime null;
alter table account add column last_login datetime null;
alter table account drop column banned;
alter table account add column eggs int;
alter table account add column warned datetime null;
ALTER TABLE account CHANGE COLUMN `owner` `system_id` VARCHAR(20) NULL;
alter table account drop column time;
alter table account drop column items;
alter table account drop column captcha;
alter table account drop column location;
alter table account drop column times_blinded;

```





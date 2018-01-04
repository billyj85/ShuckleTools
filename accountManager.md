AccountManager
=============

NOTE: the commands and samples in this document are meant as an illustration. It might require some additional config
and sense of adventure to try this for real right now.


The account manager is a circular pool of accounts. Add all your accounts from hundreds of selly emails or other
sources to the database and it will sort it all out for you.

Usage
------

The current usage is simple, there is currently no automated integration with rocketmap or monocle, but it still saves
you a lot of headache:

Basically you say:

```
python3 allocateAccount.py --max-level=31 --min-level=30 --count=400 --format=monocle --accountcsv=accounts.csv
```

The idea is that you run this inside your monocle/rocketmap installation and it actually allocates 400 accounts and
OVERWRITES accounts.csv. Within this system, the old accounts.csv is garbage. Once such a file is generated,
all the accounts within the file will end up at the *end* of the account pool.

What does it do ?
-----
Allocating accounts uses the 400 least recently used accounts matching the level-criteria. These are blind-checked 
before being written to the accountscsv file. Any accounts faililing due to temp-ban, permban or blindness are
moved 10 days into the future. If more accounts are needed, it will fetch more accounts - always using the least-recently 
used accounts.

You are supposed to run this allocation process *immediately* before using the accounts.

Why is this a good design ?
------
Blind-checking an account initiates the blindness timer for that account. This design ensures that you only 
blind-check in-stock accounts just before using them. The code also allows for configurable durations for the 
different kind of bans (temp/shadow/perm) [not exposed in settings yet].

 
Loading accounts into the database
-------------
The intention is that you add ALL your accounts to
the database, preferably adding the least-recently used accounts first. The last accounts you
add are the temp-banned accounts.


The accountloader.py is used to load accounts from files into the database. It automatically detects
rocketmap, mocole and all sorts of Selly email formats. Ensure that you specify the level of the accounts you
are loading (or a lower level).

When running rocketmap, you can do:
```
python3 scripts/export_accounts_csv.py
python3 accountloader accounts.csv 
```

This will update the account database with the monocle device ids and iOS configuration.

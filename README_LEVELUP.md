Welcome to ShuckleTools Documentation!
=========

The following guide will assist in understanding how to use LevelUp.py which effectively brings accounts to a level of 5/20/30. This is done by looting pokestops and catching pokemon at a predefined set of locations with minimal config options. 

ShuckleTools only supports MySQL

If double xp events are running the "fast-levelup" flag can be used, optionally also the "non-stop" flag will run until all accounts are at desired level. 

The sample config in the config folder is optimal. ~/ShuckleTools/config/levelup.example.ini

Basic Installation 
-------
These instructions cover an installation from the develop branch in git.
```
git clone https://github.com/ShuckleTools/ShuckleTools.git
```

Navigate to ./ShuckleTools/ run 

```
pip3 install -r requirements.txt --upgrade
```

Configure levelup.ini 
```
cp ~/ShuckleTools/config/levelup.ini.example  ~/ShuckleTools/config/levelup.ini
```

Create Database or Tables in an existing RocketMap or MonocleDB, the insert statments are located at https://github.com/ShuckleHQ/database_scripts.md


Load Accounts into the Accounts table 
```
~/ShuckleTools/bin/loadAccounts accountsfile.txt --system-id=your-bot-system-id
```

Using levelUp:
```
nohup levelUp &
```

Log output is written to a log file called [system-id].log

```
grep XP <logfile> | grep bot-2] | grep XP | less
```

Will give you somethung like this (note the square bracket after 2 to diffrentiate bot-2 from bot-21:

```
2017-11-25 16:35:00,245 [       bot-2][  stopmanager][    INFO][1840258] P1L21, 134S/106P//R0.79, 8E/1EW, 263620XP/260420@30minH, 0S@30min. idx=52, 918 hash
2017-11-25 16:36:34,712 [       bot-2][  stopmanager][    INFO][1934725] P1L21, 139S/113P//R0.81, 8E/1EW, 276400XP/255200@30minH, 0S@30min. idx=54, 199942 hash
2017-11-25 16:37:08,989 [       bot-2][  stopmanager][    INFO][1969002] P1L21, 141S/116P//R0.82, 8E/2EW, 280840XP/259640@30minH, 0S@30min. idx=55, 752 hash
2017-11-25 16:38:47,692 [       bot-2][  stopmanager][    INFO][2067705] P1L21, 146S/121P//R0.83, 8E/2EW, 289780XP/260900@30minH, 0S@30min. idx=57, 199929 hash
```

```
P1L21 = Phase 1 Level 21
146S/121P = 146 stops spinned, 121 pokemon caught
R = stop/spin ratio
8E/2EW : 8 evolves, 2 evolves waiting
289780XP/260900@30minH = total xp/last 30 minutes. "EH" means lucky egg is active.
idx=57 position in route
725 hash = number of hashes remaining. The example uses overflow hashing to goman.
```

Also note if you run multiple instances of the bot they should have different names in levelup.ini, since the accounts in
the database are attached through the "owner" field


Only use fresh L0 accounts to avoid problems with prior bans/shadowbans affecting the botting process.

from scannerutil import auth_service, device_id


def load_reallocatable_sql(system_id, ban_time, warn_time, ok_if_blinded_before, now):
    params = (system_id, ban_time, warn_time, ok_if_blinded_before, now, now)
    return "SELECT username, password, provider FROM account " \
           "WHERE system_id = %s AND perm_banned IS NULL AND (temp_banned IS NULL OR temp_banned < %s) " \
           "AND (warned IS NULL OR warned < %s) AND (blinded IS NULL OR blinded < %s) " \
           "AND allocated < %s AND %s < allocation_end " \
           "ORDER BY allocated", params


def sql_find_allocatable(temp_ban_time, warn_time, blind_time, now):
    params = (temp_ban_time, warn_time, blind_time, now)
    return "SELECT username, password, provider,iOS,model,device_id AS id FROM account " \
           "WHERE perm_banned IS NULL AND (temp_banned IS NULL OR temp_banned < %s) " \
           "AND (warned IS NULL OR warned < %s) AND (blinded IS NULL OR blinded < %s) " \
           "AND (allocation_end IS NULL OR %s > allocation_end) " \
           "ORDER BY allocated", params


def sql_find_allocatable_by_level(temp_ban_time, perm_ban_time, warn_time, blind_time, now, min_level=0, max_level=40):
    params = (temp_ban_time, perm_ban_time, warn_time, blind_time, now, min_level, max_level)
    return "SELECT username, password, provider,iOS,model,device_id AS id FROM account " \
           "WHERE (temp_banned IS NULL OR temp_banned < %s) " \
           "AND (perm_banned IS NULL OR perm_banned < %s)  " \
           "AND (warned IS NULL OR warned < %s) " \
           "AND (blinded IS NULL OR blinded < %s) " \
           "AND (allocation_end IS NULL OR %s > allocation_end) " \
           "AND level >= %s AND level <= %s " \
           "ORDER BY allocated", params


sql_consume_lures = 'UPDATE account SET lures=0 WHERE username=%s'


def sql_set_blinded(account, when):
    return 'UPDATE account SET blinded=%s WHERE username=%s', (when, account)


def sql_set_rest_until(account, when):
    return 'UPDATE account SET rest_until=%s WHERE username=%s', (when, account)


def sql_set_account_level(account, level):
    return 'UPDATE account SET level=%s WHERE username=%s', (level, account)


def sql_set_egg_count(account, egg_count):
    return 'UPDATE account SET eggs=%s WHERE username=%s', (egg_count, account)


def sql_set_lure_count(account, lure_count):
    return 'UPDATE account SET lures=%s WHERE username=%s', (lure_count, account)


def sql_set_logged_in_stats(account, lure_count, egg_count, level):
    return 'UPDATE account SET lures=%s,LEVEL=%s,eggs=%s WHERE username=%s', (lure_count, level, egg_count, account)


def sql_set_temp_banned(username, when):
    return 'UPDATE account SET temp_banned=%s WHERE username=%s', (when, username)


def sql_set_behaviour(account, behaviour):
    return 'UPDATE account SET behaviour=%s WHERE username=%s', (behaviour, account)


def sql_load_accounts(system_id):
    sql = "SELECT username, password, provider AS auth_service,allocated FROM account " \
          "WHERE system_id=%s AND ( temp_banned IS NULL AND perm_banned IS NULL) " \
          "ORDER BY allocated;"
    return sql, system_id


def sql_load_reallocated_accounts(system_id, from_time, to_time):
    sql = "SELECT username, password, provider AS auth_service,allocated FROM account " \
          "WHERE system_id=%s AND (allocated > %s AND allocated < %s) AND ( temp_banned IS NULL) " \
          "AND perm_banned IS NULL " \
          "ORDER BY allocated;"
    return sql, (system_id, from_time, to_time)


def sql_set_allocated_time(username, allocated):
    return 'UPDATE account SET allocated=%s WHERE username=%s', (allocated, username)


def sql_update_account(account_info):
    sql = 'UPDATE account SET temp_banned=%s,blinded=%s,rest_until=%s WHERE username=%s'
    params = (account_info.banned, account_info.blinded, account_info.rest_until,
              account_info.username)
    return sql, params


def sql_set_warned(account_info, when):
    return 'UPDATE account SET warned=%s WHERE username=%s', (when, account_info.username)


def sql_set_perm_banned(account_info, when):
    params = (when, account_info.username)
    return 'UPDATE account SET perm_banned=%s WHERE username=%s', params


def sql_roll_allocated_date_forward(account_info):
    return 'UPDATE account SET allocated=DATE_ADD(coalesce(allocated, now()), INTERVAL 10 DAY) WHERE username=%s', account_info.username


def sql_load_accounts(system_id, ban_cutoff_date):
    if not system_id:
        raise ValueError("need system_id")
    sql = "SELECT username,password,provider AS auth,lures,rest_until,allocated,perm_banned,temp_banned,last_login," \
          "blinded,behaviour,`level` " \
          "FROM account WHERE system_id=%s AND (temp_banned IS NULL OR temp_banned < %s) AND " \
          "(perm_banned IS NULL OR perm_banned < %s) " \
          "ORDER BY username;"
    return sql, (system_id, ban_cutoff_date, ban_cutoff_date)


def sql_load_accounts_for_lures(system_id, ban_cutoff_date):
    if not system_id:
        raise ValueError("need system_id")
    sql = "SELECT username,password,provider AS auth,lures,rest_until,allocated,perm_banned,temp_banned,last_login," \
          "blinded,behaviour,`level` " \
          "FROM account WHERE system_id=%s AND (temp_banned IS NULL OR temp_banned < %s) AND " \
          "(perm_banned IS NULL OR perm_banned < %s) " \
          "ORDER BY allocated DESC;"
    return sql, (system_id, ban_cutoff_date, ban_cutoff_date)


def sql_load_accounts_for_blindcheck(system_id, ban_cutoff_date):
    if not system_id:
        raise ValueError("need system_id")
    sql = "SELECT username,password,provider AS auth,lures,rest_until,allocated,perm_banned,temp_banned,last_login," \
          "blinded,behaviour,`level` " \
          "FROM account WHERE system_id=%s ORDER BY allocated DESC;"
    return sql, (system_id)


def sql_account_exists(username):
    sql = "SELECT * FROM account WHERE username=%s"
    return sql, username


def sql_load_account(username):
    sql = "SELECT * FROM account WHERE username=%s"
    return sql, username


def sql_set_ios(username, ios):
    return 'UPDATE account SET ios=%s WHERE username=%s', (ios, username)


def sql_delete_pokestop(pokestop):
    return 'DELETE FROM pokestop WHERE pokestop_id=%s', pokestop


def sql_set_model(username, model):
    return 'UPDATE account SET model=%s WHERE username=%s', (model, username)


def sql_set_device_id(username, deviceid):
    return 'UPDATE account SET device_id=%s WHERE username=%s', (deviceid, username)


def sql_set_system_id(username, system_id):
    return 'UPDATE account SET system_id=%s WHERE username=%s', (system_id, username)


def sql_account_level(username, level):
    return "UPDATE account SET level=%s WHERE username=%s", (level, username)


def sql_allocated(username, allocated):
    return "UPDATE account SET allocated=%s WHERE username=%s", (allocated, username)


def sql_allocation_end(username, allocation_end):
    return "UPDATE account SET allocation_end=%s WHERE username=%s", (allocation_end, username)


def sql_insert_account(account, system_id, allocated, allocation_end):
    sql = "INSERT INTO account(username,password,provider,model,ios,device_id,system_id,allocated,allocation_end) " \
          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    params = (account["username"], account["password"], auth_service(account), account.get("model"), account.get("iOS"),
              device_id(account), system_id, allocated, allocation_end)
    return sql, params


def upsert_account_select(username):
    return "SELECT username,system_id FROM account WHERE username=%s", username


def upsert_account_insert(username, password, provider, system_id):
    sql = "INSERT INTO account(username,password,provider,system_id) VALUES(%s,%s,%s,%s)"
    return sql, (username, password, provider, system_id)


'''
Data for test database:
insert into account(username,password,provider,system_id,allocated,allocation_end) values
  ("tu0clean", "tu0pclean", "ptc","testcase1","2012-9-15 20:30:00", "2013-9-15 20:30:00");

insert into account(username,password,provider,system_id,blinded, allocated, allocation_end) values
  ("tu1blinded", "tu1p", "ptc","testcase1","2012-9-16 21:00:00", "2012-9-15 21:00:00","2012-9-17 21:00:00");
insert into account(username,password,provider,system_id,warned, allocated) values
  ("tu2warned", "tu2p", "ptc","testcase1","2012-9-16 22:00:00",  "2012-9-15 21:01:00");
insert into account(username,password,provider,system_id,temp_banned, allocated) values
  ("tu3banned", "tu3p", "ptc","testcase1","2012-9-16 23:00:00",  "2012-9-15 21:02:00");


insert into account(username,password,provider,system_id,allocated) values
  ("tu1bclean", "tu1bpclean", "ptc","testcase1","2012-9-15 21:1:00");
insert into account(username,password,provider,system_id,allocated) values
  ("tu2bclean", "tu2bpclean", "ptc","testcase1","2012-9-15 21:01:30");
insert into account(username,password,provider,system_id,allocated,allocation_end) values
  ("tu3bclean", "tu3bpclean", "ptc","testcase1","2012-9-15 21:02:30","2012-9-18 21:02:30");


insert into account(username,password,provider,system_id) values
  ("tu4neverallocated", "tu4bpclean", "ptc","testcase1");


'''

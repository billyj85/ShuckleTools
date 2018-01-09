import logging
import datetime
import time
from pymysql import InternalError
import pymysql.cursors
from pymysql import IntegrityError

from scannerutil import as_str

log = logging.getLogger(__name__)

args = None


def set_gymdb_args(new_args):
    global args
    args = new_args


def __gymmapconnection():
    return pymysql.connect(user=args.db_user, password=args.db_pass, database=args.db_name, host=args.db_host,
                           port=args.db_port,
                           charset='utf8mb4',
                           cursorclass=pymysql.cursors.DictCursor)


def log_gym_change_in_db(g, previous_gym_name, kmh, distance):
    connection = __gymmapconnection()

    try:
        latitude_ = g["latitude"]
        longitude_ = g["longitude"]
        name_ = as_str(g["name"])
        modified_ = g["last_modified"]

        sql = "INSERT INTO gymlog(" \
              "gym_id,`name`,trainer_name," \
              "pokemon_uid,latitude,longitude," \
              "last_modified,last_scanned,previous_scan,gym_member_last_scanned,  " \
              "gym_points,team_id, pokemon_id, " \
              "cp, iv_attack, iv_defense, " \
              "iv_stamina, distance, kmh, previous_gym) " \
              "VALUES(" \
              "%s,%s,%s," \
              "%s,%s,%s," \
              "%s,%s,%s,%s," \
              "%s,%s,%s," \
              "%s,%s,%s," \
              "%s,%s,%s,%s)";
        # Read a single record
        trainer_name_ = as_str(g["trainer_name"])
        id_ = as_str(g["gym_id"])
        pokemon_id_ = g["pokemon_id"]
        uid_ = as_str(g["pokemon_uid"])
        args = (id_, name_, trainer_name_, uid_, latitude_, longitude_,
                modified_, g["last_scanned"], g["last_scanned"],
                g["gym_member_last_scanned"],
                g["gym_points"], g["team_id"], pokemon_id_,
                g["cp"], g["iv_attack"], g["iv_defense"], g["iv_stamina"], kmh,
                distance, previous_gym_name)
        connection.cursor().execute(sql, args)
        connection.commit()
    except IntegrityError as e:
        print("Already inserted")
    finally:
        connection.close()


def do_with_backoff_for_deadlock(thefunc):
    for i in [5, 10, 30, 60, 120]:
        try:
            return thefunc()
        except InternalError:
            log.exception("Something broke in sql")
            time.sleep(i)
    log.error("Unable to execute sql update after 5 backoffs, failing")


def previous_gym(trainer_name):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT `name`,last_modified,latitude,longitude FROM( SELECT * FROM gymlog WHERE trainer_name = %s ORDER BY last_modified DESC LIMIT 2) AS xv ORDER BY last_modified LIMIT 1;"
            cursor.execute(sql, trainer_name)
            return cursor.fetchone()
    finally:
        connection.close()


def get_bad_guys(type):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT trainer_name FROM badguys WHERE kind = %s"
            cursor.execute(sql, (type))
            fetchall = cursor.fetchall()
            result = []
            for row in fetchall:
                result.append(row["trainer_name"])
            return result
    finally:
        connection.close()


def gymmap():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT gd.name,g.gym_points,g.latitude,g.longitude,g.team_id,trainer_name,gp.pokemon_id,gp.pokemon_uid,gp.cp,gp.iv_attack," \
                  "gp.iv_defense, gp.iv_stamina,g.last_modified,g.last_scanned,g.previous_scan,gm.last_scanned AS gym_member_last_scanned, g.gym_id " \
                  "FROM gympokemon gp, gymdetails gd, gym g,gymmember gm " \
                  "WHERE gp.pokemon_uid=gm.pokemon_uid AND gm.gym_id=g.gym_id AND gd.gym_id=g.gym_id";
            cursor.execute(sql)
            result = cursor.fetchall()
            gyms = {}
            for row in result:
                trainer_name_ = row["trainer_name"]
                row_name_ = row["name"]
                if not row_name_ in gyms:
                    gyms[row_name_] = {}
                members = gyms[row_name_]
                members[trainer_name_] = row.copy()
                gyms[row_name_] = members

            return gyms
    finally:
        connection.close()


sql = "select p.*,l.altitude from " \
      "spawnpoint p left join locationaltitude " \
      "l on p.latitude=l.latitude and p.longitude=l.longitude where p.latitude < %s and p.latitude > %s and p.longitude < %s and p.longitude > %s  ORDER BY longitude"


def all_gyms():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT g.gym_id, g.latitude, g.longitude, gymdetails.name,l.altitude FROM gym g left join gymdetails on g.gym_id=gymdetails.gym_id left join locationaltitude l on g.latitude=l.latitude and g.longitude=l.longitude;"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def update_gym_members(gym, added, removed, gym_last_previous_scan):
    if not "gym_state" in gym:
        return
    state_ = gym["gym_state"]
    fort_data_ = state_["fort_data"]
    gymid = fort_data_["id"]
    last_modified_gym = datetime.datetime.utcfromtimestamp(fort_data_["last_modified_timestamp_ms"] / 1000)
    lastScanned = datetime.datetime.utcnow()

    connection = __gymmapconnection()
    try:
        update_last_scanned_members(connection, gymid, lastScanned)
        for defender in removed:
            delete_member(connection, defender)
        for memberId, member in added.items():
            insert_gym_pokemon(connection, member["pokemon_data"])
            upsert_full_gym_member(connection, gymid, member["pokemon_data"], lastScanned, last_modified_gym,
                                   gym_last_previous_scan)
    finally:
        connection.commit()


def update_defenders(gym, added, removed, gym_last_previous_scan):
    do_with_backoff_for_deadlock(lambda: do_update_defenders(gym, added, removed, gym_last_previous_scan))


def do_update_defenders(gym, added, removed, gym_last_previous_scan):
    if not "gym_state" in gym:
        return
    state_ = gym["gym_state"]
    fort_data_ = state_["fort_data"]
    gymid = fort_data_["id"]
    last_modified_gym = datetime.datetime.utcfromtimestamp(fort_data_["last_modified_timestamp_ms"] / 1000)
    lastScanned = datetime.datetime.utcnow()

    connection = __gymmapconnection()
    try:
        update_last_scanned_defenders(connection, gymid, lastScanned)
        for defender in removed:
            delete_defender(connection, defender)
        for memberId, member in added.items():
            insert_defender(connection, gymid, lastScanned, last_modified_gym, member["pokemon_data"])
    finally:
        connection.commit()


def update_last_scanned_members(connection, gym_id, last_scanned):
    with connection.cursor() as cursor:
        sql = "UPDATE gympokemon SET last_seen = %s WHERE pokemon_uid IN (SELECT pokemon_uid FROM gymmember WHERE gym_id=%s);"
        cursor.execute(sql, (last_scanned, gym_id))
        sql = "UPDATE gymmember SET last_scanned = %s WHERE gym_id=%s;"
        cursor.execute(sql, (last_scanned, gym_id))


def update_last_scanned_defenders(connection, gym_id, last_scanned):
    with connection.cursor() as cursor:
        sql = "UPDATE defender SET last_scanned = %s WHERE gym_id=%s;"
        cursor.execute(sql, (last_scanned, gym_id))


def delete_member(connection, pokemon_uid):
    with connection.cursor() as cursor:
        sql = "DELETE FROM gympokemon WHERE pokemon_uid = %s;"
        cursor.execute(sql, (pokemon_uid))
        sql = "DELETE FROM gymmember WHERE pokemon_uid = %s;"
        cursor.execute(sql, (pokemon_uid))


def delete_defender(connection, pokemon_uid):
    with connection.cursor() as cursor:
        sql = "DELETE FROM defender WHERE pokemon_uid = %s;"
        cursor.execute(sql, (pokemon_uid))


def delete_currentmembers(connection, gym_id):
    with connection.cursor() as cursor:
        sql = "DELETE FROM gympokemon WHERE pokemon_uid IN (SELECT pokemon_uid FROM gymmember WHERE gym_id = %s);"
        cursor.execute(sql, (gym_id))
        sql = "DELETE FROM gymmember WHERE gym_id = %s;"
        cursor.execute(sql, (gym_id))


def delete_defenders(connection, gym_id):
    with connection.cursor() as cursor:
        sql = "DELETE FROM defender WHERE gym_id = %s;"
        cursor.execute(sql, (gym_id))


def delete_gym(connection, gym_id):
    with connection.cursor() as cursor:
        sql = "DELETE FROM gym WHERE gym_id = %s;"
        cursor.execute(sql, (gym_id))
        sql = "DELETE FROM gymdetails WHERE gym_id = %s;"
        cursor.execute(sql, (gym_id))


def valueOrNone(gympokemon, key):
    return gympokemon.get(key, None)


def create_or_update_gym(gymid, gym):
    connection = __gymmapconnection()
    try:
        if not gym_exists(connection, gymid):
            insert_gym(connection, gym)
        else:
            update_gym_scaninfo(connection, gym)

        if not gym_details_exists(connection, gymid):
            insert_gym_details_table(connection, gym)

        connection.commit()

    finally:
        connection.close()


def create_or_update_gym_from_gmo2(gymid, gym):
    connection = __gymmapconnection()
    try:
        if not gym_exists(connection, gymid):
            insert_gym_data(connection, gym)
            modified = True
        else:
            modified = update_gym_scaninfo_gymdata(connection, gym)

        connection.commit()
        # updating gyms not implemented yet TODO
        return modified
    finally:
        connection.close()


def gym_exists(connection, gymid):
    with connection.cursor() as cursor:
        sql = "SELECT count(*) AS count FROM gym WHERE gym_id=%s"
        cursor.execute(sql, (gymid))
        fetchall = cursor.fetchall()
        for row in fetchall:
            if row["count"] == 1: return True;
        return False


def load_spawn_point_by_id(id):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM spawnpoint WHERE id=%s;"
            cursor.execute(sql, id)
            return cursor.fetchone()
    finally:
        connection.close()


def load_spawn_point(latitude, longitude):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM spawnpoint WHERE latitude=%s AND longitude=%s"
            cursor.execute(sql, (latitude, longitude))
            return cursor.fetchone()
    finally:
        connection.close()


def db_load_spawn_points():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM spawnpoint"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def db_load_spawn_points_missing_s2():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT a.*,sp.s2cell,sp.altitude FROM spawnpoint a LEFT JOIN spawnpoints2 sp ON a.id = sp.id WHERE s2cell IS NULL"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def db_load_spawn_points_missing_altitude():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT a.*,sp.altitude FROM spawnpoint a LEFT JOIN spawnpoints2 sp ON a.id = sp.id WHERE altitude IS NULL"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def db_set_s2_cellid(spawnpoint_id, cell_id):
    connection = __gymmapconnection()

    try:
        with connection.cursor() as cursor:
            sql = 'INSERT INTO spawnpoints2(id, s2cell) VALUES (%s, %s)'
            cursor.execute(sql, (spawnpoint_id, cell_id))
        connection.commit()
    finally:
        connection.close()


def db_set_altitude(spawnpoint_id, altitude):
    connection = __gymmapconnection()

    try:
        with connection.cursor() as cursor:
            sql = 'update spawnpoints2 set altitude=%s where id=%s'
            cursor.execute(sql, (altitude, spawnpoint_id))
        connection.commit()
    finally:
        connection.close()


def member_exists(connection, pokemon_uid):
    with connection.cursor() as cursor:
        sql = "SELECT count(*) AS count FROM gymmember WHERE pokemon_uid=%s"
        cursor.execute(sql, (pokemon_uid))
        fetchall = cursor.fetchall()
        for row in fetchall:
            if row["count"] == 1: return True;
        return False


def defender_exists(connection, pokemon_uid):
    with connection.cursor() as cursor:
        sql = "SELECT count(*) AS count FROM defender WHERE pokemon_uid=%s"
        cursor.execute(sql, (pokemon_uid))
        fetchall = cursor.fetchall()
        for row in fetchall:
            if row["count"] == 1: return True;
        return False


def gym_details_exists(connection, gymid):
    with connection.cursor() as cursor:
        sql = "SELECT count(*) AS count FROM gymdetails WHERE gym_id=%s"
        cursor.execute(sql, (gymid))
        fetchall = cursor.fetchall()
        for row in fetchall:
            if (row["count"] == 1): return True;
        return False


def update_gym_scaninfo(connection, gym):
    last_scanned = datetime.datetime.utcnow()

    data_ = gym.gym_status_and_defenders.pokemon_fort_proto
    gym_id_ = data_.id
    with connection.cursor() as cursor:
        sql = "UPDATE gym SET last_scanned=%s,last_modified=%s WHERE gym_id=%s"
        last_mod = data_.last_modified_timestamp_ms
        last_modified_gym = datetime.datetime.utcfromtimestamp(last_mod / 1000)

        values = (last_scanned, last_modified_gym, gym_id_)
        cursor.execute(sql, values)


def update_gym_scaninfo_gymdata(connection, data_):
    last_scanned = datetime.datetime.utcnow()

    gym_id_ = data_.id
    team_id = data_.owned_by_team
    guard_pokemon_id = data_.guard_pokemon_id
    last_modified = datetime.datetime.utcfromtimestamp(data_.last_modified_timestamp_ms / 1000)

    with connection.cursor() as cursor:
        sql = "SELECT last_modified FROM gym WHERE gym_id=%s"
        cursor.execute(sql, gym_id_)
        fetchone = cursor.fetchone()
        if fetchone and last_modified == fetchone["last_modified"]:
            sql = "UPDATE gym SET last_scanned=%s WHERE gym_id=%s"
            cursor.execute(sql, (last_scanned, gym_id_))
            return False
        else:
            sql = "UPDATE gym SET last_scanned=%s,last_modified=%s,team_id=%s,guard_pokemon_id=%s WHERE gym_id=%s"
            values = (last_scanned, last_modified, team_id, guard_pokemon_id, gym_id_)
            cursor.execute(sql, values)

            if team_id == 0:
                delete_currentmembers(connection, gym_id_)
                delete_defenders(connection, gym_id_)
            return True


def insert_gym(connection, gym):
    data_ = gym["gym_state"]["fort_data"]
    insert_gym_data(connection, data_)


def insert_gym_data(connection, data_):
    gym_id_ = data_["id"]
    team_id = data_.get("owned_by_team", 0)
    gym_points = data_.get("gym_points", 0)
    guard_pokemon_id = data_.get("guard_pokemon_id", 0)
    enabled = data_["enabled"]
    latitude = data_["latitude"]
    longitude = data_["longitude"]
    last_modified = datetime.datetime.utcfromtimestamp(data_["last_modified_timestamp_ms"] / 1000)
    last_seen = datetime.datetime.utcnow()

    with connection.cursor() as cursor:
        sql = "INSERT INTO gym(gym_id, team_id, guard_pokemon_id ,gym_points ," \
              "enabled,latitude ,gymscanner,longitude,last_modified,last_scanned)" \
              " VALUES (%s,%s,%s,%s," \
              "%s,%s,%s,%s,%s,%s);"
        values = (
            gym_id_, team_id, guard_pokemon_id, gym_points, enabled, latitude, "1", longitude, last_modified, last_seen)
        cursor.execute(sql, values)


def insert_gym_details_table(connection, gym_get_info):
    state_ = gym_get_info.gym_status_and_defenders
    data_ = state_.pokemon_fort_proto
    gym_id_ = data_.id
    name = gym_get_info.name
    description = gym_get_info.description
    url = gym_get_info.url
    last_seen = datetime.datetime.utcnow()

    with connection.cursor() as cursor:
        sql = "INSERT INTO gymdetails(gym_id, `name`, description, url, last_scanned) VALUES (%s,%s,%s,%s,%s);"
        values = (gym_id_, name, description, url, last_seen)
        cursor.execute(sql, values)


def insert_gym_pokemon(connection, gympokemon):
    pokemon_uid_ = gympokemon["id"]
    pokemon_id = gympokemon["pokemon_id"]
    cp = gympokemon["cp"]
    owner_name = gympokemon["owner_name"]
    num_upgrades = valueOrNone(gympokemon, "num_upgrades")
    move_1 = gympokemon["move_1"]
    move_2 = gympokemon["move_2"]
    height = gympokemon["height_m"]
    weight = gympokemon["weight_kg"]
    stamina = gympokemon["stamina"]
    stamina_max = gympokemon["stamina_max"]
    cp_multiplier = gympokemon["cp_multiplier"]

    additional_cp_multiplier = valueOrNone(gympokemon, "additional_cp_multiplier")
    iv_attack = valueOrNone(gympokemon, "individual_attack")
    iv_defense = valueOrNone(gympokemon, "individual_defense")
    iv_stamina = valueOrNone(gympokemon, "individual_stamina")
    last_seen_long = gympokemon["creation_time_ms"]
    #        last_seen = datetime.datetime.fromtimestamp(last_seen_long)
    last_seen = datetime.datetime.utcnow()

    with connection.cursor() as cursor:
        sql = "INSERT INTO gympokemon(pokemon_uid, pokemon_id, cp, trainer_name, num_upgrades, move_1, move_2, " \
              "height,weight, stamina, stamina_max,cp_multiplier, additional_cp_multiplier, " \
              "iv_attack, iv_defense, iv_stamina, last_seen ) " \
              "VALUES (%s,%s,%s,%s,%s,%s,%s," \
              "%s, %s, %s, %s, %s, %s," \
              "%s, %s, %s, %s);"
        values = (pokemon_uid_, pokemon_id, cp, owner_name, num_upgrades, move_1, move_2,
                  height, weight, stamina, stamina_max, cp_multiplier, additional_cp_multiplier,
                  iv_attack, iv_defense, iv_stamina, last_seen)
        try:
            cursor.execute(sql, values)
        except pymysql.err.IntegrityError:
            sql = "DELETE FROM gympokemon WHERE pokemon_uid=%s;"
            cursor.execute(sql, (pokemon_uid_))
            insert_gym_pokemon(connection, gympokemon)


def insert_defender(connection, gym_id, last_scanned, last_modified_gym, gympokemon):
    pokemon_uid_ = gympokemon["id"]
    pokemon_id = gympokemon["pokemon_id"]
    cp = gympokemon["cp"]
    owner_name = gympokemon["owner_name"]
    num_upgrades = valueOrNone(gympokemon, "num_upgrades")
    move_1 = gympokemon["move_1"]
    move_2 = gympokemon["move_2"]
    height = gympokemon["height_m"]
    weight = gympokemon["weight_kg"]
    stamina = gympokemon["stamina"]
    stamina_max = gympokemon["stamina_max"]
    cp_multiplier = gympokemon["cp_multiplier"]

    additional_cp_multiplier = valueOrNone(gympokemon, "additional_cp_multiplier")
    iv_attack = valueOrNone(gympokemon, "individual_attack")
    iv_defense = valueOrNone(gympokemon, "individual_defense")
    iv_stamina = valueOrNone(gympokemon, "individual_stamina")
    # todo: set last_no_present from gym last scanned date
    with connection.cursor() as cursor:
        sql = "INSERT INTO defender(gym_id, pokemon_uid, pokemon_id, cp, trainer_name, num_upgrades, move_1, move_2, " \
              "height,weight, stamina, stamina_max,cp_multiplier, additional_cp_multiplier, " \
              "iv_attack, iv_defense, iv_stamina, first_seen, last_modified, last_scanned) " \
              "VALUES (%s,%s,%s,%s,%s,%s,%s,%s," \
              "%s, %s, %s, %s, %s, %s," \
              "%s, %s, %s, %s, %s, %s);"
        values = (gym_id, pokemon_uid_, pokemon_id, cp, owner_name, num_upgrades, move_1, move_2,
                  height, weight, stamina, stamina_max, cp_multiplier, additional_cp_multiplier,
                  iv_attack, iv_defense, iv_stamina, last_modified_gym, last_modified_gym, last_scanned)
        try:
            cursor.execute(sql, values)
        except pymysql.err.IntegrityError:
            sql = "DELETE FROM defender WHERE pokemon_uid=%s;"
            cursor.execute(sql, (pokemon_uid_))
            insert_defender(connection, gym_id, last_scanned, last_modified_gym, gympokemon)


def insert_gym_member(connection, gymid, member, last_scanned):
    pokemon_id = member["id"]

    with connection.cursor() as cursor:
        sql = "INSERT INTO gymmember(gym_id, pokemon_uid, last_scanned ) VALUES (%s,%s,%s);"
        values = (gymid, pokemon_id, last_scanned)
        cursor.execute(sql, values)


def upsert_full_gym_member(connection, gymid, member, last_scanned, first_seen, last_no_present):
    pokemon_id = member["id"]

    with connection.cursor() as cursor:
        if member_exists(connection, pokemon_id):
            sql = "UPDATE gymmember SET gym_id=%s,last_scanned=%s WHERE pokemon_uid=%s;"
            values = (gymid, last_scanned, pokemon_id)
        else:
            sql = "INSERT INTO gymmember(gym_id, pokemon_uid, last_scanned, first_seen, last_no_present ) VALUES (%s,%s,%s,%s,%s);"
            values = (gymid, pokemon_id, last_scanned, first_seen, last_no_present)
        cursor.execute(sql, values)


def dbSetLastModified(gymId, lastScanned, lastModified):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE gym SET LAST_MODIFIED=%s, LAST_SCANNED=%s WHERE gym_id=%s;"
            values = (lastModified, lastScanned, gymId)
            cursor.execute(sql, values)
            connection.commit()
    finally:
        connection.close()


def dbSetLastScanned(gymId, lastScanned):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE gym SET LAST_SCANNED=%s WHERE gym_id=%s;"
            values = (lastScanned, gymId)
            cursor.execute(sql, values)
            connection.commit()
    finally:
        connection.close()


# stolen from gymanalyzer
def member_map():
    return make_gym_map(member_list())


# stolen from gymanalyzer
def member_list():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT gd.name,g.gym_points,g.latitude,g.longitude,g.team_id,move_1,trainer_name,gp.pokemon_id,gp.pokemon_uid,gp.cp,gp.iv_attack," \
                  "gp.iv_defense, gp.iv_stamina,g.last_modified,g.last_scanned,gm.last_scanned AS gym_member_last_scanned, g.gym_id " \
                  "FROM gympokemon gp, gymdetails gd, gym g,gymmember gm " \
                  "WHERE gp.pokemon_uid=gm.pokemon_uid AND gm.gym_id=g.gym_id AND gd.gym_id=g.gym_id ORDER BY gym_id,cp";
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def defender_map():
    return make_gym_map(defender_list())


def defender_list():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT g.name,g.gym_points,g.latitude,g.longitude,g.team_id,move_1,trainer_name,gm.pokemon_id,gm.pokemon_uid,gm.cp,gm.iv_attack," \
                  "gm.iv_defense, gm.iv_stamina,g.last_modified,g.last_scanned,gm.last_scanned AS gym_member_last_scanned, g.gym_id " \
                  "FROM gymview g,defender gm " \
                  "WHERE g.gym_id=gm.gym_id ORDER BY latitude";
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def gymcoordinates():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT gd.name,g.latitude,g.longitude,g.gym_id FROM gym g,gymdetails gd WHERE g.gym_id = gd.gym_id ORDER BY latitude;";
            cursor.execute(sql)
            result = cursor.fetchall()
            for gym in result:
                gym["coordinates"] = (gym["latitude"], gym["longitude"])
            return result
    finally:
        connection.close()


def most_recent_trainer_gyms(trainer_name):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            # and g.gymscanner=1
            sql = "SELECT gym_id,latitude,longitude,last_modified FROM gymlog WHERE trainer_name = %s ORDER BY last_modified DESC";
            cursor.execute(sql, (trainer_name))
            result = cursor.fetchall()
            for gym in result:
                gym["coordinates"] = (gym["latitude"], gym["longitude"])
            return result
    finally:
        connection.close()


def gymscannercoordinates():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            # and g.gymscanner=1
            sql = "SELECT gd.name,g.latitude,g.longitude,g.gym_id FROM gym g LEFT JOIN gymdetails AS gd ON g.gym_id = gd.gym_id ORDER BY longitude;";
            cursor.execute(sql)
            result = cursor.fetchall()
            for gym in result:
                gym["coordinates"] = (gym["latitude"], gym["longitude"])
            return result
    finally:
        connection.close()


def spawnpoints():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT id,latitude,longitude FROM spawnpoint ORDER BY longitude"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def spawnpoints_in_box(fencebox):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "select p.*,l.altitude from " \
                  "spawnpoint p left join locationaltitude " \
                  "l on p.latitude=l.latitude and p.longitude=l.longitude where p.latitude < %s and p.latitude > %s and p.longitude < %s and p.longitude > %s  ORDER BY longitude"
            cursor.execute(sql, (fencebox[0][0], fencebox[1][0], fencebox[1][1], fencebox[0][1]))
            return cursor.fetchall()
    finally:
        connection.close()


def gyms_in_box(fencebox):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "select p.*,l.altitude from " \
                  "gym p left join locationaltitude " \
                  "l on p.latitude=l.latitude and p.longitude=l.longitude where p.latitude < %s and p.latitude > %s and p.longitude < %s and p.longitude > %s  ORDER BY longitude"
            cursor.execute(sql, (fencebox[0][0], fencebox[1][0], fencebox[1][1], fencebox[0][1]))
            return cursor.fetchall()
    finally:
        connection.close()


def pokestops_in_box(fencebox):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "select p.*,l.altitude from " \
                  "pokestop p left join locationaltitude " \
                  "l on p.latitude=l.latitude and p.longitude=l.longitude where p.latitude < %s and p.latitude > %s and p.longitude < %s and p.longitude > %s  ORDER BY longitude"
            cursor.execute(sql,(fencebox[0][0], fencebox[1][0], fencebox[1][1], fencebox[0][1]))
            return cursor.fetchall()
    finally:
        connection.close()


def pokestops_in_box_2(fencebox):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "select p.*,l.altitude from (select pokestop_id,latitude,longitude from pokestop union  select gym_id as pokestop_id,latitude,longitude from gym ) as p left join locationaltitude l on p.latitude=l.latitude and p.longitude=l.longitude  where "\
                  "p.latitude < %s and p.latitude > %s and p.longitude < %s and p.longitude > %s   ORDER BY longitude"
            cursor.execute(sql,(fencebox[0][0], fencebox[1][0], fencebox[1][1], fencebox[0][1]))
            return cursor.fetchall()
    finally:
        connection.close()


def pokestops():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "select p.*,l.altitude from pokestop p left join locationaltitude l on p.latitude=l.latitude and p.longitude=l.longitude ORDER BY longitude"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()



def altitudes(topleft, bottomright):
    connection = __gymmapconnection()
    sql = "select latitude,longitude,altitude from locationaltitude where " \
          "latitude > %s and latitude < %s and longitude > %s and longitude < %s"
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, (bottomright[0], topleft[0], topleft[1], bottomright[1]))
            return cursor.fetchall()
    finally:
        connection.close()


def insert_altitude(cellid, latitude, longitude, altitude):
    connection = __gymmapconnection()
    sql = "insert into locationaltitude(cellid, latitude,longitude,altitude) values (%s, %s,%s,%s)"
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, (cellid, latitude, longitude, altitude))
            connection.commit()
    except IntegrityError:
        pass
    finally:
        connection.close()

def pokestops_by_latitude():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT pokestop_id,latitude,longitude FROM pokestop ORDER BY latitude"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def pokemon_location(encounter_id):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT latitude,longitude FROM pokemon WHERE encounter_id=%s"
            cursor.execute(sql, (encounter_id))
            fetchone = cursor.fetchone()
            if fetchone:
                return fetchone["latitude"], fetchone["longitude"]
    finally:
        connection.close()


def pokestop_coordinates(pokestop_id):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT latitude,longitude FROM pokestop WHERE pokestop_id=%s"
            cursor.execute(sql, (pokestop_id))
            fetchone = cursor.fetchone()
            return fetchone["latitude"], fetchone["longitude"]
    finally:
        connection.close()


def spawns(after):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT spawnpoint_id,pokemon_id FROM pokemon WHERE disappear_time > %s"
            cursor.execute(sql, (after))
            return cursor.fetchall()
    finally:
        connection.close()


def defenderIds(gymid):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT gp.pokemon_uid FROM gympokemon gp, gymdetails gd, gym g,gymmember gm " \
                  "WHERE gp.pokemon_uid=gm.pokemon_uid AND gm.gym_id=g.gym_id AND gd.gym_id=g.gym_id AND g.gym_id=%s";
            cursor.execute(sql, (gymid))
            result = cursor.fetchall()
            resp = []
            for row in result:
                uid_ = int(row["pokemon_uid"])
                resp.append(uid_)

            return resp
    finally:
        connection.close()


def singlegym(gymid):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT gd.name,g.gym_points,g.latitude,g.longitude,g.team_id,trainer_name,gp.pokemon_id,gp.pokemon_uid,gp.cp,gp.iv_attack," \
                  "gp.iv_defense, gp.iv_stamina,g.last_modified,g.last_scanned,gm.last_scanned AS gym_member_last_scanned, g.gym_id " \
                  "FROM gympokemon gp, gymdetails gd, gym g,gymmember gm " \
                  "WHERE gp.pokemon_uid=gm.pokemon_uid AND gm.gym_id=g.gym_id AND gd.gym_id=g.gym_id AND g.gym_id=%s";
            cursor.execute(sql, (gymid))
            result = cursor.fetchall()
            return single_gym_map(result, gymid)
    finally:
        connection.close()


def gym_names():
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT g.gym_id,g.latitude,g.longitude,gd.name FROM gymdetails gd, gym g WHERE gd.gym_id=g.gym_id"
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def singlegym_Defenders(gymid):
    connection = __gymmapconnection()
    try:
        with connection.cursor() as cursor:
            # Read a single record
            sql = "SELECT g.name,g.gym_points,g.latitude,g.longitude,g.team_id,trainer_name,d.pokemon_id,d.pokemon_uid,d.cp,d.iv_attack," \
                  "d.iv_defense, d.iv_stamina,d.last_modified,d.last_scanned, g.gym_id " \
                  "FROM defender d, gymview g " \
                  "WHERE d.gym_id=g.gym_id AND g.gym_id=%s";
            cursor.execute(sql, (gymid))
            result = cursor.fetchall()
            return single_gym_map(result, gymid)
    finally:
        connection.close()


def single_gym_map(result, gym_id):
    gym = {"defenders": {}}
    counter = 0
    for row in result:
        uid_ = int(row["pokemon_uid"])
        gym["defenders"][uid_] = row
        gym["last_modified"] = row["last_modified"]
        gym["last_scanned"] = row["last_scanned"]
        counter += 1
    if counter > 10:
        print("gym " + gym_id + " has " + str(counter) + "members")
        connection = __gymmapconnection()
        try:
            delete_currentmembers(connection, gym_id)
            connection.commit()
        finally:
            connection.close()
        gym = {"defenders": {}}
    return gym


def make_gym_map(result):
    gyms = {}
    for row in result:
        trainer_name_ = row["trainer_name"]
        row_name_ = row["name"]
        gym_id_ = row["gym_id"]
        if not gym_id_ in gyms:
            fields = {"trainers": {}}
            gyms[gym_id_] = fields
        else:
            fields = gyms[gym_id_]
        fields["last_modified"] = row["last_modified"]
        fields["trainers"][trainer_name_] = row
    return gyms


def make_gym_map_v2(result):
    gyms = {}
    for row in result:
        trainer_name_ = row["trainer_name"]
        row_name_ = row["name"]
        gym_id_ = row["gym_id"]
        if not gym_id_ in gyms:
            fields = {"defenders": []}
            gyms[gym_id_] = fields
        else:
            fields = gyms[gym_id_]
        fields["last_modified"] = row["last_modified"]
        fields["defenders"].append(row)
    return gyms

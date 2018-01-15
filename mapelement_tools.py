import codecs
import logging
import os
import unittest
from datetime import datetime as dt, timedelta

from mapelements import Pokestop, RouteElement, SpawnPoints, GymElement, ElementType
from mapelements import SpawnPoint

try:
    from exceptions import ValueError
except ImportError: # will be 3.x series
    pass
from itertools import islice

dirname = os.path.dirname(os.path.realpath(__file__))


from geography import step_position, center_geolocation, box_around, move_towards
from gymdbsql import spawnpoints_in_box, insert_altitude, altitudes
from pogom.fnord_altitude import with_gmaps_altitude
from pogom.utils import cellid
from scannerutil import equi_rect_distance_m, second_of_hour

log = logging.getLogger(__name__)


def create_pokestop(stop):
    latitude_ = stop["latitude"]
    longitude_ = stop["longitude"]
    altitude_ = stop["altitude"]
    return Pokestop(stop["pokestop_id"], latitude_, longitude_, altitude_)


def create_elem(id, type, lat, lng, alt):
    if type == "P":
        return Pokestop(id, lat, lng, alt)
    if type == "S":
        return SpawnPoint.create(id, lat, lng, alt)
    if type == "G":
        return GymElement.create(id, lat, lng, alt)
    raise "Element type {} not known".format(type)


def load_map_elements(inputFile, sep=",", commentaryMarker="#"):
    data = []
    with codecs.open(dirname + "/routes/" + inputFile, 'r', 'utf-8') as f:
        for line in f:
            line = line.strip()
            if len(line) < 1 or line[0] == commentaryMarker:
                continue
            parts = line.split(sep)
            id = parts[0]
            type = parts[1]
            lat = float(parts[2])
            lon = float(parts[3])
            alt = float(parts[4]) if parts[4] != "None" else 5.5  # todo. Look at this
            data.append(create_elem(id, type, lat, lon, alt))
    return data

def create_spawnpoint(point):
    return SpawnPoint.create(point.id, point[0], point[1], point[2])


def add_altitudes(stops, gmaps_key):
    added = 0
    for stop in stops:
        if stop["altitude"] is None:
            pos = (stop["latitude"], stop["longitude"])
            RADIUS = 70.0
            topleft_box = step_position(pos, RADIUS, -RADIUS)
            bottomright_box = step_position(pos, -RADIUS, RADIUS)
            altitude_candidates = altitudes(topleft_box, bottomright_box)
            if len(altitude_candidates) > 0:
                stop["altitude"] = altitude_candidates[0]["altitude"]
                insert_altitude(cellid(pos), pos[0], pos[1], altitude_candidates[0]["altitude"])
                added += 1
            else:
                pos = with_gmaps_altitude(pos, gmaps_key)
                stop["altitude"] = pos[2]
                insert_altitude(cellid(pos), pos[0], pos[1], pos[2])
    if added > 0:
        log.info("Found {} altitudes by approximating DB data, {} total stops".format(str(added), str(len(stops))))
    return stops


def create_pokestop_model(stops_to_check, args, radius=39):
    add_altitudes(stops_to_check, args.gmaps_key)
    point_list = create_pokestops(stops_to_check)
    update_distances(point_list, radius)
    return point_list


def create_spawnpoint_model(stops_to_check, args, radius=39):
    add_altitudes(stops_to_check, args.gmaps_key)
    point_list = create_spawnpoints(stops_to_check)
    update_distances(point_list, radius)
    return point_list


def create_spawnpoints(stops_to_check):
    point_list = []
    for stop in stops_to_check:
        pokestop = create_spawnpoint(stop)
        point_list.append(pokestop)
    return point_list

def create_pokestops(stops_to_check):
    point_list = []
    for stop in stops_to_check:
        pokestop = create_pokestop(stop)
        point_list.append(pokestop)
    return point_list

def filter_map_elements(map_elements, type):
    return [f for f in map_elements if f.element_type() == type]

def fence_elements(map_elements, fence):
    return fence.filter_forts(map_elements)


def pokestops_in_fence(file, fence):
    me = load_map_elements(file)
    result = [f for f in me if f.element_type() == ElementType.POKESTOP and fence.contains_fort(f)]
    return result

def spawnpoints_in_fence(file, fence):
    me = load_map_elements(file)
    result = [f for f in me if f.element_type() == ElementType.POKESTOP and fence.contains_fort(f)]
    return result


def update_distances(point_list, radius=39):
    distance = 2 * radius
    for idx, point in enumerate(point_list):
        if idx % 500 == 0:
            print("Processing point at index " + str(idx))
        cutoff_long = step_position(point.coords, 0, distance)
        for point2 in islice(point_list, idx + 1, None):
            point_longitude = point2.coords[1]
            if point_longitude > cutoff_long[1]:
                break
            point.add_neighbours(point2, distance)


def find_largest_stop_group(stops):
    result = 0
    for poke_stop in stops:
        result = max(result, len(poke_stop.collected_neighbours()))
    return result


def find_largest_groups(point_list, min_size=3):
    all_coords = {}
    for stop in point_list:
        all_coords[stop.coords] = stop

    result_coords = []
    num_stops_found = 0
    max_stop_group = find_largest_stop_group(point_list)
    for counter in range(max_stop_group, min_size - 1, -1):
        for poke_stop_ in point_list:
            intersected_ = poke_stop_.collected_neighbours()
            if len(intersected_) == counter and poke_stop_.coords in all_coords:
                locations = [n.coords for n in intersected_]
                re = RouteElement(center_geolocation(locations), poke_stop_.collected_neighbours())
                result_coords.append(re)
                num_stops_found += len(locations)
                for location in locations:
                    if location in all_coords:
                        del all_coords[location]
                # clear out neighbours so they dont contribute to further collected_neighhbours
                for stop in intersected_:
                    stop.neighbours = []
    log.info("Found {} stops".format(str(num_stops_found)))
    return result_coords



def find_optimal_location(stop_coords, gmaps_key, spin_range=38.5, catch_range=20):
    stop_box = box_around(stop_coords, spin_range + catch_range)
    sp = spawnpoints_in_box(stop_box)
    add_altitudes(sp, gmaps_key)
    points = SpawnPoint.from_db_rows(sp)
    in_range_of_stop = [p for p in points if p.is_within_range(stop_coords, spin_range + catch_range)]
    for idx, x in enumerate(in_range_of_stop):
        for n in points[idx + 1:]:
            x.add_neighhbours(n, 60)

    z = 0
    curr = None
    for x in in_range_of_stop:
        num_neigh = x.collected_neighbours()
        if num_neigh > z:
            curr = x
            z = num_neigh
    if not curr:
        return ()
    neighbours = curr.collected_neighbours()
    max_spawns = center_geolocation([x.location() for x in neighbours])

    m = equi_rect_distance_m(max_spawns, stop_coords)
    if m > spin_range:
        max_spawns = move_towards(max_spawns, stop_coords, m - spin_range)

    distance = equi_rect_distance_m(max_spawns, stop_coords)

    return max_spawns, len(neighbours), distance

class SpawnPoint_duration_test(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 600,
                 "earliest_unseen": 700, "s2cell": 1234, "altitude": 40}
        self.assertEqual(1800, SpawnPoint(point).duration())
        point["kind"] = "hhhs"
        self.assertEqual(900, SpawnPoint(point).duration())
        point["kind"] = "hshs"
        self.assertEqual(2700, SpawnPoint(point).duration())


class SpawnpointCouldHaveSpawned(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 3400,
                 "earliest_unseen": 3500, "s2cell": 1234, "altitude": 40}
        self.assertEqual((1600, 1700), SpawnPoint(point).startwindow())  # 26:40->28:20

        spawn_point = SpawnPoint(point)
        unseen = dt(2016, 12, 1, 2, 25, 0)
        seen = dt(2016, 12, 1, 2, 27, 0)
        self.assertTrue(spawn_point.could_have_spawned(unseen, seen))

        unseen = dt(2016, 12, 1, 2, 27, 30)
        seen = dt(2016, 12, 1, 2, 27, 30)
        self.assertFalse(spawn_point.could_have_spawned(unseen, seen))  # not really a use case

        outside_unseen = dt(2016, 12, 1, 2, 39, 0)
        outside_seen = dt(2016, 12, 1, 2, 30, 0)
        self.assertFalse(spawn_point.could_have_spawned(outside_unseen, outside_seen))


class SpawnPoint_Could_Have_Spawned_Wrapping_Hour(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 1680,
                 "earliest_unseen": 1680, "s2cell": 1234, "altitude": 40}

        spawn_point = SpawnPoint(point)
        unseen = dt(2016, 12, 1, 2, 2, 0)
        expanded_start_window = unseen - timedelta(minutes=5)

        self.assertTrue(spawn_point.could_have_spawned_soh(second_of_hour(expanded_start_window), 159))


# Pokeomn 63 in window 78-159 with185/1153/1638/1909/2170/2364/2389/2616/2890/3046/3490/
class SpawnpointsCouldHaveSpawned(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 3400,
                 "earliest_unseen": 3500, "s2cell": 1234, "altitude": 40}
        point2 = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 1900,
                  "earliest_unseen": 2000, "s2cell": 1234, "altitude": 40}

        spawn_point = SpawnPoint(point)  # 1600-1700 26:40-28:30
        print(spawn_point.startwindow())
        spawn_point2 = SpawnPoint(point2)  # 100-200   1:40-3:20
        print(spawn_point2.startwindow())
        points = SpawnPoints([spawn_point, spawn_point2])
        unseen = dt(2016, 12, 1, 2, 25, 0)
        seen = dt(2016, 12, 1, 2, 27, 0)
        self.assertEqual(1, len(points.points_that_can_spawn(unseen, seen)))
        unseen2 = dt(2016, 12, 1, 2, 2, 0)
        seen2 = dt(2016, 12, 1, 2, 3, 30)
        self.assertEqual(1, len(points.points_that_can_spawn(unseen2, seen2)))


class SpawnpointsExpandedStartWindow(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 3400,
                 "earliest_unseen": 3500, "s2cell": 1234, "altitude": 40}
        point2 = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 3200,
                  "earliest_unseen": 3200, "s2cell": 1234, "altitude": 40}
        point3 = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 2800,
                  "earliest_unseen": 2800, "s2cell": 1234, "altitude": 40}

        spawn_point = SpawnPoint(point)  # 1600-1700 26:40-28:30
        print(spawn_point.startwindow())
        spawn_point2 = SpawnPoint(point2)  # 100-200   1:40-3:20
        print(spawn_point2.startwindow())
        spawn_point3 = SpawnPoint(point3)  # 100-200   1:40-3:20
        print(spawn_point3.startwindow())
        points = SpawnPoints([spawn_point, spawn_point2, spawn_point3])
        unseen = dt(2016, 12, 1, 2, 25, 0)
        seen = dt(2016, 12, 1, 2, 27, 0)
        self.assertEqual(1, len(points.points_that_can_spawn(unseen, seen)))
        self.assertEqual(2, len(points.search_points_for_runner(unseen, seen)))


class OverlapTest(unittest.TestCase):
    def test(self):
        spawn_point_time = (20, 40)

        inside = (21, 39)
        around = (19, 41)
        tangenting = (0, 20)  # Unsure if this is important. Should probably add 1 sec to spawn point window anyway
        outsidebefore = (0, 19)
        outsideafter = (41, 50)

        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 600,
                 "earliest_unseen": 700, "s2cell": 1234, "altitude": 40}
        spawn_point = SpawnPoint(point)  # start window 2400-2500 40:0-41:40
        print(str(spawn_point))
        # todo: think very hard about what to do when spawn point uncertainty > obeservation window (spawn point time fully contained in obs)
        # self.assertTrue(spawn_point.overlaps(inside, spawn_point_time))
        self.assertFalse(spawn_point.overlaps(outsidebefore, spawn_point_time))
        self.assertFalse(spawn_point.overlaps(outsideafter, spawn_point_time))
        self.assertTrue(spawn_point.overlaps(around, spawn_point_time))


class SpawnpointStartwindowTest(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 3400,
                 "earliest_unseen": 3500, "s2cell": 1234, "altitude": 40}
        self.assertEqual((1600, 1700), SpawnPoint(point).startwindow())
        point["kind"] = "hhhs"
        self.assertEqual((2500, 2600), SpawnPoint(point).startwindow())
        point["kind"] = "hshs"
        self.assertEqual((700, 800), SpawnPoint(point).startwindow())


class SpawnPoint_startwindow_wrapping_test(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 600,
                 "earliest_unseen": 700, "s2cell": 1234, "altitude": 40}
        self.assertEqual((2400, 2500), SpawnPoint(point).startwindow())
        point["kind"] = "hhhs"
        self.assertEqual((3300, 3400), SpawnPoint(point).startwindow())
        point["kind"] = "hshs"
        self.assertEqual((1500, 1600), SpawnPoint(point).startwindow())


class SpawnPoint_expires_at(unittest.TestCase):
    def test(self):
        point = {"id": 123, "latitude": 43.2, "longitude": 48.6, "kind": "hhss", "links": "hh??", "latest_seen": 600,
                 "earliest_unseen": 700, "s2cell": 1234, "altitude": 40}
        print(str(SpawnPoint(point).expires_at()))

class TestRouteElement(unittest.TestCase):
    def test(self):
        p1 = Pokestop("23abc",59,10,2)
        p2 = Pokestop(24,59.1,10.1,2.1)
        pos = (17.0, 1.0, 2.0)
        re = RouteElement(pos, [p1, p2])
        as_tuple = re.as_tuple()
        print(as_tuple)
        r2 = RouteElement.from_tuple(as_tuple)
        self.assertEqual(p1, r2.pokestops[0])
        self.assertEqual(p2, r2.pokestops[1])
        self.assertEqual(pos, r2.position)



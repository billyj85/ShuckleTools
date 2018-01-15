import unittest
from datetime import datetime as dt, timedelta

import math
from enum import Enum


def second_of_hour(time):
    return time.minute * 60 + time.second

# Return equirectangular approximation distance in m.
def equi_rect_distance_m(loc1, loc2):
    r = 6371  # Radius of the earth in km.
    lat1 = math.radians(loc1[0])
    lat2 = math.radians(loc2[0])
    x = (math.radians(loc2[1]) - math.radians(loc1[1])
         ) * math.cos(0.5 * (lat2 + lat1))
    y = lat2 - lat1
    return (r * math.sqrt(x * x + y * y)) * 1000

class ElementType(Enum):
     SPAWNPOINT = 1
     POKESTOP = 2
     GYM = 3


class SpawnPoints:
    def __init__(self, spawnpoints):
        self.spawnpoints = sorted(spawnpoints, key=lambda spawnpoint: spawnpoint.start())

    def points_that_can_spawn(self, last_not_seen_time, seen_time):
        return [x for x in self.spawnpoints if x.could_have_spawned(last_not_seen_time, seen_time)]

    def all_matching_spanwpoints(self, seen_at):
        return [x for x in self.spawnpoints if x.spawns_at(seen_at)]

    def search_points_for_runner(self, last_not_seen_time, seen_time):
        expanded_start_window = last_not_seen_time - timedelta(minutes=5)
        first_window = [x for x in self.spawnpoints if x.could_have_spawned(expanded_start_window, seen_time)]
        if len(first_window) > 0:
            return first_window
        expanded_start_window = last_not_seen_time - timedelta(minutes=10)
        return [x for x in self.spawnpoints if x.could_have_spawned(expanded_start_window, seen_time)]

    def spawn_point(self, spawn_point_id):
        for spawnpoint in self.spawnpoints:
            if spawnpoint.id == spawn_point_id:
                return spawnpoint

    def explain(self, pokemon_id, last_not_seen_time, seen_time):
        result = "Pokeomn {} in window {}-{} with".format(str(pokemon_id), str(second_of_hour(last_not_seen_time)),
                                                          str(second_of_hour(seen_time)))
        for spawnpoint in self.spawnpoints:
            result += str(spawnpoint.start())
            result += "/"
        return result

    def __str__(self):
        result = ""
        for spawnpoint in self.spawnpoints:
            result += str(spawnpoint)
            result += " "
        return result


class MapElement(object):
    def __init__(self, element_id, latitude, longitude, altitude):
        self.id = element_id
        if altitude is None:
            raise ValueError
        self.coords = (latitude, longitude, altitude)
        self.neighbours = []

    def __str__(self):
        return self.id

    def __repr__(self):
        return self.__str__()

    def element_type(self):
        raise NotImplementedError("This is an abstract method.")

    def __getitem__(self, key):
        if key == 0 or key == "lat" or key == "latitude":
            return self.coords[0]
        if key == 1 or key == "lon" or key == "longitude":
            return self.coords[1]
        if key == 2 or key == "altitude":
            return self.coords[2]

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def add_neighbour(self, neighbour):
        self.neighbours.append(neighbour)

    def neighbours_with_self(self):
        neighbours = self.neighbours[:]
        neighbours.append(self)
        return neighbours

    def intersected_with(self, other):
        return list(set(self.neighbours_with_self()) & set(other))

    def collected_neighbours(self):
        current_result = self.neighbours_with_self()
        copy = current_result[:]
        for neightbour in copy:
            current_result = neightbour.intersected_with(current_result)
        return current_result

    def is_within_range(self, other, m):
        return equi_rect_distance_m(self.coords, other.coords) <= m

    def add_neighbours(self, otherpokestop, distance_requirement):
        if otherpokestop == self:
            return
        if self.is_within_range(otherpokestop, distance_requirement):
            self.neighbours.append(otherpokestop)
            otherpokestop.neighbours.append(self)

    def print_gmaps_coordinates(self):
        intersected_ = self.collected_neighbours()
        if len(intersected_) >= 2:
            print("{} neighbours @ https://www.google.com/maps/?daddr={},{}".format(
                len(intersected_), str(self.coords[0]), str(self.coords[1])))
            return True
        else:
            return False

    def gpx_string(self):
        """  <trkpt lat="47.644548" lon="-122.326897">"""
        combined_ = "<trkpt lat='" + str(self.coords[0]) + "' lon='" + str(self.coords[1]) + "'"
        if self.id:
            return combined_ + "><name>" + str(self.id) + "</name></trkpt>"
        else:
            return combined_ + "/>"

    def as_map_link(self):
        return "https://maps.google.com/?q={},{}".format(self.coords[0], self.coords[1])


class RouteElement(MapElement):
    def __init__(self, position, pokestops):
        super().__init__(position[0] + position[1], position[0], position[1], position[2] if len(position) > 1 else 0)
        self.pokestops = pokestops

    @staticmethod
    def from_coordinate(pos):
        return RouteElement(pos, [])

    def as_tuple(self):
        stops = [x.as_tuple() for x in self.pokestops]
        return self.coords, stops

    def as_latlon_object(self):
        return{"lat": self.coords[0], "lon": self.coords[1]}

    @staticmethod
    def from_tuple(tuple):
        pos = tuple[0]
        stops_arr = tuple[1]
        return RouteElement(pos, list([Pokestop.from_tuple(x) for x in stops_arr]))

    @staticmethod
    def from_tuples(tuples):
        return [RouteElement.from_tuple(x) for x in tuples]

    def __str__(self):
        return str(self.as_tuple())

    def __repr__(self):
        return self.__str__()

class MapElements(object):
    initial_gpx = """
    <?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.0">
    	<name>Example gpx</name>
    	<trk><name>Example gpx</name><number>1</number><trkseg>
    """

    post_gpx = """
    	</trkseg></trk>
    </gpx>
    """

    def __init__(self, elements) -> None:
        super().__init__()
        self.elements = elements

    def gpx_route(self):
        return "\n".join([x.gpx_string() for idx, x in enumerate(self.elements)])

    def write_gpx_route(self, filename):
        with open(filename, "w") as text_file:
            text_file.write(self.initial_gpx)
            text_file.write(self.gpx_route())
            text_file.write(self.post_gpx)

    @staticmethod
    def with_bogus_altitude(elements):
        return MapElements([MapElement(None, x[0], x[1], 0.1) for x in elements])

class Pokestop(MapElement):
    def __init__(self, element_id, latitude, longitude, altitude):
        super(Pokestop, self).__init__(element_id, latitude, longitude, altitude)
        self.twelves = 0

    def as_tuple(self):
        return self.coords, self.id

    @staticmethod
    def from_tuple(tuple):
        pos = tuple[0]
        id_ = tuple[1]
        return Pokestop(id_, pos[0], pos[1], pos[2])

    def element_type(self):
        return ElementType.POKESTOP


class GymElement(MapElement):
    def __init__(self, row):
        super(GymElement, self).__init__(row["gym_id"], row["latitude"], row["longitude"], row.get("altitude", None))
        self.name = row.get("name")

    @staticmethod
    def create(id_, latitude, longitude, altitude):
        row = {"gym_id": id_, "latitude": latitude, "longitude": longitude, "altitude": altitude}
        return GymElement(row)


    @staticmethod
    def from_db_rows(rows):
        return [GymElement(row) for row in rows]

    def element_type(self):
        return ElementType.GYM


class SpawnPoint(MapElement):
    def __init__(self, row):
        super(SpawnPoint, self).__init__(row["id"], row["latitude"], row["longitude"], row.get("altitude", None))
        self.id = row["id"]
        self.latitude = row["latitude"]
        self.longitude = row["longitude"]
        self.altitude = row["altitude"]
        self.kind = row.get("kind")
        self.links = row.get("links")
        self.latest_seen = row.get("latest_seen")
        self.earliest_unseen = row.get("earliest_unseen")

    @staticmethod
    def create(id_, latitude, longitude, altitude):
        row = {"id": id_, "latitude": latitude, "longitude": longitude, "altitude": altitude}
        return SpawnPoint(row)

    def location(self):
        return self.latitude, self.longitude, self.altitude

    @staticmethod
    def from_db_row(row):
        return SpawnPoint(row)

    @staticmethod
    def from_db_rows(rows):
        return [SpawnPoint(row) for row in rows]

    def element_type(self):
        return ElementType.SPAWNPOINT

    def __str__(self):
        startwindow = self.startwindow()
        start = startwindow[0]
        end = startwindow[1]
        return "{}/{}:{}-{}:{}".format(self.id, int(start / 60), start % 60, int(end / 60), end % 60)

    def duration(self):
        if self.kind == "hhhs":
            return 900
        if self.kind == "hhss":
            return 1800
        if self.kind == "ssss":
            return 3600
        if self.kind == "hsss":
            return 2700
        if self.kind == "hshs":
            return 2700
        raise ValueError("Dont know spawnpoint kind {}".format(self.kind))

    def startwindow(self):
        dur = self.duration()
        stop = (self.earliest_unseen - dur) % 3600
        return self.start(), stop

    def start(self):
        dur = self.duration()
        return (self.latest_seen - dur) % 3600

    def expires_at(self):
        return self.expires_at_with_time(dt.now())

    def expires_at_with_time(self, now):
        dt_ = now.replace(minute=0, second=0, microsecond=0)
        if second_of_hour(now) > self.latest_seen:
            dt_ = dt_ + timedelta(hours=1)
        return dt_ + timedelta(seconds=self.latest_seen)

    def could_have_spawned(self, last_not_seen_time, seen_time):
        return self.could_have_spawned_soh(second_of_hour(last_not_seen_time),
                                           second_of_hour(seen_time))

    def could_have_spawned_soh(self, last_not_seen_time_soh, seen_time_soh):
        pokemon_observation = (last_not_seen_time_soh,
                               seen_time_soh)
        return self.overlaps(pokemon_observation, self.startwindow())

    def spawns_at(self, instant):  # fix the hshs type
        pokemon_observation = (second_of_hour(instant),
                               second_of_hour(instant))
        return self.overlaps(pokemon_observation, self.startwindow())

    @staticmethod
    def overlaps(observations, spawnpoint_time):
        if observations[1] < observations[0]:  # normalize to non-wrapping time
            observations = (observations[0], observations[1] + 3600)
        if spawnpoint_time[1] < spawnpoint_time[0]:  # normalize to non-wrapping time
            spawnpoint_time = (spawnpoint_time[0], spawnpoint_time[1] + 3600)
        if observations[0] < spawnpoint_time[0] < observations[1]:
            return True
        if observations[0] < spawnpoint_time[1] < observations[1]:
            return True
        return False


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
        self.assertEqual(pos, r2.coords)



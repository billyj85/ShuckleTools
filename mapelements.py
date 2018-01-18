import unittest
from datetime import datetime as dt, timedelta

import math
from enum import Enum

import logging
from itertools import islice

from geography import center_geolocation, step_position


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
        return self.__str__() + "\n"

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

    def __iter__(self):
        return self.elements.__iter__()

    def fence_filtered(self, fence):
        return MapElements(fence.filter_map_elements(self.elements))

    def filter(self, type):
        return MapElements([f for f in self.elements if f.element_type() == type])

    def without_element_ids(self, ids):
        return MapElements([ x for x in self.elements if x.id not in ids])

    def __add__(self, another_map_elements):
        return MapElements(self.elements + another_map_elements.elements)

    def gpx_route(self):
        return "\n".join([x.gpx_string() for idx, x in enumerate(self.elements)])

    def write_gpx_route(self, filename):
        with open(filename, "w") as text_file:
            text_file.write(self.initial_gpx)
            text_file.write(self.gpx_route())
            text_file.write(self.post_gpx)

    @staticmethod
    def find_largest_stop_group(mapelements):
        result = 0
        for poke_stop in mapelements:
            result = max(result, len(poke_stop.collected_neighbours()))
        return result


    def __str__(self):
        return str(self.elements)

    def __repr__(self):
        return self.__str__()

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


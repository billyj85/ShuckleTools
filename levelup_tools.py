import asyncio
import logging
import numbers
import threading

from geography import step_position, chunk_box, is_inside_box, move_in_direction_of
from mapelement_tools import find_largest_groups
from scannerutil import precise_coordinate_string, full_precision_coordinate_string, equi_rect_distance_m
from tokyopath import find_best

log = logging.getLogger(__name__)


class CountDownLatch(object):
    def __init__(self, count=1):
        self.count = count
        self.lock = asyncio.Condition()

    async def count_down(self):
        await self.lock.acquire()
        self.count -= 1
        if self.count <= 0:
            await self.lock.notifyAll()
        self.lock.release()

    async def do_await(self):
        await self.lock.acquire()
        while self.count > 0:
            await self.lock.wait()
        self.lock.release()


def get_pos_to_use(route_element):
    return route_element.coords


def __get_cluster_pos(pokestop_position, spawn_cluster, worker_role):
    if not worker_role:
        return pokestop_position[0], pokestop_position[1], pokestop_position[2]
    role_mod = worker_role % 4
    if len(spawn_cluster) > 0 and spawn_cluster[1] > 2:  # use spawn cluster for positioning
        max_spawn_pos = spawn_cluster[0]
        max_spawn_pos = max_spawn_pos[0], max_spawn_pos[1], pokestop_position[2]
        if role_mod == 0:
            return max_spawn_pos
        if role_mod == 1:
            to_stop = equi_rect_distance_m(max_spawn_pos, pokestop_position)
            move_in_direction_of(max_spawn_pos, pokestop_position, to_stop + 39)
        if role_mod == 2:
            return step_position(max_spawn_pos, 39, 0)  # not really catch length ?
        if role_mod == 3:
            return step_position(max_spawn_pos, -39, 0)  # not really catch length ?

    if role_mod == 0:
        return step_position(pokestop_position, 39, 0)
    if role_mod == 1:
        return step_position(pokestop_position, -39, 0)
    if role_mod == 2:
        return step_position(pokestop_position, 0, 39)
    if role_mod == 3:
        return step_position(pokestop_position, 0, -39)
    log.error("No modulo")


def is_encounter_to(tuple_to_use):
    return type(tuple_to_use) is not tuple

def is_array_pokestops(tuple_to_use):
    return isinstance(tuple_to_use[1], list)



def is_plain_coordinate(tuple_to_use):
    return len(tuple_to_use) == 3 and type(tuple_to_use[0]) is not tuple


def as_coordinate(global_feed_map_pokemon, fallback_altitude):
    return global_feed_map_pokemon.latitude, global_feed_map_pokemon.longitude, fallback_altitude


def gpx_string(combined, pos=None):
    """  <trkpt lat="47.644548" lon="-122.326897">"""
    combined_ = "<trkpt lat='" + str(combined.coords[0]) + "' lon='" + str(combined.coords[1]) +"'"
    if pos:
        return combined_ + "><name>" + str(pos) +"</name></trkpt>"
    else:
        return combined_ + "/>"


def distance_route_locs_m(loc1, loc2):
    return equi_rect_distance_m(loc1[0], loc2[0])


def gpx_route(route):
    return "\n".join([gpx_string(x, idx) for idx, x in enumerate(route)])


def stop_string(combined):
    return "((" + precise_coordinate_string(combined[0]) +"),(" + full_precision_coordinate_string(combined[1].coords) + "," + repr(combined[1].id) + ")," + str(combined[2]) +")"

def stop_node(stop):
    return "(" + full_precision_coordinate_string(stop.coords) + ", '" + str(stop.id) + "')"

def xp_stop_string(xp_tuple):
    stops = "[" + ", ".join([stop_node(x) for x in xp_tuple[1]]) + "]"

    return "((" + precise_coordinate_string(xp_tuple[0]) + "), " + stops + ")"

def location_string(pos):
    return "(" + precise_coordinate_string(pos) +")"

def as_gpx(route):
    return initial_gpx + gpx_route(route) + post_gpx

def write_gpx_route(filename, xp_route):
    with open(filename, "w") as text_file:
        text_file.write(as_gpx(xp_route))


def back_to_route_elements(route_map, route_elements):
    result = []
    for i in range(0, len(route_map)):
        pos = route_map[i]
        result.extend(filter(lambda e: e.coords[0] == pos[0] and e.coords[1] == pos[1], route_elements))
    return result

def find_xp_route(point_list, fence_box, target_positions, min_size=2 ):
    route_elements = find_largest_groups(point_list, min_size)
    best_distance, best_route = find_best([x.as_latlon_object() for x in route_elements], target_positions)
    return back_to_route_elements( best_route, route_elements)

def exclusion_pokestops(list_):
    return {y[1] for x in list_ for y in x[1]}


initial_gpx="""
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.0">
	<name>Example gpx</name>
	<trk><name>Example gpx</name><number>1</number><trkseg>
"""

post_gpx = """
	</trkseg></trk>
</gpx>
"""

if __name__ == "__main__":
    from pokestoproutesv2 import routes_p1
    hbg = routes_p1.get("hamburg")
    for route_elem in hbg:
        print(str(precise_coordinate_string(route_elem[0])))

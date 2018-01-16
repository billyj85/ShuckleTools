import asyncio
import logging
import os

from argparser import basic_std_parser, add_geofence, setup_default_app
from geofence import get_geofences
from geography import lat_routed
from levelup_tools import find_xp_route, write_gpx_route, distance_route_locs_m
from mapelements import RouteElement, ElementType, MapElements
from mapelement_tools import find_optimal_location, create_pokestop_model, create_spawnpoint_model, \
    load_map_elements, filter_map_elements

dirname = os.path.dirname(os.path.realpath(__file__))

parser = basic_std_parser("pokestops")
parser.add_argument('-k', '--gmaps-key',
                    help='Google Maps Javascript API Key.',
                    required=False)
add_geofence(parser)
args = parser.parse_args()
args.system_id = "levelup-routes"

loop = asyncio.get_event_loop()
setup_default_app(args, loop)
log = logging.getLogger(__name__)

num_locs = 0


def filter_too_close(points):
    result = []
    idx = 0
    current = points[idx]
    idx += 1
    i = len(points) - 1
    while idx < i:
        while distance_route_locs_m(current, points[idx]) < 120 and idx < i:
            idx += 1
        result.append(points[idx])
        current = points[idx]
    return result


'''
    Grind route: Maximal spawn points only, center location between spawnpoints. in-range stops for lures.
    xp powerup route: Maximal pokestops, center location between stops. in-range (50) stops for lures
'''


def create_spawnpoint_route(fence_filtered, used_pokestops, gpx_filename, radius=39, target_positions=360*3):
    spawnpoint_elements = filter_map_elements(fence_filtered, ElementType.SPAWNPOINT)

    #pokestop_list = filter_map_elements(fence_filtered, ElementType.POKESTOP)
    #unused_stops = [ x for x in pokestop_list if x.id not in used_pokestops]
    #update_distances(unused_stops, radius)
    #extra_stops = find_largest_groups(unused_stops, min_size=2)
    #combined = extra_stops + spawnpoint_elements

    spawnpoints = create_spawnpoint_model(spawnpoint_elements, args)

    spawnpoint_route = find_xp_route(spawnpoints, target_positions=target_positions, min_size=3 )
    write_gpx_route(gpx_filename, spawnpoint_route)

    # clear off the actual points since we dont use them
    elems = [RouteElement.from_coordinate(xz.coords) for xz in spawnpoint_route]
    return elems


def create_boost_xp_route(pokestop_list, gpx_filename, target_positions=190):
    xp_route_1 = find_xp_route(pokestop_list, target_positions=target_positions, min_size=2 )
    write_gpx_route(gpx_filename, xp_route_1)
    return xp_route_1

def pokestop_ids(xp_route):
    result = set()
    for element in xp_route:
        for pokestop in element.pokestops:
            result.add(pokestop.id)
    return result

def create_one(pokestop_list, fence):
    def loc_find_optimal_location(stop_coords):
        global num_locs
        num_locs += 1
        if num_locs % 50 == 0:
            log.info("Found {} optimal spawn points".format(str(num_locs)))
        return find_optimal_location(stop_coords, args.gmaps_key)

    fenced78 = lat_routed(fence, 120, 39, pokestop_list)

    spaced = filter_too_close(fenced78)
    with_spawns = [x + (loc_find_optimal_location(x[1].coords),) for x in spaced]
    return with_spawns

def create_pokestop_list(file_name, fence):
    me = load_map_elements(file_name)
    pokestops = filter_map_elements(me, ElementType.POKESTOP)
    stops = fence.filter_forts(pokestops)
    return create_pokestop_model(stops, args)


def create_xp_route(fence_elements, gpx_name_root, radius=39):
    pokestop_list = filter_map_elements(fence_elements, ElementType.POKESTOP)
    MapElements.update_distances(pokestop_list, radius)

    xp_route_initial = create_boost_xp_route(pokestop_list, gpx_name_root + "_xp.gpx", 190)
    return xp_route_initial

def fence(name):
    return get_geofences(dirname + "/levelup_fences.txt", [name])

def write_file(file_name, var_name, route_string):
    with open("{}/routes/{}".format(dirname, file_name), "w") as text_file:
        text_file.write("{} = {}\n".format(str(var_name), str(route_string)))

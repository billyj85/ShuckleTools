import asyncio
import logging
import os
import sys

from argparser import basic_std_parser, add_geofence, setup_default_app
from geofence import get_geofences
from geography import lat_routed
from gymdbsql import pokestops_in_box, spawnpoints_in_box
from levelup_tools import find_xp_route, write_gpx_route, distance_route_locs_m
from mapelements import RouteElement
from mapelement_tools import find_optimal_location, create_pokestop_model, create_spawnpoint_model

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


def create_spawnpoint_route(fence, gpx_filename, target_positions=360*3):
    stops = fence.filter_forts(spawnpoints_in_box(fence.box()))
    spawnpoints = create_spawnpoint_model(stops, args)
    spawnpoint_route = find_xp_route(spawnpoints, fence.box(), target_positions=target_positions, min_size=4 )
    write_gpx_route(gpx_filename, spawnpoint_route)

    # clear off the actual points since we dont use them
    elems = [RouteElement.from_coordinate(xz.coords) for xz in spawnpoint_route]
    return elems


def create_boost_xp_route(pokestop_list, fence, gpx_filename, target_positions=190):
    xp_route_1 = find_xp_route(pokestop_list, fence.box(), target_positions=target_positions, min_size=2 )
    write_gpx_route(gpx_filename, xp_route_1)
    return xp_route_1


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


def create_pokestop_list(fence):
    stops = fence.filter_forts(pokestops_in_box(fence.box()))
    return create_pokestop_model(stops, args)


def fence(name):
    return get_geofences(dirname + "/levelup_fences.txt", [name])

def write_file(file_name, var_name, route_string):
    with open("{}/routes/{}".format(dirname, file_name), "w") as text_file:
        text_file.write("{} = {}\n".format(str(var_name), str(route_string)))

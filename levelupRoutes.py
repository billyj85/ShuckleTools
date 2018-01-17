import asyncio
import logging
import os

from argparser import basic_std_parser, add_geofence, setup_default_app
from geofence import get_geofences
from geography import lat_routed
from levelup_tools import distance_route_locs_m, find_optimal_route_brute_force
from mapelements import RouteElement, ElementType
from mapelement_tools import find_optimal_location, create_spawnpoint_model

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
    stops = fence_filtered.filter(ElementType.POKESTOP).without_element_ids(used_pokestops).update_distances(radius)
    groups_of_unused_stops = stops.find_largest_groups(min_size=3)

    spawnpoints = create_spawnpoint_model(fence_filtered.filter(ElementType.SPAWNPOINT), args, radius=55)
    spawnpoints_grouped = spawnpoints.find_largest_groups(4)

    combined = spawnpoints_grouped + groups_of_unused_stops

    spawnpoint_route = find_optimal_route_brute_force(combined, target_positions=target_positions)

    spawnpoint_route.write_gpx_route(gpx_filename)
    # clear off the actual spawnpoint since we dont use them. Somewhat odd :)
    elems = [RouteElement.from_coordinate(xz.coords) for xz in spawnpoint_route]
    return elems


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

def create_xp_route(fence_elements, gpx_name_root, radius=39):
    pokestop_list = fence_elements.filter(ElementType.POKESTOP)
    pokestop_list.update_distances(radius)
    route_elements = pokestop_list.find_largest_groups(2)
    xp_route_1 = find_optimal_route_brute_force(route_elements, target_positions=190)
    # xp_route_1.write_gpx_route(gpx_name_root + "_xp.gpx")
    return xp_route_1

def fence(name):
    return get_geofences(dirname + "/levelup_fences.txt", [name])

def write_file(file_name, var_name, route_string):
    with open("{}/routes/{}".format(dirname, file_name), "w") as text_file:
        text_file.write("{} = {}\n".format(str(var_name), str(route_string)))

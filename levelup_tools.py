from mapelements import MapElements
from scannerutil import equi_rect_distance_m
from tokyopath import find_best


def get_pos_to_use(route_element):
    if type(route_element) is tuple:
        return route_element
    return route_element.coords


def distance_route_locs_m(loc1, loc2):
    return equi_rect_distance_m(loc1[0], loc2[0])


def back_to_route_elements(route_map, route_elements):
    result = []
    for i in range(0, len(route_map)):
        pos = route_map[i]
        result.extend(filter(lambda e: e.coords[0] == pos[0] and e.coords[1] == pos[1], route_elements))
    return MapElements(result)


def find_optimal_route_brute_force(route_elements, target_positions):
    best_distance, best_route = find_best([x.as_latlon_object() for x in route_elements], target_positions)
    return back_to_route_elements(best_route, route_elements)



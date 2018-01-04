import logging
import math
import unittest
from collections import defaultdict
from math import cos, sin, atan2, sqrt

from geopy.distance import vincenty, distance

from scannerutil import precise_nice_number, precise_coordinate_string, pairwise, equi_rect_distance_m

log = logging.getLogger(__name__)


def fnords_box_moves_generator(topleft, bottomright, step_distance):
    current_pos = step_position(bottomright, step_distance / 2, -step_distance / 2)
    moving_left = True
    while is_inside_box_coords(current_pos, topleft, bottomright):
        yield current_pos
        if moving_left:
            next_pos = step_position(current_pos, 0.0, -step_distance)
        else:
            next_pos = step_position(current_pos, 0.0, +step_distance)
        if not is_inside_box_coords(next_pos, topleft, bottomright):
            next_pos = step_position(current_pos, step_distance, 0.0)
            if not is_inside_box_coords(next_pos, topleft, bottomright):
                return
            moving_left = not moving_left
        current_pos = next_pos


def lat_routed(fence, radius, catch_radius, coordinate_list):
    result = []
    box = fence.box()
    latitude = lat_offset(box[1][0], radius)
    forward = True
    while latitude < box[0][0]:
        first_row = latitude_filter(latitude, coordinate_list, radius)
        corrected = centerline_corrected(latitude, first_row, catch_radius)
        result += corrected if forward else reversed(corrected)
        latitude = lat_offset(latitude, 2 * radius)
        forward = not forward
    return result


def spline_stops(stop_in_order, spawns_in_order, forward):
    result = []
    num_stops = len(stop_in_order) - 1
    for idx, stop in enumerate(stop_in_order):
        spawns_between_stops = []
        if idx < num_stops:
            this_long = stop[1].coords[1]
            next_long = stop_in_order[idx + 1][1].coords[1]
            if forward:
                spawns_between_stops = [x for x in spawns_in_order if this_long < x["longitude"] < next_long]
            else:
                spawns_between_stops = [x for x in spawns_in_order if this_long > x["longitude"] > next_long]
            for x in spawns_between_stops:
                x["distance"] = distance(stop[1].coords, (x["latitude"], x["longitude"])).m
        result.append((stop[0], stop[1], spawns_between_stops))
    return result


def lat_routed_two(fence, radius, catch_radius, coordinate_list, spanw_points):
    result = []
    box = fence.box()
    latitude = lat_offset(box[1][0], radius)
    forward = True
    while latitude < box[0][0]:
        first_row = latitude_filter(latitude, coordinate_list, radius)
        corrected = centerline_corrected(latitude, first_row, catch_radius)
        stop_in_order = corrected if forward else list(reversed(corrected))

        band_spawns = latitude_filter_map(latitude, spanw_points, catch_radius)
        spawns_in_order = band_spawns if forward else list(reversed(band_spawns))

        latitude = lat_offset(latitude, 2 * radius)
        result += spline_stops(stop_in_order, spawns_in_order, forward)
        forward = not forward
    return result


def centerline_corrected(latitude, items, max_distance):
    result = []
    for pokestop in items:
        centerline_coord = (latitude, pokestop[1], pokestop[2])
        distance_from_centerline = distance(centerline_coord, pokestop.coords).m
        if distance_from_centerline < max_distance:
            result.append((centerline_coord, pokestop))
        else:
            if pokestop[0] > latitude:
                lat_to_use = lat_offset(latitude, distance_from_centerline - max_distance)
            else:
                lat_to_use = lat_offset(latitude, -(distance_from_centerline - max_distance))
            player_position = (lat_to_use, pokestop[1], pokestop[2])
            if distance(player_position, pokestop.coords).m > 40:
                log.warning("Tr")
            result.append((player_position, pokestop))
    return result


class LatRoutedTest(unittest.TestCase):
    def test_centerline_corrected(self):
        corrected = centerline_corrected(59.1, [(59.2, 10), (59.0, 11)], 20)
        print(corrected)


def box_moves_generator(topleft, bottomright):
    current_pos = step_position(bottomright, 303.5, -303.0)
    moving_left = True
    while is_inside_box_coords(current_pos, topleft, bottomright):
        yield current_pos
        if moving_left:
            next_pos = step_position(current_pos, 0.0, -707.0)
        else:
            next_pos = step_position(current_pos, 0.0, +707.0)
        if not is_inside_box_coords(next_pos, topleft, bottomright):
            next_pos = step_position(current_pos, 707.0, 0.0)
            if not is_inside_box_coords(next_pos, topleft, bottomright):
                return
            moving_left = not moving_left
        current_pos = next_pos


def num_box_steps(topleft, bottomright):
    current_pos = step_position(bottomright, 303.5, -303.0)
    left = 0
    north = 0
    while is_inside_box_coords(current_pos, topleft, bottomright):
        current_pos = step_position(current_pos, 0.0, -707.0)
        left += 1
    current_pos = step_position(bottomright, 303.5, -303.0)
    while is_inside_box_coords(current_pos, topleft, bottomright):
        current_pos = step_position(current_pos, 707.0, 0.0)
        north += 1
    return left * north


def gym_moves_generator(gyms):
    num = 0
    while num < (len(gyms)):
        currentpos = gyms[num]
        yield currentpos
        num += 1


def moves_generator(pos, steps):
    num = 0
    currentpos = pos
    while num < steps:
        yield currentpos
        currentpos = step_position(currentpos, 0.0, -707.0)
        num += 1


def latitude_filter(latitude, list, radius):
    northernly = lat_offset(latitude, radius)
    southernly = lat_offset(latitude, -radius)
    res = [x for x in list if northernly >= x[0] >= southernly]
    return res


def latitude_filter_map(latitude, list, radius):
    northernly = lat_offset(latitude, radius)
    southernly = lat_offset(latitude, -radius)
    res = [x for x in list if northernly >= x["latitude"] >= southernly]
    return res


def width_generator(pos, steps):
    num = 0
    currentpos = pos
    while num < steps:
        yield currentpos
        currentpos = step_position(currentpos, 707.0, 0.0)
        num += 1


def as_2d_coords_one_per_line(coordinates):
    result = ""
    for c in coordinates:
        result += precise_nice_number(c[0]) + "," + precise_nice_number(c[1]) + "\n"
    return result


def as_3d_coord_array(coordinates):
    return "[" + ", ".join(["(" + precise_coordinate_string(x[0]) + ")" for x in coordinates]) + "]"


def lat_offset(latitude, offset):
    return latitude + (180 / 3.1415929) * (float(offset) / 6378137)


def box_around(pos, offset):
    topleft_box = step_position(pos, offset, -offset)
    bottomright_box = step_position(pos, -offset, offset)
    return topleft_box, bottomright_box


def step_position(pos, north, east):
    dx = float(east)
    lat0 = pos[0]
    lon0 = pos[1]
    lat = lat_offset(lat0, north)
    lon = lon0 + (180 / 3.1415929) * (dx / 6378137) / math.cos(3.1415929 / 180.0 * lat0)
    if len(pos) == 2:
        return lat, lon
    else:
        return lat, lon, pos[2]


def geo_chunk(coordinates, gridsize=4):
    box = geo_box(coordinates)
    for box in chunk_box(box, gridsize):
        for coord in coordinates:
            if is_inside_box(coord, box):
                yield coord


def geo_chunk_map(coordinates, gridsize=4):
    box = geo_box(coordinates)
    log.info(u"Geo box is {}".format(str(box)))
    result = defaultdict(list)
    boxes = list(chunk_box(box, gridsize))
    for coord in coordinates:
        for box in boxes:
            if is_inside_box(coord, box):
                result[box].append(coord)
    return result


def chunk_box(box, gridsize=4):
    lat_step = float(box[1][0] - box[0][0]) / gridsize
    long_step = float(box[1][1] - box[0][1]) / gridsize
    even = True
    for lat in range(0, gridsize):
        if even:
            for lng in range(0, gridsize):
                topleft = (box[0][0] + (lat_step * lat), box[0][1] + (long_step * lng))
                yield topleft, (topleft[0] + lat_step, topleft[1] + long_step)
        else:
            for lng in range(gridsize, 0, -1):
                topleft = (box[0][0] + (lat_step * lat), box[0][1] + (long_step * (lng-1)))
                yield topleft, (topleft[0] + lat_step, topleft[1] + long_step)
        even = not even


def geo_box(coordinates):
    min_lat = 180
    max_lat = -180
    min_lon = 180
    max_lon = -180
    for coord in coordinates:
        min_lat = min(min_lat, coord[0])
        max_lat = max(max_lat, coord[0])
        min_lon = min(min_lon, coord[1])
        max_lon = max(max_lon, coord[1])
    return (max_lat, min_lon), (min_lat, max_lon)


def time_between_locations(start, end, meters_per_second):
    if not end:
        return 0
    return time_for_distance(vincenty(start, end).m, meters_per_second)


def time_for_distance(distance, meters_per_second):
    return distance / meters_per_second if distance > 0 else 0


def is_inside_box(pos, box):
    return is_inside_box_coords(pos, box[0], box[1])


def is_inside_box_coords(pos, top_left, bottom_right):
    latmatch = top_left[0] >= pos[0] >= bottom_right[0]
    longmatch = top_left[1] <= pos[1] <= bottom_right[1]
    return latmatch and longmatch


def within_fences(latitude, longitude, fences):
    if len(fences) == 0:
        return True
    for fence in fences:
        if fence.contains(latitude, longitude):
            return True
    return False


def create_route(waypoints, step_lengths, north, east):
    result = []
    offseted_wp = [step_position(x, north, east) for x in waypoints]
    for pos, next_pos in pairwise(offseted_wp):
        result.append(pos)
        while equi_rect_distance_m(pos, next_pos) > step_lengths:
            pos = move_towards(pos, next_pos, step_lengths)
            result.append(pos)
    return result


def move_towards(start, stop, m):
    dist = equi_rect_distance_m(start, stop)
    if dist < m:
        return stop
    return go_to_step_num(start, stop, dist, m)


def move_in_direction_of(start, stop, m):
    """Moves toward another point, can go past point"""
    dist = equi_rect_distance_m(start, stop)
    return go_to_step_num(start, stop, dist, m)


def go_to_step_num(start, stop, num_steps, step):
    dx, dy = (stop[0] - start[0], stop[1] - start[1])
    alt = start[2]
    stepx, stepy = (dx / float(num_steps), dy / float(num_steps))
    return start[0] + (1 + step) * stepx, start[1] + (1 + step) * stepy, alt


def steps_to_point(start, stop, num_steps):
    ax = start[0]
    ay = start[1]
    bx = stop[0]
    by = stop[1]
    dx, dy = (bx - ax, by - ay)
    result = []
    stepx, stepy = (dx / float(num_steps), dy / float(num_steps))
    for i in range(int(num_steps)):
        stepy_ = (start[0] + (1 + i) * stepx, start[1] + (1 + i) * stepy)
        if stepy_ != stop:
            result.append(stepy_)
    return result


def center_geolocation(geolocations):
    """
    Provide a relatively accurate center lat, lon returned as a list pair, given
    a list of list pairs.
    ex: in: geolocations = ((lat1,lon1), (lat2,lon2),)
        out: (center_lat, center_lon)
    """
    x = 0
    y = 0
    z = 0

    for tuple_ in geolocations:
        lat = tuple_[0]
        lon = tuple_[1]
        lat = float(math.radians(lat))
        lon = float(math.radians(lon))
        x += cos(lat) * cos(lon)
        y += cos(lat) * sin(lon)
        z += sin(lat)

    x = float(x / len(geolocations))
    y = float(y / len(geolocations))
    z = float(z / len(geolocations))

    rlat = float(math.degrees(atan2(z, sqrt(x * x + y * y))))
    rlng = float(math.degrees(atan2(y, x)))
    if len(geolocations[0]) == 3:
        return rlat, rlng, geolocations[0][2]
    else:
        return rlat, rlng


class WaypointsTest(unittest.TestCase):
    def test(self):
        wp = [(53.477084, 10.259286, 50.22897338867188), (53.478151, 10.238244, 5.319664478302002),
              (53.479974, 10.225083, 2.908063411712646), (53.483188, 10.213013, 4.66163969039917)]
        route = create_route(wp, 50, 0, 0)
        for elem in route:
            print(precise_coordinate_string(elem))
        route = create_route(wp, 50, 50, 0)
        for elem in route:
            print(precise_coordinate_string(elem))
        route = create_route(wp, 50, 100, 0)
        for elem in route:
            print(precise_coordinate_string(elem))


class BoxMovesTest(unittest.TestCase):
    def test(self):
        generator = box_moves_generator((59.934862, 10.71567),
                                        (59.905849, 10.768023))
        items = list(generator)
        self.assertEqual(len(items), 20)
        self.assertEqual(
            num_box_steps((59.934862, 10.71567), (59.905849, 10.768023)), 20)
        self.assertEqual(items[0][0], items[1][0])
        self.assertEqual(items[0][0], items[2][0])
        self.assertEqual(items[0][0], items[3][0])
        self.assertNotEqual(items[0][0], items[4][0])
        self.assertEqual(items[3][1], items[4][1])  # turning point


class BoxTest(unittest.TestCase):
    def test(self):
        box = geo_box([(59.935684, 10.682678), (59.935684, 10.682478), (59.921234, 10.684459), (59.926481, 10.712504)])
        self.assertEqual(box[0][0], 59.935684)
        self.assertEqual(box[0][1], 10.682478)
        self.assertEqual(box[1][0], 59.921234)
        self.assertEqual(box[1][1], 10.712504)


class BoxChunkTest(unittest.TestCase):
    def test(self):
        box = geo_box([(59, 9.5), (58.9, 9), (58.5, 10), (58, 9.75)])
        self.assertEqual(box, ((59, 9), (58, 10)))
        chunks = list(chunk_box(box, 2))
        self.assertEqual(chunks[0], ((59.0, 9.0), (58.5, 9.5)))
        self.assertEqual(chunks[1], ((59.0, 9.5), (58.5, 10.0)))
        self.assertEqual(chunks[2], ((58.5, 9.0), (58.0, 9.5)))
        self.assertEqual(chunks[3], ((58.5, 9.5), (58.0, 10.0)))


class MyTest2(unittest.TestCase):
    def test(self):
        top_left = (60.0, 9.0)
        box = (top_left, (58.0, 10.0))
        self.assertEqual(is_inside_box((59.0, 9.5), box), True)
        self.assertEqual(is_inside_box((61.0, 9.5), box), False)
        self.assertEqual(is_inside_box((57.0, 9.5), box), False)
        self.assertEqual(is_inside_box((59.0, 11), box), False)
        self.assertEqual(is_inside_box((59.0, 8), box), False)
        self.assertEqual(is_inside_box((60.0, 9.5), box), True)
        self.assertEqual(is_inside_box((59.0, 9.0), box), True)
        self.assertEqual(is_inside_box((58.0, 9.5), box), True)
        self.assertEqual(is_inside_box((57.9999, 9.5), box), False)
        self.assertEqual(is_inside_box((59.0, 10.0), box), True)


class TestGeo(unittest.TestCase):
    def test(self):
        coords = [(59.925818, 10.7032860), (59.925846, 10.7035530), (59.926148, 10.7027230), (59.926396, 10.7032060)]
        center = center_geolocation(coords)
        print("center is {}".format(str(center)))
        for coord in coords:
            print(("dist to {} is {}".format(str(coord), vincenty(center, coord).m)))



class TestGeo2(unittest.TestCase):
    def test(self):
        coords = [(59.940370, 10.721415), (59.940166, 10.7206500), (59.939642, 10.7221430), (59.939620, 10.7215500)]
        center = center_geolocation(coords)
        print("center is {}".format(str(center)))
        for coord in coords:
            print(("dist to {} is {}".format(str(coord), vincenty(center, coord).m)))


class TestSteps(unittest.TestCase):
    def test(self):
        start = 59.904162, 10.842091
        stop = 59.898157, 10.831147
        offset = steps_to_point(start, stop, 3)
        self.assertEqual((59.902160333333335, 10.838443), offset[0])
        self.assertEqual((59.90015866666666, 10.834795), offset[1])

    def test_other_direction(self):
        start = 59.898157, 10.831147
        stop = 59.904162, 10.842091
        offset = steps_to_point(start, stop, 3)
        self.assertEqual((59.902160333333335, 10.838443), offset[1])
        self.assertEqual((59.90015866666666, 10.834795), offset[0])

    def test_halfstep(self):
        start = 59.898157, 10.831147
        stop = 59.904162, 10.842091
        offset = steps_to_point(start, stop, 2.3)
        print(str(offset))
        self.assertEqual((59.900767869565215, 10.835905260869565), offset[0])
        self.assertEqual((59.90337873913043, 10.840663521739131), offset[1])

    def test_misc_stuff(self):
        start = 59.898157, 10.831147
        stop = 59.904162, 10.842091
        seconds = 49.1
        num_steps = int(seconds / 10)
        offset = steps_to_point(start, stop, num_steps)
        print(offset)

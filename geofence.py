import logging
import re
import sys
import traceback
import unittest

from collections import defaultdict

log = logging.getLogger(__name__)


def is_inside_box(pos, box):
    return is_inside_box_coords(pos, box[0], box[1])


def is_inside_box_coords(pos, top_left, bottom_right):
    latmatch = top_left[0] >= pos[0] >= bottom_right[0]
    longmatch = top_left[1] <= pos[1] <= bottom_right[1]
    return latmatch and longmatch


class Geofences(object):
    def __init__(self, fences):
        self.fences = fences

    def box(self):
        __min_long = sys.maxsize
        __max_lat = -181
        __max_long = -181
        __min_lat = sys.maxsize
        for p in self.fences:
            box = p.box()
            topleft = box[0]
            bottomright = box[1]
            __max_lat = max(topleft[0], __max_lat)
            __min_lat = min(topleft[0], __min_lat)
            __max_long = max(topleft[1], __max_long)
            __min_long = min(topleft[1], __min_long)
            __max_lat = max(bottomright[0], __max_lat)
            __min_lat = min(bottomright[0], __min_lat)
            __max_long = max(bottomright[1], __max_long)
            __min_long = min(bottomright[1], __min_long)
        return (__max_lat, __min_long), (__min_lat, __max_long)

    def within_fences(self, latitude, longitude):
        if len(self.fences) == 0:
            return True
        for fence in self.fences:
            if fence.contains(latitude, longitude):
                return True
        return False

    def fence_name(self, lat, lng):
        for fence in self.fences:
            if fence.contains(lat, lng):
                return fence.name

    def pos_within_fences(self, pos):
        return self.within_fences(pos[0], pos[1])

    def filter_fence_names(self, fence_names_):
        if fence_names_ is not None and len(fence_names_) > 0:
            fences_to_use = []
            for fence in self.fences:
                if fence.name in fence_names_:
                    fences_to_use.append(fence)
            if len(fence_names_) != len(fences_to_use):
                raise ValueError(
                    "One or more required fences is missing, required {} found only {}".format(str(fence_names_),
                                                                                               str(len(fences_to_use))))
            log.info(u"Using geofences {}".format(str(fences_to_use)))
            return Geofences(fences_to_use)
        else:
            return self

    def filter_forts(self, gyms):
        result = [loc for loc in gyms if self.within_fences(loc["latitude"], loc["longitude"])]
        log.info(u"There are {} elements within fence".format(str(len(result))))
        return result

    def __str__(self):
        return ", ".join([str(x) for x in self.fences])


class Geofence(object):
    # Expects points to be
    def __init__(self, name, points):
        self.name = name
        self.__points = points

        self.__min_x = points[0][0]
        self.__max_x = points[0][0]
        self.__min_y = points[0][1]
        self.__max_y = points[0][1]

        for p in points:
            self.__min_x = min(p[0], self.__min_x)
            self.__max_x = max(p[0], self.__max_x)
            self.__min_y = min(p[1], self.__min_y)
            self.__max_y = max(p[1], self.__max_y)

    def box(self):
        return (self.__max_x, self.__max_y), (self.__min_x, self.__min_y)

    def contains(self, x, y):
        # Quick check the boundary box of the entire polygon
        if self.__max_x < x or x < self.__min_x or self.__max_y < y or y < self.__min_y:
            return False

        xinters = None
        inside = False
        p1x, p1y = self.__points[0]
        n = len(self.__points)
        for i in range(1, n + 1):
            p2x, p2y = self.__points[i % n]
            if min(p1y, p2y) < y <= max(p1y, p2y) and x <= max(p1x, p2x):
                if p1y != p2y:
                    xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if p1x == p2x or x <= xinters:
                    inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def contains_fort(self, fort):
        if isinstance(fort, dict):
            return self.contains(fort["latitude"], fort["longitude"])
        else:
            return self.contains(fort.latitude, fort.longitude)

    def get_name(self):
        return self.name

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()


def filter_for_geofence(gyms, fence_file, fence_name):
    fences_to_use = get_geofences(fence_file, fence_name)
    result = []

    for loc in gyms:
        if fences_to_use.within_fences(loc["latitude"], loc["longitude"]):
            result.append(loc)

    return result


def group_by_geofence(gyms, fence_file, fence_name):
    fences_to_use = get_geofences(fence_file, fence_name)
    result = defaultdict(list)

    for loc in gyms:
        fence_name = fences_to_use.fence_name(loc["latitude"], loc["longitude"])
        if fence_name:
            result[fence_name].append(str(loc["latitude"]) + "," + str(loc["longitude"]))

    return result


def within_fences(latitude, longitude, fences):
    if len(fences) == 0:
        return True
    for fence in fences:
        if fence.contains(latitude, longitude):
            return True
    return False


def fence_names(self, latitude, longitude):
    names = []
    for fence in self.fences:
        if fence.contains(latitude, longitude):
            names.append(fence.name)
    return names


def get_geofences(fence_file, fence_names_):
    result = Geofences([])
    if fence_file is None:
        return result

    geofence_file = load_geofence_file(fence_file)
    if not geofence_file:
        log.error("No geofences in file or file {} missing ?".format(fence_file))
    geofences = Geofences(geofence_file)
    return geofences.filter_fence_names(fence_names_)


# Load in a geofence file
def load_geofence_file(file_path):
    try:
        geofences = []
        name_pattern = re.compile("(?<=\[)([^]]+)(?=\])")
        coor_patter = re.compile("[-+]?[0-9]*\.?[0-9]*" + "[ \t]*,[ \t]*" + "[-+]?[0-9]*\.?[0-9]*")
        with open(file_path, 'r') as f:
            lines = f.read().splitlines()
        name = "geofence"
        points = []
        for line in lines:
            line = line.strip()
            match_name = name_pattern.search(line)
            if match_name:
                if len(points) > 0:
                    geofences.append(Geofence(name, points))
                    log.info(u"Geofence {} loaded.".format(name))
                    points = []
                name = match_name.group(0)
            elif coor_patter.match(line):
                lat, lng = list(map(float, line.split(",")))
                points.append([lat, lng])
            else:
                log.error("Geofence was unable to parse this line: {}".format(line))
                log.error("All lines should be either '[name]' or 'lat,lng'.")
        geofences.append(Geofence(name, points))
        log.info(u"Geofence {} added.".format(name))
        return geofences
    except IOError:
        log.error("IOError: Please make sure a file with read/write permissions exsist at {}".format(file_path))
    except Exception as e:
        log.error("Encountered error while loading Geofence: {}: {}".format(type(e).__name__, e))
    log.debug("Stack trace: \n {}".format(traceback.format_exc()))


class GeoFencesTest(unittest.TestCase):
    def test(self):
        f1 = Geofence("testFence1", [(2, 2), (1, 1)])
        f2 = Geofence("testFence2", [(3, 2), (0.5, 1)])
        f3 = Geofence("testFence2", [(3, 4), (1, 0.3)])
        fences = Geofences([f1, f2, f3])
        box = fences.box()
        topleft = box[0]
        bottomright = box[1]
        self.assertEqual(topleft[0], 3)
        self.assertEqual(topleft[1], 0.3)
        self.assertEqual(bottomright[0], 0.5)
        self.assertEqual(bottomright[1], 4)


class GeofenceBoxTest(unittest.TestCase):
    def test(self):
        fg = Geofence("testFence", [(59.93967316186938, 10.691757202148438),
                                    (59.92642849367861, 10.671157836914062),
                                    (59.90921973039279, 10.696220397949219),
                                    (59.908531194256106, 10.775871276855469),
                                    (59.92746073574969, 10.802650451660156),
                                    (59.94414419318535, 10.770721435546875)
                                    ])
        box = fg.box()
        self.assertEqual(box[0], (59.94414419318535, 10.802650451660156))
        self.assertEqual(box[1], (59.908531194256106, 10.671157836914062))
        print((str(box)))


class GeofenceSimpleBoxTest(unittest.TestCase):
    def test(self):
        fg = Geofence("testFence", [(4.0, 4.1),
                                    (3.9, 2.0),
                                    (2.0, 1.9),
                                    (2.1, 4.2)
                                    ])
        box = fg.box()
        self.assertEqual(box[0], (4, 4.2))
        self.assertEqual(box[1], (2, 1.9))
        self.assertTrue(fg.contains(3, 3))


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

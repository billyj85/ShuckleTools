# import tqdm
import codecs
import argparse
import asyncio
import geopy
import sys
from geopy.distance import vincenty
from collections import defaultdict
from math import sin, cos, sqrt, atan2, radians


def calc_distance(point1, point2):
    R = 6373.0

    lat1 = radians(point1[0])
    lon1 = radians(point1[1])
    lat2 = radians(point2[0])
    lon2 = radians(point2[1])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

def parseFile(inputFile='tokyostops.txt', sep=",", commentaryMarker="#"):
    data = []
    with codecs.open(inputFile, 'r', 'utf-8') as f:
        for line in f:
            line = line.strip()
            if len(line) < 1 or line[0] == commentaryMarker:
                continue
            parts = line.split(sep)
            lat = parts[0]
            lon = parts[1]
            data.append({"lat": lat, "lon": lon})
    return data



def find_nearest_unused_element(start_point, stop_data, route, used_elements):

    point_distance = 100000000
    closest_point = None
    for i in range(0, len(stop_data) - 1):
        if start_point != stop_data[i]:
            next_point = (float(stop_data[i]['lat']), float(stop_data[i]['lon']))

            if start_point is None:
                print(str(next_point))
            distance_new = calc_distance(start_point, next_point)

            if ((distance_new < point_distance) and (next_point not in used_elements)):
                point_distance = distance_new
                closest_point = next_point

    return closest_point, point_distance

def calc_route(start_point, stopData, route, used_elements, count, distance, route_distance):
    closest_point, point_distance = find_nearest_unused_element(start_point, stopData, route,used_elements)
    if closest_point is None:
        return None, None
    count += 1
    route[count] = closest_point
    used_elements.add(closest_point)
    total_distance = distance + point_distance

    if len(route) > route_distance:
        return route, total_distance
    return calc_route(closest_point, stopData, route, used_elements, count, total_distance, route_distance)


def main():
    stop_data = parseFile()
    total_stops_to_hit = min(2000, len(stop_data) - 2)
    best_distance, best_route = find_best(stop_data, total_stops_to_hit)

    print(str(best_route))

def find_best(stop_data, total_stops_to_hit):
    route_file = open('routes.txt', 'w')
    best_route = {}
    best_distance = 10000000
    total_stops_to_hit = min(total_stops_to_hit, len(stop_data) -1)

    for i in range(0, len(stop_data) -1 ):
        start_point = (float(stop_data[i]['lat']), float(stop_data[i]['lon']))
        new_route = {0: start_point}
        used_elements = set()
        temp_route, distance = calc_route(start_point, stop_data, new_route, used_elements, 0, 0, total_stops_to_hit)

        route_file.write(str(distance) + ' ' + str(temp_route) + '\n')

        if (distance < best_distance):
           best_distance = distance
           print("New best distance {}".format(best_distance))
           for j in range(0, len(temp_route)):
               best_route[j] = temp_route[j]

    return best_distance, best_route

if __name__ == '__main__':
#    loop=asyncio.get_event_loop()
#    future = asyncio.ensure_future(main())
#    loop.run_until_complete(future)
    sys.setrecursionlimit(3700)
    main()

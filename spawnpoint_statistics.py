from async_accountdbsql import set_account_db_args
from gymdbsql import spawnpoints,spawns
from datetime import datetime, timedelta
from geopy.distance import vincenty
from argparser import basic_std_parser,add_geofence
from gymdbsql import set_gymdb_args
from itertools import islice
from geofence import get_geofences
from geography import within_fences,step_position

parser = basic_std_parser("spawnpoints")
add_geofence(parser)
args = parser.parse_args()
set_gymdb_args(args)
set_account_db_args(args)


class StatSpawnPoint:
    def __init__(self, id, latitude, longitude):
        self.id = id
        self.coords = ( latitude, longitude)
        self.twelves = 0
        self.twentyfives = 0
        self.twelves_from_neighbours = 0
        self.twentyfives_from_neighbours = 0

    def add_spawn(self, pokemonid):
        if  pokemonid == 12 or pokemonid == 15 or pokemonid == 18:
            self.twelves += 3
        if pokemonid == 11 or pokemonid == 14 or pokemonid == 17:
            self.twelves += 2
        if pokemonid == 10 or pokemonid == 13 or pokemonid == 16:
            self.twelves += 1
        if pokemonid == 1 or pokemonid == 4 or pokemonid == 7 or pokemonid == 19 \
            or pokemonid == 29 or pokemonid == 32 or pokemonid == 43 or pokemonid == 60 \
            or pokemonid == 63 or pokemonid == 66 or pokemonid == 69 or pokemonid == 74 \
            or pokemonid == 92 or pokemonid == 133 or pokemonid == 147 or pokemonid == 152 \
            or pokemonid == 155 or pokemonid == 158 or pokemonid == 172 or pokemonid == 174 \
            or pokemonid == 179 or pokemonid == 187 or pokemonid == 246:
            self.twentyfives += 1

    def is_within_range(self, other, m):
        return vincenty(self.coords, other.coords).m <= m


    def add_neighhbours(self, otherspawnpoint, distanceRequirement):
        if otherspawnpoint == self:
            return
        if self.is_within_range(otherspawnpoint, distanceRequirement):
            self.twelves_from_neighbours += otherspawnpoint.twelves
            otherspawnpoint.twelves_from_neighbours += self.twelves
            self.twentyfives_from_neighbours += otherspawnpoint.twentyfives
            otherspawnpoint.twentyfives_from_neighbours += self.twentyfives

    def total_twelves(self):
        return self.twelves + self.twelves_from_neighbours

    def total_twentyfives(self):
        return self.twentyfives + self.twentyfives_from_neighbours


points = {}
point_list = []

fences = get_geofences(args.geofence, args.fencename)

for spawnpoint in spawnpoints():
    latitude_ = spawnpoint["latitude"]
    longitude_ = spawnpoint["longitude"]
    if within_fences( latitude_, longitude_, fences):
        spawn_point = StatSpawnPoint(spawnpoint["id"], latitude_, longitude_)
        points[spawnpoint["id"]] = spawn_point
        point_list.append( spawn_point)

print("{} spawn points in area".format(str(len(point_list))))

d = datetime.today() - timedelta(days=1)
for spawn in spawns(d):
    pt = points.get(spawn["spawnpoint_id"])
    if pt is not None: pt.add_spawn(spawn["pokemon_id"])

print("Populated {} spawn points with spawn data".format(str(len(point_list))))

for idx, point in enumerate(point_list):
    if idx % 500 == 0:
        print("Processing point at index " + str(idx))
    cutoff_long = step_position(point.coords, 0, 150.0)
    for point2 in islice(point_list, idx + 1 , None):
        point_longitude = point2.coords[1]
        if point_longitude > cutoff_long[1]:
            break
        point.add_neighhbours(point2, 150.0)

maxTwelve = 0
for point in point_list:
    if point.total_twelves() > maxTwelve:
        maxTwelve = point.total_twelves()

cutoff = maxTwelve * 0.90
print("Cutoff is " + str(cutoff))

for key in point_list:
    if key.total_twelves() >= cutoff:
        print()
        print("{} spawn {} tjuefemmere ved https://www.google.com/maps/?daddr={},{}".format(
            str(key.total_twelves()), str(key.total_twentyfives()), str(key.coords[0]), str(key.coords[1]) ))








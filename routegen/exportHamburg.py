import asyncio
import logging
import os

from argparser import basic_std_parser, add_geofence, setup_default_app
from geofence import Geofence
from gymdbsql import pokestops_in_box, spawnpoints_in_box, gyms_in_box

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

fence = Geofence("hamburg", [
    (53.7351445815432, 9.5635986328125),
    (53.363088956906395, 9.57183837890625),
    (53.31389056047761, 10.513916015625),
    (53.793591468075, 10.4754638671875),
    (53.824405643545084, 9.55810546875)])
box=fence.box()
sps = fence.filter_forts(spawnpoints_in_box(box))
pokestops = fence.filter_forts(pokestops_in_box(box))
gyms = fence.filter_forts(gyms_in_box(box))


def dump_elem(text_file, x, idfield, type):
    text_file.write("{},{},{},{},{}\n".format(str(x[idfield]), type, str(x["latitude"]), str(x["longitude"]), str(x["altitude"])))


with open("{}/../routes/hamburg_source_data.txt".format(dirname), "w") as text_file:
    for x in gyms:
        dump_elem(text_file, x, "gym_id","G")
    for x in pokestops:
        dump_elem(text_file, x, "pokestop_id", "P")
    for x in sps:
        dump_elem(text_file, x, "id", "S")


print ("Done")

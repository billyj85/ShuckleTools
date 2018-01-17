import asyncio

from levelupRoutes import create_spawnpoint_route, fence, write_file, \
    create_xp_route, pokestop_ids
from mapelement_tools import load_map_elements
import sys

loop = asyncio.get_event_loop()


sys.setrecursionlimit(10000)


async def start():
    location_elements = load_map_elements("hamburg_source_data.txt")
    fence_filtered = location_elements.fence_filtered(fence("HamburgRight"))
    radius = 39

    # temp_dud = create_spawnpoint_route(fence_filtered,set(), "spawnpoint_route_hr.gpx", radius)

    xp_route_right = create_xp_route(fence_filtered, "hbg_right", radius)
    used_pokestops = pokestop_ids(xp_route_right)
    write_file( "hamburg_xp1.py", "xp_route_1", str(xp_route_right))
    spawnpoint_route_right = create_spawnpoint_route(fence_filtered,used_pokestops, "spawnpoint_route_hr.gpx", radius)
    write_file( "hamburg_grind1.py", "spawnpoint_route_1", str(spawnpoint_route_right))


loop.run_until_complete(start())

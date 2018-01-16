import asyncio

from levelupRoutes import create_spawnpoint_route, fence, write_file, \
    create_xp_route, pokestop_ids
from mapelement_tools import load_map_elements

loop = asyncio.get_event_loop()


async def start():
    location_elements = load_map_elements("hamburg_source_data.txt")
    fence_filtered = fence("HamburgLeft").filter_forts(location_elements)
    radius = 39
    xp_route_left = create_xp_route(fence_filtered, "hbg_left", radius)
    write_file( "hamburg_xp2.py", "xp_route_2", str(xp_route_left))
    used_pokestops = pokestop_ids(xp_route_left)
    spawnpoint_route_left = create_spawnpoint_route(fence_filtered, used_pokestops, "spawnpoint_route_hl.gpx", radius)
    write_file( "hamburg_grind2.py", "spawnpoint_route_2", str(spawnpoint_route_left))


loop.run_until_complete(start())

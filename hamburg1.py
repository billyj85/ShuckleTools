import asyncio

from levelupRoutes import create_spawnpoint_route, fence, write_file, \
    create_xp_route
from mapelement_tools import load_map_elements

loop = asyncio.get_event_loop()


async def start():
    location_elements = load_map_elements("hamburg_source_data.txt")
    fence_filtered = fence("HamburgLeft").filter_forts(location_elements)
    xp_route_left = create_xp_route(fence_filtered, "hbg_left")
    write_file( "hamburg_xp1.py", "xp_route_1", str(xp_route_left))
    spawnpoint_route_left = create_spawnpoint_route(fence_filtered, "spawnpoint_route_hl.gpx")
    write_file( "hamburg_grind1.py", "spawnpoint_route_1", str(spawnpoint_route_left))


loop.run_until_complete(start())

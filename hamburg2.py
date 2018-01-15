import asyncio

from levelupRoutes import create_spawnpoint_route, fence, write_file, \
    create_xp_route
from mapelement_tools import load_map_elements

loop = asyncio.get_event_loop()


async def start():
    location_elements = load_map_elements("hamburg_source_data.txt")
    fence_filtered = fence("HamburgRight").filter_forts(location_elements)

    xp_route_right = create_xp_route(fence_filtered, "hbg_right")
    write_file( "hamburg_xp2.py", "xp_route_2", str(xp_route_right))
    spawnpoint_route_right = create_spawnpoint_route(fence_filtered, "spawnpoint_route_hr.gpx")
    write_file( "hamburg_grind2.py", "spawnpoint_route_2", str(spawnpoint_route_right))


loop.run_until_complete(start())

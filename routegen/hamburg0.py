import asyncio

from levelupRoutes import fence, write_file, create_xp_route, create_spawnpoint_route, pokestop_ids
from mapelement_tools import load_map_elements

loop = asyncio.get_event_loop()


async def start():
    location_elements = load_map_elements("hamburg_source_data.txt")
    fence_filtered = fence("InitialHamburg").filter_forts(location_elements)

    xp_route_initial = create_xp_route(fence_filtered, "hbg_initial")
    write_file( "hamburg_initial.py", "stop_route_initial", str(xp_route_initial))
    used_ids = pokestop_ids( xp_route_initial)
    spawnpoint_route_left = create_spawnpoint_route(fence_filtered, used_ids, "spawnpoint_route_hl.gpx")


loop.run_until_complete(start())

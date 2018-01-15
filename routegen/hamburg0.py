import asyncio

from mapelement_tools import load_map_elements
from routegen.levelupRoutes import  fence, write_file, create_xp_route

loop = asyncio.get_event_loop()


async def start():
    location_elements = load_map_elements("hamburg_source_data.txt")
    fence_filtered = fence("InitialHamburg").filter_forts(location_elements)

    xp_route_initial = create_xp_route(fence_filtered, "hbg_initial")
    write_file( "hamburg_initial.py", "stop_route_initial", str(xp_route_initial))

loop.run_until_complete(start())

import asyncio

from levelupRoutes import create_pokestop_list, create_boost_xp_route, create_spawnpoint_route, fence, write_file

loop = asyncio.get_event_loop()


async def start():
    def create_xp_route(fence_, gpx_name_root):
        pokestop_list = create_pokestop_list(fence_)
        return create_boost_xp_route(pokestop_list, fence_, gpx_name_root + "_xp.gpx", 190)

    hamburg_initial_fence = fence("InitialHamburg")
    xp_route_initial = create_xp_route(hamburg_initial_fence, "hbg_initial")
    write_file( "hamburg_initial.py", "stop_route_initial", str(xp_route_initial))

loop.run_until_complete(start())

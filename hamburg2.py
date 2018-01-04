import asyncio

from levelupRoutes import create_pokestop_list, create_boost_xp_route, create_spawnpoint_route, fence, write_file

loop = asyncio.get_event_loop()


async def start():
    def create_xp_route(fence_, gpx_name_root):
        pokestop_list = create_pokestop_list(fence_)
        xp_route_initial = create_boost_xp_route(pokestop_list, fence_, gpx_name_root + "_xp.gpx", 190)
        return xp_route_initial


    hamburg_right_fence = fence("HamburgRight")
    xp_route_right = create_xp_route(hamburg_right_fence, "hbg_right")
    write_file( "hamburg_xp2", "xp_route_2", str(xp_route_right))
    spawnpoint_route_right = create_spawnpoint_route(fence("HamburgRight"), "spawnpoint_route_hr.gpx")
    write_file( "hamburg_grind2", "spawnpoint_route_2", str(spawnpoint_route_right))


loop.run_until_complete(start())

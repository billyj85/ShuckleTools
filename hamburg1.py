import asyncio

from levelupRoutes import create_pokestop_list, create_boost_xp_route, create_spawnpoint_route, fence, write_file

loop = asyncio.get_event_loop()


async def start():
    def create_xp_route(fence_, gpx_name_root):
        pokestop_list = create_pokestop_list(fence_)
        xp_route_initial = create_boost_xp_route(pokestop_list, fence_, gpx_name_root + "_xp.gpx", 190)
        return xp_route_initial

    hamburg_left_fence = fence("HamburgLeft")
    xp_route_left = create_xp_route(hamburg_left_fence, "hbg_left")
    write_file( "hamburg_xp1", "xp_route_1", str(xp_route_left))
    spawnpoint_route_left = create_spawnpoint_route(hamburg_left_fence, "spawnpoint_route_hl.gpx")
    write_file( "hamburg_grind1", "spawnpoint_route_1", str(spawnpoint_route_left))


loop.run_until_complete(start())

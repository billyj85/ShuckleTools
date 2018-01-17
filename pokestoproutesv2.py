from mapelements import RouteElement
from routes.hamburg_grind1 import spawnpoint_route_1
from routes.hamburg_grind2 import spawnpoint_route_2
from routes.hamburg_grind3 import spawnpoint_route_3
from routes.hamburg_initial import stop_route_initial
from routes.hamburg_xp1 import xp_route_1
from routes.hamburg_xp2 import xp_route_2
from routes.hamburg_xp3 import xp_route_3

initial_130_stops = {"hamburg": list(reversed(RouteElement.from_tuples(stop_route_initial)))}

routes_all = {
    "hamburg": [
        {
            "grind": RouteElement.from_tuples(spawnpoint_route_1),
            "xp": RouteElement.from_tuples(xp_route_1)
        },
        {
            "grind": RouteElement.from_tuples(spawnpoint_route_3),
            "xp": RouteElement.from_tuples(xp_route_3)
        },
        {
            "grind": RouteElement.from_tuples(spawnpoint_route_2),
            "xp": RouteElement.from_tuples(xp_route_2)
        },
    ]
}

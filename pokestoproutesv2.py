from mapelements import RouteElement
from routes.hamburg_grind1 import hamburg_spawnpoint_route_1
from routes.hamburg_grind2 import spawnpoint_route_2
from routes.hamburg_grind3 import spawnpoint_route_3
from routes.hamburg_xp1 import hamburg_xp_route_1
from routes.hamburg_xp2 import xp_route_2
from routes.hamburg_xp3 import xp_route_3
from routes.tokyo_grind1 import tokyo_spawnpoint_route_1
from routes.tokyo_grind2 import tokyo_spawnpoint_route_2
from routes.tokyo_xp1 import tokyo_xp_route_1
from routes.tokyo_xp2 import tokyo_xp_route_2

routes_all = {
    "hamburg": [
        {
            "grind": RouteElement.from_tuples(hamburg_spawnpoint_route_1),
            "xp": RouteElement.from_tuples(hamburg_xp_route_1)
        },
        {
            "grind": RouteElement.from_tuples(spawnpoint_route_3),
            "xp": RouteElement.from_tuples(xp_route_3)
        },
        {
            "grind": RouteElement.from_tuples(spawnpoint_route_2),
            "xp": RouteElement.from_tuples(xp_route_2)
        }
    ],
    "tokyo": [
        {
            "grind": RouteElement.from_tuples(tokyo_spawnpoint_route_1),
            "xp": RouteElement.from_tuples(tokyo_xp_route_1)
        },
        {
            "grind": RouteElement.from_tuples(tokyo_spawnpoint_route_2),
            "xp": RouteElement.from_tuples(tokyo_xp_route_2)
        }
    ]

}

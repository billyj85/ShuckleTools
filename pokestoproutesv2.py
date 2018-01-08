from mapelements import RouteElement
from routes.hamburg_grind1 import spawnpoint_route_1
from routes.hamburg_grind2 import spawnpoint_route_2
from routes.hamburg_initial import stop_route_initial
from routes.hamburg_xp1 import xp_route_1
from routes.hamburg_xp2 import xp_route_2

initial_130_stops = {"hamburg": list(reversed(RouteElement.from_tuples(stop_route_initial)))}

routes_p1 = {"hamburg": RouteElement.from_tuples(spawnpoint_route_1)}
xp_p1 = {"hamburg": RouteElement.from_tuples(xp_route_1)}

routes_p2 = {"hamburg": RouteElement.from_tuples(spawnpoint_route_2)}
xp_p2 = {"hamburg": RouteElement.from_tuples(xp_route_2)}



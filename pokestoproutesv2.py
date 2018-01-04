from hamburg import spawnpoint_route_1, spawnpoint_route_2, xp_route_1, xp_route_2, stop_route_initial
from mapelements import RouteElement

initial_130_stops = {"hamburg": list(reversed(RouteElement.from_tuples(stop_route_initial)))}

routes_p1 = {"hamburg": RouteElement.from_tuples(spawnpoint_route_1)}
xp_p1 = {"hamburg": RouteElement.from_tuples(xp_route_1)}

routes_p2 = {"hamburg": RouteElement.from_tuples(spawnpoint_route_2)}
xp_p2 = {"hamburg": RouteElement.from_tuples(xp_route_2)}



import logging
import os

dirname = os.path.dirname(os.path.realpath(__file__))


from geography import step_position
from gymdbsql import insert_altitude, altitudes
from pogom.fnord_altitude import with_gmaps_altitude
from pogom.utils import cellid

log = logging.getLogger(__name__)


def add_altitudes(stops, gmaps_key):
    added = 0
    for stop in stops:
        if stop["altitude"] is None:
            pos = (stop["latitude"], stop["longitude"])
            RADIUS = 70.0
            topleft_box = step_position(pos, RADIUS, -RADIUS)
            bottomright_box = step_position(pos, -RADIUS, RADIUS)
            altitude_candidates = altitudes(topleft_box, bottomright_box)
            if len(altitude_candidates) > 0:
                stop["altitude"] = altitude_candidates[0]["altitude"]
                insert_altitude(cellid(pos), pos[0], pos[1], altitude_candidates[0]["altitude"])
                added += 1
            else:
                pos = with_gmaps_altitude(pos, gmaps_key)
                stop["altitude"] = pos[2]
                insert_altitude(cellid(pos), pos[0], pos[1], pos[2])
    if added > 0:
        log.info("Found {} altitudes by approximating DB data, {} total stops".format(str(added), str(len(stops))))
    return stops



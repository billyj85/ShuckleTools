from datetime import datetime, timedelta

from aiopogo.hash_server import HashServer

from behaviours import beh_aggressive_bag_cleaning, beh_spin_pokestop, beh_spin_nearby_pokestops
from inventory import inventory
from scannerutil import nice_number_2


class StopManager(object):
    def __init__(self, worker, catch_manager, worker_manager, max_stops):
        self.max_stops = int(max_stops)
        self.worker = worker
        self.next_spin_log = 10
        self.save_pokestops = False
        self.catch_manager = catch_manager
        self.worker_manager = worker_manager
        self.spins_at = {}
        self.spin_number = 0
        self.spun_stops = set()
        self.log_xp_at = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)

    async def spin_stops(self, map_objects, pokestop_id, player_position, index, exclusions={}):
        if self.should_spin(index):
            if self.worker_manager.has_active_lucky_egg():
                await self.spin_all_stops(map_objects, player_position, exclusion=exclusions)
            else:
                await self.spin_single_stop(map_objects, player_position, pokestop_id, exclusions)

    def should_spin(self, index):
        return (self.save_pokestops and index % 2 == 0) or not self.save_pokestops

    async def spin_all_stops(self, map_objects, player_position, range_m=39, exclusion={}):
        spuns = await beh_spin_nearby_pokestops(self.worker, map_objects, player_position, range_m, self.spun_stops,
                                          exclusion)
        self.spun_stops.update(spuns)
        return len(spuns)

    async def spin_single_stop(self, map_objects, player_position, pokestop_id, exclusions):
        self.spins_at[(datetime.now().minute + 1) % 59] = 0
        if pokestop_id in exclusions:
            self.worker.log.info(u"Not spinning excluded stop {}".format(pokestop_id))
            return
        if pokestop_id in self.spun_stops:
            self.worker.log.info(u"Skipping stop {}, already spun".format(pokestop_id))
        spin_pokestop = await beh_spin_pokestop(self.worker, map_objects, player_position, pokestop_id)
        if spin_pokestop == 4:
            await beh_aggressive_bag_cleaning(self.worker)
            spin_pokestop = await beh_spin_pokestop(self.worker, map_objects, player_position, pokestop_id)

        if spin_pokestop == 1:
            self.spun_stops.add(pokestop_id)
            if len(self.spun_stops) == 2500 and self.catch_manager.pokemon_caught < 1200:
                self.save_pokestops = True
                self.increment_spin()
        else:
            self.worker.log.info(u"Spinning failed {}".format(str(spin_pokestop)))

    def increment_spin(self):
        self.spin_number += 1
        self.spins_at[datetime.now().minute % 59] = self.spin_number

    def num_spins_last_30_minutes(self):
        before_that = (datetime.now().minute - 30) % 59
        spins_30_min_ago = self.spins_at.get(before_that, 0)
        return self.spin_number - spins_30_min_ago

    def log_status(self, egg_active, has_egg, egg_number, index, phase):
        xp = self.worker.account_info()["xp"]
        self.worker_manager.register_xp(xp)
        if datetime.now() > self.log_xp_at:
            self.log_xp_at = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
            self.next_spin_log = len(self.spun_stops) + 10
            num_stops = self.num_spins_last_30_minutes()
            rem = HashServer.status.get('remaining', 0)
            ratio = float(self.catch_manager.pokemon_caught) / len(self.spun_stops) if len(self.spun_stops) > 0 else 0
            xp_30min_ago = self.worker_manager.xp_30_minutes_ago()
            self.worker.log.info(u"P{}L{}, {}S/{}P//R{}, {}E/{}EW, {}XP/{}@30min{}{}, {}S@30min. idx={}, {} hash"
                     .format(str(phase), str(self.worker_manager.level), str(len(self.spun_stops)),
                             str(self.catch_manager.pokemon_caught), str(nice_number_2(ratio)),
                             str(self.catch_manager.evolves),
                             str(self.catch_manager.num_evolve_candidates()),
                             str(xp), str(xp - xp_30min_ago), 'E' + str(egg_number) if egg_active else '',
                             'H' if has_egg else '',
                             str(num_stops), str(index), str(rem)))

    async def reached_limits(self):
        if len(self.spun_stops) > self.max_stops:
            self.worker.log.info(u"Reached target spins {}".format(str(len(self.spun_stops))))
            return True
        if await self.worker_manager.reached_target_level():
            return True
        return False

    def log_inventory(self):
        self.worker.log.info(u"Inventory:{}".format(str(inventory(self.worker))))

    def clear_state(self):
        self.spun_stops = set()

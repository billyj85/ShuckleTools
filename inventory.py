from six import itervalues


def has_lucky_egg(worker):
    return egg_count(worker) > 0


def has_incense(worker):
    return incense_count(worker) > 0


def egg_count(worker):
    return __inv(worker).get(301, 0)


def incense_count(worker):
    return __inv(worker).get(401, 0)


def lure_count(worker):
    return __inv(worker).get(501, 0)


def ultra_balls(worker):
    return __inv(worker).get(3, 0)


def poke_balls(worker):
    return __inv(worker).get(1, 0)


def blue_ball(worker):
    return __inv(worker).get(2, 0)


def total_balls(worker):
    return ultra_balls(worker) + blue_ball(worker) + poke_balls(worker)


def total_iventory_count(worker):
    return sum(itervalues(__inv(worker)))


def __inv(worker):
    return worker.account_info()["items"]


def inventory(worker):
    return worker.account_info()["items"]

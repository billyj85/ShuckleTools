class GaveUp(BaseException):
    """We tried and we tried, but it's simply not going to work out between us...."""


class GaveUpApiAction(BaseException):
    """We tried and we tried, but it's simply not going to work out between us...."""

    def __init__(self, msg):
        self.msg = msg


class NoMoreWorkers(BaseException):
    pass


class TooFarAway(BaseException):
    def __init__(self, distance):
        self.distance = distance


class SkippedDueToOptional(BaseException):

    def __init__(self, distance):
        self.distance = distance

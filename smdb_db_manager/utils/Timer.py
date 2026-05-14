from time import time_ns


class Timer:
    start: float
    end: float

    def __init__(self):
        self.start = time_ns()

    def stop(self, divisor: float = 1.0) -> float:
        self.end = time_ns()
        return (self.end - self.start) / divisor

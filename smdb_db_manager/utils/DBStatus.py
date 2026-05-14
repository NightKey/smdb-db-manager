from enum import Enum


class DBStatus(Enum):
    STARTING = 0
    RUNNING = 1
    STOPPING = 2
    STOPPED = 3
    FAILED = 4

    def __lt__(self, other) -> bool:
        if not isinstance(other, DBStatus): return False
        return self.value < other.value

    def __gt__(self, other) -> bool:
        if not isinstance(other, DBStatus): return False
        return self.value > other.value

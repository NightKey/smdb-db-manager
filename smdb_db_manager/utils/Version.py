from dataclasses import dataclass
from typing import Tuple


@dataclass
class Version:
    major: int
    minor: int
    patch: int

    def __eq__(self, other) -> bool:
        if not isinstance(other, Version): return False
        return self.major == other.major and self.minor == other.minor and self.patch == other.patch

    def __gt__(self, other):
        if not isinstance(other, Version): return False
        return (self.major > other.major or
                (self.major == other.major and self.minor > other.minor) or
                (self.major == other.major and self.minor == other.minor and self.patch > other.patch))

    def __lt__(self, other):
        if not isinstance(other, Version): return False
        return (self.major < other.major or
                (self.major == other.major and self.minor < other.minor) or
                (self.major == other.major and self.minor == other.minor and self.patch < other.patch))

    def to_db(self) -> Tuple[int, int, int]:
        return self.major, self.minor, self.patch

    @staticmethod
    def from_db(row: Tuple[int, int, int]) -> 'Version':
        return Version(
            int(row[0]),
            int(row[1]),
            int(row[2])
        )

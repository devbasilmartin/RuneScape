"""The OSRS experience table."""
from functools import lru_cache


@lru_cache(maxsize=None)
def xp_for_level(level: int) -> int:
    """Total XP needed to reach ``level`` (1-99)."""
    points = 0
    for lvl in range(1, level):
        points += int(lvl + 300 * 2 ** (lvl / 7))
    return points // 4


def xp_between(start: int, end: int) -> int:
    return max(0, xp_for_level(end) - xp_for_level(start))

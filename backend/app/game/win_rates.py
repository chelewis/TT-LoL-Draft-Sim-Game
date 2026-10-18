"""Champion x champion win rates (same team and against) as simulation modifiers.

A delta is the average win rate of a set of pairs minus `win_rates.baseline`, in points, capped at
`max_points` either way. Pairs without data are left out; a set with no data at all has delta 0.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable

from .models import MatchupTable


def _delta(rates: Iterable[float | None], config: dict) -> float:
    known = [r for r in rates if r is not None]
    if not known:
        return 0.0
    cfg = config["win_rates"]
    delta = sum(known) / len(known) - cfg["baseline"]
    cap = cfg["max_points"]
    return max(-cap, min(cap, delta))


def ally_delta(champion_ids: list[int], table: MatchupTable, config: dict) -> float:
    """How much better than the baseline these champions do together, averaged over every pair."""
    return _delta((table.ally_rate(a, b) for a, b in combinations(champion_ids, 2)), config)


def counter_delta(mine: list[int], theirs: list[int], table: MatchupTable, config: dict) -> float:
    """How much better than the baseline `mine` do against `theirs`, averaged over every cross pair."""
    return _delta((table.enemy_rate(m, t) for m in mine for t in theirs), config)


def multiplier(delta: float, scale: float, config: dict) -> float:
    if not config["win_rates"]["enabled"]:
        return 1.0
    return max(1.0 + scale * delta, 0.1)

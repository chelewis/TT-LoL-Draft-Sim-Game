"""Player Draft for seasons (pure, no database): snake order, whether a pool can still fill every open roster lane,
and the automatic pick used when a pick clock runs out or the CPU drafts for a team.

A pool player can fill a lane they play (their role or secondary role). A pick is only allowed if, afterwards, the
players left can still fill every team's open lanes, so no team can be left without a legal pick.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.game.config import LANES


@dataclass(frozen=True)
class PoolPlayer:
    id: int
    lanes: frozenset[str]         # the lanes they can fill
    total: int                    # stat total: the auto pick takes the best available
    role: str = ""                # their main lane, tried first by the auto pick


def snake_order(order: Sequence[int], pick_number: int) -> int:
    """The team on the clock for `pick_number` (1-based): the order forward in odd rounds, backward in even ones."""
    n = len(order)
    if n == 0:
        raise ValueError("no teams in the draft")
    index, round_ = (pick_number - 1) % n, (pick_number - 1) // n
    return order[index] if round_ % 2 == 0 else order[n - 1 - index]


def lane_shortfall(needs: Mapping[str, int], pool: Sequence[PoolPlayer]) -> dict[str, int]:
    """For each lane, how many of the `needs` (open slots across all teams) the pool can't fill, with each player
    used at most once. Empty when everything can be filled. (Bipartite matching: players against lane slots.)"""
    slots = [lane for lane in LANES for _ in range(max(0, needs.get(lane, 0)))]
    if not slots:
        return {}
    taken: list[int | None] = [None] * len(slots)          # slot -> index into pool
    by_lane: dict[str, list[int]] = {}
    for i, lane in enumerate(slots):
        by_lane.setdefault(lane, []).append(i)

    def place(p: int, seen: set[int]) -> bool:
        for lane in pool[p].lanes:
            for slot in by_lane.get(lane, ()):
                if slot in seen:
                    continue
                seen.add(slot)
                if taken[slot] is None or place(taken[slot], seen):
                    taken[slot] = p
                    return True
        return False

    filled = 0
    for p in range(len(pool)):
        if filled == len(slots):
            break
        if pool[p].lanes & by_lane.keys() and place(p, set()):
            filled += 1
    missing: dict[str, int] = {}
    for slot, lane in enumerate(slots):
        if taken[slot] is None:
            missing[lane] = missing.get(lane, 0) + 1
    return missing


def _needs(open_lanes: Sequence[Sequence[str]]) -> dict[str, int]:
    needs: dict[str, int] = {}
    for lanes in open_lanes:
        for lane in lanes:
            needs[lane] = needs.get(lane, 0) + 1
    return needs


def pick_problem(pool: Sequence[PoolPlayer], open_lanes: Sequence[Sequence[str]], team: int, player_id: int,
                 lane: str) -> str | None:
    """Why `team` (an index into `open_lanes`) can't take `player_id` for `lane` (None: it can)."""
    player = next((p for p in pool if p.id == player_id), None)
    if player is None:
        return "That player isn't available."
    if lane not in open_lanes[team]:
        return f"Your {lane} spot is already filled."
    if lane not in player.lanes:
        return f"That player can't play {lane}."
    after = [list(lanes) for lanes in open_lanes]
    after[team].remove(lane)
    missing = lane_shortfall(_needs(after), [p for p in pool if p.id != player_id])
    if missing:
        lanes = ", ".join(sorted(missing))
        return f"That pick would leave the pool unable to fill every team's {lanes}. Pick someone else."
    return None


def auto_pick(pool: Sequence[PoolPlayer], open_lanes: Sequence[Sequence[str]], team: int) -> tuple[int, str] | None:
    """The best available player (highest stat total) for one of the team's open lanes whose pick still leaves
    every team able to fill its roster. A player's main lane is tried first. None if nothing fits."""
    for player in sorted(pool, key=lambda p: (-p.total, p.id)):
        for lane in sorted(player.lanes & set(open_lanes[team]), key=lambda lane: (lane != player.role, LANES.index(lane))):
            if pick_problem(pool, open_lanes, team, player.id, lane) is None:
                return player.id, lane
    return None

"""KDA, rank scores, MVP and ACE (spec 9.12)."""
from __future__ import annotations

import random
from typing import Any


def kda(kills: int, deaths: int, assists: int) -> float:
    return (kills + assists) / max(1, deaths)


def rank_score(lane_score: float, kills: int, deaths: int, assists: int) -> int:
    return int(lane_score * kda(kills, deaths, assists))


def assign_ranks(players: list[dict[str, Any]], rng: random.Random) -> None:
    """Add `rank_score` and `rank` (1 = best) to each player dict, in place.

    Ties break by kills, then gold, then a seeded coin flip.
    """
    for p in players:
        p["kda"] = round(kda(p["kills"], p["deaths"], p["assists"]), 2)
        p["rank_score"] = rank_score(p["lane_score"], p["kills"], p["deaths"], p["assists"])
        p["_coin"] = rng.random()
    ordered = sorted(players, key=lambda p: (-p["rank_score"], -p["kills"], -p["gold"], p["_coin"]))
    for position, p in enumerate(ordered, start=1):
        p["rank"] = position
    for p in players:
        del p["_coin"]


def pick_mvp_and_ace(players: list[dict[str, Any]], winner: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """MVP: best player on the winning team. ACE: best player of all ten."""
    ace = min(players, key=lambda p: p["rank"])
    mvp = min((p for p in players if p["team"] == winner), key=lambda p: p["rank"])
    return mvp, ace

"""Champion range (1 melee, 2 short, 3 long) and waveclear (1 weak, 2 average, 3 strong) in the simulation.

Every effect is a plain multiplier or chance offset (no rolls), and most compare one side with the other, so a
matchup between equal comps changes nothing. Each section returns a neutral value when it is switched off.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .models import Champion

NEUTRAL = 2  # the middle score of both attributes
BOT_LANE = ("BOT", "SUPPORT")


def share_multiplier(mine: float, theirs: float, scale: float) -> float:
    """1 + scale * 2 * (share - 0.5): +scale when `mine` is everything, -scale when it is nothing."""
    total = mine + theirs
    share = mine / total if total > 0 else 0.5
    return 1.0 + scale * 2.0 * (share - 0.5)


def _avg(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else float(NEUTRAL)


def avg_range(champions: Iterable[Champion]) -> float:
    return _avg(c.attack_range for c in champions)


def avg_waveclear(champions: Iterable[Champion]) -> float:
    return _avg(c.waveclear for c in champions)


# -------------------------------------------------------------- waveclear
def waveclear_lane_cs(mine: Champion, theirs: Champion, config: dict) -> float:
    """Lane-phase CS multiplier: the side that clears waves faster farms more of them."""
    cfg = config["waveclear"]
    if not cfg["enabled"]:
        return 1.0
    return share_multiplier(mine.waveclear, theirs.waveclear, cfg["lane_cs_scale"])


def waveclear_farm_factor(champion: Champion, config: dict) -> float:
    """CS per minute multiplier after the lane phase: strong waveclear farms side waves faster."""
    cfg = config["waveclear"]
    if not cfg["enabled"]:
        return 1.0
    return 1.0 + cfg["farm_scale"] * (champion.waveclear - NEUTRAL)


def waveclear_priority(champions_by_lane: Mapping[str, Champion], config: dict) -> float:
    """Objective control multiplier from lane priority: the team's waveclear, weighted by lane (mid and bot
    pushing first matters most for dragons and barons)."""
    cfg = config["waveclear"]
    if not cfg["enabled"]:
        return 1.0
    weights = cfg["priority_weights"]
    total = sum(weights.get(lane, 0.0) for lane in champions_by_lane)
    if total <= 0:
        return 1.0
    weighted = sum(c.waveclear * weights.get(lane, 0.0) for lane, c in champions_by_lane.items()) / total
    return 1.0 + cfg["priority_scale"] * (weighted - NEUTRAL)


# ------------------------------------------------------------------ range
def range_lane_multiplier(mine: Iterable[Champion], theirs: Iterable[Champion], config: dict) -> float:
    """Lane score multiplier: the longer-ranged side wins trades (per step of average range over the opponent)."""
    cfg = config["range"]
    if not cfg["enabled"]:
        return 1.0
    return 1.0 + cfg["lane_scale"] * (avg_range(mine) - avg_range(theirs))


def range_fight_multiplier(members: Iterable[Champion], enemies: Iterable[Champion], size: int,
                           config: dict) -> float:
    """Fight power multiplier: range wins teamfights (poke, kiting), melee wins skirmishes (dive). `size` is the
    side's fighter count, split the same way as the team-style teamfight/skirmish bonuses."""
    cfg = config["range"]
    if not cfg["enabled"]:
        return 1.0
    diff = avg_range(members) - avg_range(enemies)
    if size >= 4:
        return max(1.0 + cfg["teamfight_scale"] * diff, 0.1)
    return max(1.0 - cfg["skirmish_scale"] * diff, 0.1)


# ------------------------------------------------------------------ siege
def siege_chance_delta(attackers: Iterable[Champion], defenders: Iterable[Champion], config: dict) -> float:
    """Change to a siege hit's chance: the attacker's waveclear pushes waves in and its range pokes the
    defenders off the tower; the defender's waveclear and range hold it."""
    attackers, defenders = list(attackers), list(defenders)
    delta = 0.0
    wc, rg = config["waveclear"], config["range"]
    if wc["enabled"]:
        delta += wc["siege_scale"] * (avg_waveclear(attackers) - avg_waveclear(defenders))
    if rg["enabled"]:
        delta += rg["siege_scale"] * (avg_range(attackers) - avg_range(defenders))
    return delta


# -------------------------------------------------------------- callouts
_SIDE_NAME = {"BLUE": "Blue", "RED": "Red"}
_LANE_NAME = {"TOP": "Top", "MID": "Mid", "BOT": "Bot lane"}
TEAM_GAP = 2      # team total difference that gets a callout
SOLO_LANE_GAP = 2  # top/mid range difference (long vs melee)
DUO_LANE_GAP = 1   # bot duo average range difference


def _lead(blue: float, red: float) -> tuple[str, str]:
    return ("BLUE", "RED") if blue > red else ("RED", "BLUE")


def matchup_callouts(lineups: Mapping[str, Mapping[str, int]], champions: Mapping[int, Champion],
                     config: dict) -> list[str]:
    """Short notes for the matchup panel when one side has a clear range or waveclear edge. Only effects that
    are switched on are mentioned."""
    teams = {side: {lane: champions[cid] for lane, cid in lineup.items() if cid in champions}
             for side, lineup in lineups.items()}
    if set(teams) != {"BLUE", "RED"}:
        return []
    notes: list[str] = []
    blue, red = teams["BLUE"], teams["RED"]
    rg, wc = config["range"], config["waveclear"]

    if rg["enabled"]:
        totals = {"BLUE": sum(c.attack_range for c in blue.values()), "RED": sum(c.attack_range for c in red.values())}
        if abs(totals["BLUE"] - totals["RED"]) >= TEAM_GAP:
            hi, lo = _lead(totals["BLUE"], totals["RED"])
            notes.append(f"{_SIDE_NAME[hi]} out-ranges {_SIDE_NAME[lo]} ({totals[hi]} vs {totals[lo]}): stronger in "
                         f"teamfights and sieges; {_SIDE_NAME[lo]} is stronger in skirmishes.")
        for lane in ("TOP", "MID"):
            b, r = blue.get(lane), red.get(lane)
            if b and r and abs(b.attack_range - r.attack_range) >= SOLO_LANE_GAP:
                (hs, hc), (_, lc) = sorted((("BLUE", b), ("RED", r)), key=lambda x: -x[1].attack_range)
                notes.append(f"{_LANE_NAME[lane]}: {_SIDE_NAME[hs]}'s {hc.name} out-ranges {lc.name} in lane.")
        if all(l in blue for l in BOT_LANE) and all(l in red for l in BOT_LANE):
            b_avg, r_avg = avg_range(blue[l] for l in BOT_LANE), avg_range(red[l] for l in BOT_LANE)
            if abs(b_avg - r_avg) >= DUO_LANE_GAP:
                hi, _ = _lead(b_avg, r_avg)
                notes.append(f"{_LANE_NAME['BOT']}: {_SIDE_NAME[hi]}'s duo out-ranges its opponents in lane.")

    if wc["enabled"]:
        totals = {"BLUE": sum(c.waveclear for c in blue.values()), "RED": sum(c.waveclear for c in red.values())}
        if abs(totals["BLUE"] - totals["RED"]) >= TEAM_GAP:
            hi, lo = _lead(totals["BLUE"], totals["RED"])
            notes.append(f"{_SIDE_NAME[hi]} has stronger waveclear ({totals[hi]} vs {totals[lo]}): more farm, better "
                         f"objective priority and harder to siege.")
    return notes

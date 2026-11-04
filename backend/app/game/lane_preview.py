"""Lane-phase previews for the lineup (lock-in / swap) stage: the matchup wheel per lane, each player's expected
lane score on their champion graded against every champion they could have played there, and whether the
champion is in one of its usual roles.

Everything here mirrors the per-player part of `lane_phase.run_lane_phase` with the average roll in place of the
dice. The team-wide multipliers (team style, focus lane) are left out: they are the same for every champion, so
they can't change how a pick ranks.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .comfort import comfort_modifier, comfort_tier, off_role, off_role_multiplier
from .lane_phase import BOT_LANE, champion_synergy, strength_fit
from .matchup import apply_coach_draft, lane_matchup
from .models import Champion, MatchupTable, PlayerSpec
from .playstyle import adjust_comfort, effect_totals
from .range_waveclear import range_lane_multiplier
from .scaling import scaling_multiplier
from .win_rates import ally_delta, counter_delta, multiplier

FIT_STATS = ("aggr", "aware", "pos", "dmg")
GRADES = ("S", "A", "B", "C", "D")   # best first; below the last floor is F


# ------------------------------------------------------------------ roles
def role_status(champion: Champion, lane: str, player: PlayerSpec | None, config: dict) -> str | None:
    """MAIN (the champion's most played role), SECONDARY (another of its usual roles), OFF_ROLE, or
    OFF_ROLE_EXEMPT (off-role, but a top pool pick of the player's, so there is no penalty). None when the
    champion has no role data. Without a player (their pool is hidden) an off-role champion is just OFF_ROLE."""
    if not champion.roles:
        return None
    if champion.roles[0] == lane:
        return "MAIN"
    if lane in champion.roles:
        return "SECONDARY"
    if player is not None and champion.id in player.pool[:config["off_role"]["pool_exempt"]]:
        return "OFF_ROLE_EXEMPT"
    return "OFF_ROLE"


def off_role_penalty(champion: Champion, lane: str, player: PlayerSpec, config: dict) -> float:
    """The fraction of lane score the off-role rule takes from this player on this champion (0 when none)."""
    return round(1.0 - off_role_multiplier(champion, lane, player, config), 4) if off_role(
        champion, lane, player, config) else 0.0


# ------------------------------------------------------------------ the wheel
def wheel_summary(blue: Champion, red: Champion, blue_draft: int, red_draft: int, config: dict) -> dict:
    """Who wins the lane on the matchup wheel, how clearly, and each side's multiplier after its coach's Draft."""
    mb, mr, label = lane_matchup(blue, red, config)
    winner = kind = None
    if label:
        winner = "BLUE" if label.startswith("A") else "RED"
        kind = label.split("_")[1]
    return {
        "blue": {"strength": blue.strength, "weakness": blue.weakness},
        "red": {"strength": red.strength, "weakness": red.weakness},
        "winner": winner,
        "kind": kind,
        "blue_multiplier": round(apply_coach_draft(mb, blue_draft, config), 3),
        "red_multiplier": round(apply_coach_draft(mr, red_draft, config), 3),
    }


def average_rate(mine: int, theirs: Iterable[int], table: MatchupTable) -> float | None:
    """`mine`'s average win rate against `theirs` (pairs without data left out); None with no data."""
    rates = [r for r in (table.enemy_rate(mine, t) for t in theirs) if r is not None]
    return round(sum(rates) / len(rates), 1) if rates else None


# ------------------------------------------------------------------ expected lane score
def expected_lane_score(player: PlayerSpec, champion: Champion, lane: str, *, opponents: Mapping[str, Champion],
                        partner: Champion | None, my_draft: int, enemy_draft: int, table: MatchupTable,
                        config: dict) -> tuple[float, dict]:
    """The lane score this player would get on `champion` in `lane` with an average roll, before assists.

    opponents: the enemy champions by lane (only the lanes this one faces are read: its own, or both bot lanes
    for bot and support). partner: the bot lane partner (bot and support only). Returns (score, factors), where
    factors are the multipliers that make it up, for a breakdown."""
    lane_cfg = config["lane"]
    lo, hi = lane_cfg["roll_range"]
    weights = champion_synergy(champion, config)
    base = (lo + hi) / 2 * sum(getattr(player, s) * weights[s] for s in FIT_STATS) * lane_cfg["scale"]

    tags = effect_totals(player)
    tier = comfort_tier(player, champion.id, config)
    comfort = adjust_comfort(comfort_modifier(tier, config), tier, tags)
    factors = {
        "comfort": 1.0 + comfort,
        "playstyle": 1.0 + tags.get("lane_score", 0.0),
        "strength_fit": strength_fit(player, champion, config),
        "off_role": off_role_multiplier(champion, lane, player, config),
        "wheel": 1.0, "counter": 1.0, "duo": 1.0, "range": 1.0,
        "scaling": scaling_multiplier(champion, "lane", config),
    }

    facing = BOT_LANE if lane in BOT_LANE else (lane,)
    enemy = [opponents[l] for l in facing if l in opponents]
    direct = opponents.get(lane)
    if direct is not None:
        mine, theirs, _ = lane_matchup(champion, direct, config)
        factors["wheel"] = apply_coach_draft(mine, my_draft, config) / apply_coach_draft(theirs, enemy_draft, config)
    wr = config["win_rates"]
    if enemy:
        factors["counter"] = multiplier(counter_delta([champion.id], [c.id for c in enemy], table, config),
                                        wr["lane_counter_scale"], config)
    if partner is not None and lane in BOT_LANE:
        factors["duo"] = multiplier(ally_delta([champion.id, partner.id], table, config), wr["lane_duo_scale"], config)
    if lane != "JUNGLE":
        duo = [champion] + ([partner] if partner is not None and lane in BOT_LANE else [])
        factors["range"] = range_lane_multiplier(duo, enemy, config)

    score = base
    for value in factors.values():
        score *= value
    return score, {"comfort_tier": tier, **{k: round(v, 3) for k, v in factors.items()}}


def grade_for(percentile: float, config: dict) -> str:
    floors = config["lane_grade"]
    for grade in GRADES:
        if percentile >= floors[grade]:
            return grade
    return "F"


def lane_grade(player: PlayerSpec, champion: Champion, lane: str, candidates: Iterable[Champion], *,
               opponents: Mapping[str, Champion], partner: Champion | None, my_draft: int, enemy_draft: int,
               table: MatchupTable, config: dict) -> dict:
    """Grade `champion` for this player in this lane by where its expected lane score ranks among every
    candidate champion in the same spot (same opponents, same partner). The percentile counts the candidates
    that score lower, plus half the ties."""
    kwargs = dict(opponents=opponents, partner=partner, my_draft=my_draft, enemy_draft=enemy_draft, table=table,
                  config=config)
    score, factors = expected_lane_score(player, champion, lane, **kwargs)
    others = [expected_lane_score(player, c, lane, **kwargs)[0] for c in candidates if c.id != champion.id]
    if others:
        below = sum(s < score - 1e-9 for s in others)
        ties = sum(abs(s - score) <= 1e-9 for s in others)
        percentile = (below + ties / 2) / len(others)
    else:
        percentile = 1.0
    return {"grade": grade_for(percentile, config), "percentile": round(percentile, 3),
            "expected": round(score, 1), "factors": factors}

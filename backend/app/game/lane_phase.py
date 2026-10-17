"""Lane phase: per-player lane scores, matchup multipliers, lane assists, CS and gold at 15 min
(spec 9.1, 9.4, 9.8, 9.9)."""
from __future__ import annotations

from .config import FOCUS_TO_LANE, LANES
from .matchup import apply_coach_draft, lane_matchup
from .models import Champion, PlayerSpec
from .state import Match, PlayerState, TeamState


def champion_synergy(champion: Champion, config: dict) -> dict[str, float]:
    """Per-stat weights (aggr/aware/pos/dmg) for a champion's attributes."""
    cfg = config["lane"]["champion_synergy"]
    divisor = cfg["divisor"]
    attrs = {"damage": champion.damage, "sturdiness": champion.sturdiness, "cc": champion.cc,
             "mobility": champion.mobility, "utility": champion.utility}
    return {stat: sum(attrs[a] * w for a, w in cfg[stat].items()) / divisor
            for stat in ("aggr", "aware", "pos", "dmg")}


def strength_fit(player: PlayerSpec, champion: Champion, config: dict) -> float:
    """Lane multiplier from the player's stats behind the champion's strength (Offence/Defence/Control):
    above-average stats there raise the score, below-average ones cut it."""
    cfg = config["lane"]["strength_fit"]
    if not cfg["enabled"]:
        return 1.0
    stats = cfg["stats"][champion.strength]
    value = sum(getattr(player, s) for s in stats) / len(stats)
    lo, hi = cfg["stat_range"]
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    return max(1.0 + cfg["scale"] * (value - mid) / half, 0.0)


def raw_lane_score(player: PlayerSpec, champion: Champion, rng, config: dict) -> float:
    """sum(roll * player stat * champion synergy) over aggr/aware/pos/dmg (spec 9.1)."""
    syn = champion_synergy(champion, config)
    lo, hi = config["lane"]["roll_range"]
    score = 0.0
    for stat in ("aggr", "aware", "pos", "dmg"):
        score += rng.randint(lo, hi) * getattr(player, stat) * syn[stat]
    return score


def _focus_weight(team: TeamState, lane: str) -> float:
    """1.0 for the primary focus lane, 0.5 for the secondary, else 0."""
    for index, focus in enumerate(team.setup.focus):
        if FOCUS_TO_LANE.get(focus, focus) == lane:
            return 1.0 if index == 0 else 0.5
    return 0.0


def team_lane_multiplier(team: TeamState, lane: str, config: dict) -> float:
    ts = config["team_style"]
    if not ts["enabled"]:
        return 1.0
    mult = 1.0 + team.style_bonus("early", config)
    if "scaling" in team.setup.styles:
        mult -= ts["scaling_lane_penalty"]
    mult += ts["focus_lane_bonus"] * team.synergy_factor * _focus_weight(team, lane)
    return mult


def run_lane_phase(match: Match) -> None:
    """Compute lane scores, apply assists, hand out 15-minute gold and emit LANE_RESULT events."""
    cfg = match.config
    lane_cfg = cfg["lane"]
    blue, red = match.sides
    match.phase = "lane"
    match.minute = float(cfg["economy"]["lane_minutes"])

    # 1) matchup multipliers (determined before scoring so they actually apply)
    for lane in LANES:
        pb, pr = blue.players[lane], red.players[lane]
        mb, mr, label = lane_matchup(pb.champion, pr.champion, cfg)
        pb.matchup_multiplier = apply_coach_draft(mb, blue.coach.draft, cfg)
        pr.matchup_multiplier = apply_coach_draft(mr, red.coach.draft, cfg)
        if label:
            advantaged = "BLUE" if label.startswith("A") else "RED"
            pb.matchup_label = pr.matchup_label = f"{advantaged}_{label.split('_')[1]}"

    # 2) base scores (blue first, then red, lane by lane: fixed RNG draw order)
    for team in (blue, red):
        for lane in LANES:
            p = team.players[lane]
            raw = raw_lane_score(p.spec, p.champion, match.rng, cfg)
            score = raw * lane_cfg["scale"]
            score *= 1.0 + p.comfort
            score *= strength_fit(p.spec, p.champion, cfg)
            score *= p.matchup_multiplier
            score *= team_lane_multiplier(team, lane, cfg)
            p.base_score = max(score, lane_cfg["min_score"])

    # 3) 15-minute CS gold differences use the base scores (reference order), before assists
    gold_diffs: dict[str, float] = {}
    for lane in LANES:
        pb, pr = blue.players[lane], red.players[lane]
        gb = pb.base_score + pb.spec.cs * 10
        gr = pr.base_score + pr.spec.cs * 10
        gold_diffs[lane] = abs(gb - gr)

    # 4) lane assists computed from a snapshot of the base scores, then applied
    for team in (blue, red):
        snapshot = {l: team.players[l].base_score for l in LANES}
        assist = lane_cfg["assist"]
        boost = lane_cfg["focus_assist_boost"]
        for lane in LANES:
            total = snapshot[lane]
            for other in LANES:
                if other == lane:
                    continue
                if other == "JUNGLE":
                    frac = assist["jungle"]
                    frac *= 1.0 + boost * (1.0 if _focus_weight(team, "JUNGLE") else 0.0)
                elif other == "SUPPORT" and lane == "BOT":
                    frac = assist["support_to_bot"]
                    frac *= 1.0 + boost * (1.0 if _focus_weight(team, "SUPPORT") else 0.0)
                else:
                    frac = assist["other"]
                total += snapshot[other] * frac * team.synergy_factor
            team.players[lane].lane_score = total

    # 5) CS and gold at the end of the lane phase; the lane winner also takes the gold difference
    eco = cfg["economy"]
    for team in (blue, red):
        for lane in LANES:
            p = team.players[lane]
            factor = eco["support_cs_factor"] if lane == "SUPPORT" else 1.0
            p.cs = p.spec.cs * eco["lane_minutes"] * factor
            p.gold = p.cs * eco["gold_per_cs"]
    match.cs_minute = float(eco["lane_minutes"])

    for lane in LANES:
        pb, pr = blue.players[lane], red.players[lane]
        if pb.lane_score > pr.lane_score:
            winner = "BLUE"
            pb.gold += gold_diffs[lane]
        elif pr.lane_score > pb.lane_score:
            winner = "RED"
            pr.gold += gold_diffs[lane]
        else:
            winner = None
        match.emit("LANE_RESULT", lane=lane, winner=winner,
                   blue_player=pb.spec.id, red_player=pr.spec.id,
                   blue_champion=pb.champion.id, red_champion=pr.champion.id,
                   blue_score=round(pb.lane_score), red_score=round(pr.lane_score),
                   gold_diff=round(gold_diffs[lane]), matchup=pb.matchup_label)

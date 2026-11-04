"""Lane phase: per-player lane scores, matchup multipliers, lane assists, CS and gold at 15 min
(spec 9.1, 9.4, 9.8, 9.9)."""
from __future__ import annotations

from .comfort import off_role_multiplier
from .config import FOCUS_TO_LANE, LANES
from .matchup import apply_coach_draft, lane_matchup
from .models import Champion, PlayerSpec
from .range_waveclear import range_lane_multiplier, share_multiplier, waveclear_farm_factor, waveclear_lane_cs
from .scaling import scaling_multiplier
from .state import Match, PlayerState, TeamState
from .win_rates import ally_delta, counter_delta, multiplier


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


BOT_LANE = ("BOT", "SUPPORT")


def win_rate_lane_multiplier(match: Match, team: TeamState, lane: str) -> float:
    """Lane score multiplier from the win rate matrices: the champion against its lane opponent(s) (bot and
    support each face both enemy bot laners) and, in the bot lane, the duo's same-team win rate."""
    cfg = match.config
    wr = cfg["win_rates"]
    enemy = match.other(team)
    mine = team.players[lane].champion.id
    opponents = BOT_LANE if lane in BOT_LANE else (lane,)
    delta = counter_delta([mine], [enemy.players[l].champion.id for l in opponents], match.matchups, cfg)
    mult = multiplier(delta, wr["lane_counter_scale"], cfg)
    if lane in BOT_LANE:
        duo = ally_delta([team.players[l].champion.id for l in BOT_LANE], match.matchups, cfg)
        mult *= multiplier(duo, wr["lane_duo_scale"], cfg)
    return mult


def range_lane_factor(match: Match, team: TeamState, lane: str) -> float:
    """Lane score multiplier from range: top and mid compare their champion with the lane opponent's, bot and
    support compare their duo's average range with the enemy duo's. The jungle has no lane opponent."""
    if lane == "JUNGLE":
        return 1.0
    enemy = match.other(team)
    lanes = BOT_LANE if lane in BOT_LANE else (lane,)
    return range_lane_multiplier([team.players[l].champion for l in lanes],
                                 [enemy.players[l].champion for l in lanes], match.config)


def _assist_fraction(lane: str, other: str, lane_cfg: dict, team: TeamState | None = None) -> float:
    """Share of `other`'s base score added to `lane`'s. Given a team, its jungle/support focus boost applies."""
    assist = lane_cfg["assist"]
    if other == "JUNGLE":
        frac, helper = assist["jungle"], "JUNGLE"
    elif other == "SUPPORT" and lane == "BOT":
        frac, helper = assist["support_to_bot"], "SUPPORT"
    else:
        return assist["other"]
    if team is not None and _focus_weight(team, helper):
        frac *= 1.0 + lane_cfg["focus_assist_boost"]
    return frac


def assist_totals(config: dict) -> dict[str, float]:
    """Each lane's score as a multiple of its base score when every teammate has the same base score."""
    lane_cfg = config["lane"]
    return {l: 1.0 + sum(_assist_fraction(l, o, lane_cfg) for o in LANES if o != l) for l in LANES}


def role_factors(config: dict) -> dict[str, float]:
    """Per-lane multiplier that evens out the roles' assist shares (all 1.0 when `normalise_assists` is off)."""
    totals = assist_totals(config)
    if not config["lane"]["normalise_assists"]:
        return {l: 1.0 for l in LANES}
    mean = sum(totals.values()) / len(totals)
    return {l: mean / t for l, t in totals.items()}


def lane_cs_multiplier(team: TeamState, enemy: TeamState, lane: str, config: dict) -> float:
    """Lane-phase CS multiplier. Bot farms more when their support wins the support matchup; top and mid farm
    more when their jungler wins the jungle matchup and when the team focuses their lane. Top, mid and bot also
    farm more when they out-clear their lane opponent."""
    cfg = config["cs"]
    if lane == "BOT":
        mult = share_multiplier(team.players["SUPPORT"].lane_score, enemy.players["SUPPORT"].lane_score,
                                cfg["support_scale"])
    elif lane in ("TOP", "MID"):
        mult = share_multiplier(team.players["JUNGLE"].lane_score, enemy.players["JUNGLE"].lane_score,
                                cfg["jungle_scale"])
        mult += cfg["focus_bonus"] * team.synergy_factor * _focus_weight(team, lane)
    else:
        return 1.0
    return mult * waveclear_lane_cs(team.players[lane].champion, enemy.players[lane].champion, config)


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

    # 2) base scores (blue first, then red, lane by lane: fixed RNG draw order). `unscaled` is the same
    #    score without the lane phase's champion scaling, which fights take back out.
    unscaled: dict[str, dict[str, float]] = {"BLUE": {}, "RED": {}}
    for team in (blue, red):
        for lane in LANES:
            p = team.players[lane]
            raw = raw_lane_score(p.spec, p.champion, match.rng, cfg)
            score = raw * lane_cfg["scale"]
            score *= 1.0 + p.comfort
            score *= 1.0 + p.tag("lane_score")
            score *= strength_fit(p.spec, p.champion, cfg)
            score *= off_role_multiplier(p.champion, lane, p.spec, cfg)
            score *= p.matchup_multiplier
            score *= team_lane_multiplier(team, lane, cfg)
            score *= win_rate_lane_multiplier(match, team, lane)
            score *= range_lane_factor(match, team, lane)
            unscaled[team.side][lane] = max(score, lane_cfg["min_score"])
            p.base_score = max(score * scaling_multiplier(p.champion, "lane", cfg), lane_cfg["min_score"])

    # 3) lane assists from a snapshot of the base scores, then each role's total assist share is evened out
    factors = role_factors(cfg)
    for team in (blue, red):
        snapshot = {l: team.players[l].base_score for l in LANES}
        flat = unscaled[team.side]
        for lane in LANES:
            total, total_unscaled = snapshot[lane], flat[lane]
            for other in LANES:
                if other == lane:
                    continue
                frac = _assist_fraction(lane, other, lane_cfg, team) * team.synergy_factor
                total += snapshot[other] * frac
                total_unscaled += flat[other] * frac
            p = team.players[lane]
            p.lane_score = total * factors[lane]
            p.lane_unscaled_ratio = total_unscaled / total

    # 4) CS and gold at the end of the lane phase (the lane multiplier covers these minutes only); from here on
    #    the champion's waveclear speeds up or slows down farming. The lane winner also takes their lead as gold
    eco = cfg["economy"]
    for team in (blue, red):
        for lane in LANES:
            p = team.players[lane]
            p.cs = p.cs_rate * eco["lane_minutes"] * lane_cs_multiplier(team, match.other(team), lane, cfg)
            p.gold = p.cs * eco["gold_per_cs"]
            p.cs_rate *= waveclear_farm_factor(p.champion, cfg)
    match.cs_minute = float(eco["lane_minutes"])

    # the lead is the lane score margin (brought back to base-score size) plus the CS stat difference
    assist_mean = sum(assist_totals(cfg).values()) / len(LANES)
    for lane in LANES:
        pb, pr = blue.players[lane], red.players[lane]
        winner, gold = None, 0.0
        if pb.lane_score != pr.lane_score:
            winner = "BLUE" if pb.lane_score > pr.lane_score else "RED"
            w, l = (pb, pr) if winner == "BLUE" else (pr, pb)
            gold = max((w.lane_score - l.lane_score) / assist_mean + (w.spec.cs - l.spec.cs) * 10, 0.0)
            w.gold += gold
        match.emit("LANE_RESULT", lane=lane, winner=winner,
                   blue_player=pb.spec.id, red_player=pr.spec.id,
                   blue_champion=pb.champion.id, red_champion=pr.champion.id,
                   blue_score=round(pb.lane_score), red_score=round(pr.lane_score),
                   gold_diff=round(gold), matchup=pb.matchup_label,
                   counter_rate=match.matchups.enemy_rate(pb.champion.id, pr.champion.id))

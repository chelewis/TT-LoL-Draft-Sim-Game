"""Skirmishes and teamfights (spec 9.3, 9.7)."""
from __future__ import annotations

from .objectives import siege
from .state import PHASE_SCALING_WEIGHT, Match, PlayerState, TeamState
from .win_rates import ally_delta, counter_delta, multiplier


def skill_check(player: PlayerState, rng, config: dict) -> float:
    """Percent performance swing. Difficulty amplifies the comfort effect between 1x and Dx.

    Positive comfort on a hard champion has a higher ceiling; negative comfort on a hard
    champion is more punishing. Scaled by `skill_check.scale`.
    """
    c = player.comfort * 100.0
    d = player.champion.difficulty
    lo, hi = sorted((c, c * d))
    return rng.uniform(lo, hi) * config["skill_check"]["scale"]


def fight_multiplier(match: Match, team: TeamState, size: int) -> float:
    """Team-style and elder multipliers for a fight of `size` players."""
    cfg = match.config
    mult = 1.0
    if cfg["team_style"]["enabled"]:
        if match.phase == "early":
            mult += team.style_bonus("early", cfg)
        mult += team.style_bonus("scaling", cfg) * PHASE_SCALING_WEIGHT.get(match.phase, 0.0)
        mult += team.style_bonus("teamfight", cfg) if size >= 4 else 0.0
        mult += team.style_bonus("skirmish", cfg) if size <= 3 else 0.0
    if team.elder_fights > 0:
        mult += cfg["objectives"]["elder_bonus"]
    return mult


def damage_effectiveness(match: Match, team: TeamState) -> float:
    """Share of this team's damage that still lands once the enemy has itemized against its damage profile.
    The penalty comes from the whole comp, scaled by how far into the game we are."""
    cfg = match.config["damage_balance"]
    weight = cfg["phase_weights"].get(match.phase, 0.0)
    return max(1.0 - team.damage_balance_penalty(match.config) * weight, 0.0)


def win_rate_fight_multiplier(match: Match, members: list[PlayerState], enemies: list[PlayerState]) -> float:
    """Same-team synergy among these fighters and their win rate against the enemy fighters."""
    cfg = match.config
    wr = cfg["win_rates"]
    mine = [p.champion.id for p in members]
    theirs = [p.champion.id for p in enemies]
    mult = multiplier(counter_delta(mine, theirs, match.matchups, cfg), wr["fight_counter_scale"], cfg)
    if len(mine) >= 2:
        mult *= multiplier(ally_delta(mine, match.matchups, cfg), wr["fight_synergy_scale"], cfg)
    return mult


def _performance(match: Match, p: PlayerState) -> float:
    base = (p.lane_score + p.gold) / 2.0
    return max(1.0, base * (1.0 + skill_check(p, match.rng, match.config) / 100.0))


def _side_power(match: Match, team: TeamState, members: list[PlayerState], perf: dict[str, float],
                enemies: list[PlayerState]) -> float:
    f = match.config["fight"]
    damage_weight = f["damage_weight"] * damage_effectiveness(match, team)
    weighted = sum(perf[p.lane] * (damage_weight * p.champion.damage
                                   + f["sturdiness_weight"] * p.champion.sturdiness) for p in members)
    n = len(members)
    control = sum(p.champion.cc + p.champion.mobility + p.champion.utility for p in members) / n
    control_mod = 1.0 + f["control_scale"] * (control - f["control_average"]) / f["control_average"]
    return (weighted * max(control_mod, 0.1) * fight_multiplier(match, team, n)
            * win_rate_fight_multiplier(match, members, enemies))


def _choose_weighted_distinct(rng, candidates: list[PlayerState], weights: dict[str, float], k: int) -> list[PlayerState]:
    pool = list(candidates)
    chosen: list[PlayerState] = []
    for _ in range(min(k, len(pool))):
        pick = rng.choices(pool, weights=[max(weights[p.lane], 1e-9) for p in pool], k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen


def run_fight(match: Match, attacker: TeamState, defender: TeamState, n_att: int, n_def: int, kind: str) -> None:
    rng = match.rng
    cfg = match.config["fight"]
    eco = match.config["economy"]
    att = rng.sample(attacker.ordered_players(), n_att)
    dfn = rng.sample(defender.ordered_players(), n_def)
    perf_a = {p.lane: _performance(match, p) for p in att}
    perf_d = {p.lane: _performance(match, p) for p in dfn}

    power_a = _side_power(match, attacker, att, perf_a, dfn)
    power_d = _side_power(match, defender, dfn, perf_d, att)
    dominance = abs(power_a - power_d) / (power_a + power_d)

    kills_a = kills_d = 0
    winner = None
    if dominance >= cfg["even_threshold"]:
        winner = attacker if power_a > power_d else defender
        w_members, l_members = (att, dfn) if winner is attacker else (dfn, att)
        n_loser = len(l_members)
        wk = round(dominance * cfg["dominance_scale"] * n_loser + rng.uniform(-0.5, 0.5))
        wk = min(n_loser, max(1, wk))
        lk = 0 if wk >= n_loser else min(len(w_members), rng.randint(0, wk))
        if winner is attacker:
            kills_a, kills_d = wk, lk
        else:
            kills_d, kills_a = wk, lk

    a_events = _resolve_pair(match, att, dfn, perf_a, perf_d, kills_a)
    d_events = _resolve_pair(match, dfn, att, perf_d, perf_a, kills_d)

    for killer, victim in a_events + d_events:
        killer.kills += 1
        killer.gold += eco["kill"]
        victim.deaths += 1
    for members, events in ((att, a_events), (dfn, d_events)):
        for p in members:
            own = sum(1 for k, _ in events if k is p)
            assists = len(events) - own
            p.assists += assists
            p.gold += eco["assist"] * assists
    attacker.kills += kills_a
    defender.kills += kills_d

    for team in (attacker, defender):
        if team.elder_fights > 0:
            team.elder_fights -= 1

    if winner is not None:
        winner.fights_won += 1
    match.emit("FIGHT", kind=kind, attacker=attacker.side, defender=defender.side,
               attackers=[p.lane for p in att], defenders=[p.lane for p in dfn],
               winner=winner.side if winner else None,
               kills={attacker.side: kills_a, defender.side: kills_d},
               log=[{"killer": k.champion.name, "victim": v.champion.name, "team": k.team}
                    for k, v in a_events + d_events])

    if winner is not None:
        won_kills = kills_a if winner is attacker else kills_d
        if won_kills >= match.config["structures"]["siege_min_kills"]:
            siege(match, winner, won_kills, reason=kind.lower())


def _resolve_pair(match: Match, killers: list[PlayerState], victims: list[PlayerState],
                  killer_perf: dict[str, float], victim_perf: dict[str, float], count: int):
    if count <= 0:
        return []
    total = sum(victim_perf.values())
    death_weights = {p.lane: max(total - victim_perf[p.lane], 1e-9) for p in victims}
    dying = _choose_weighted_distinct(match.rng, victims, death_weights, count)
    return [(match.rng.choices(killers, weights=[killer_perf[k.lane] for k in killers], k=1)[0], v)
            for v in dying]

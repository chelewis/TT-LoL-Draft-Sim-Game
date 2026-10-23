"""Match simulation orchestrator (spec 8-10).

    result = simulate_match(blue_team, red_team, champions, seed, config, matchups)

Pure function of its inputs: same teams + seed + config -> identical result and event log.
"""
from __future__ import annotations

from typing import Mapping

from .config import LANES, simulation_config
from .fights import run_fight
from .lane_phase import run_lane_phase
from .models import Champion, MatchResult, MatchupTable, TeamSetup
from .objectives import roll_baron, roll_dragon, roll_tower
from .ranking import assign_ranks, pick_mvp_and_ace
from .scaling import comp_scaling
from .state import Match, PlayerState, TeamState
from .win_rates import ally_delta


def _weighted_count(rng, maximum: int) -> int:
    """Number of towers in a phase: 0..maximum with probability decreasing as 1/(i+1)."""
    if maximum <= 0:
        return 0
    return rng.choices(range(maximum + 1), weights=[1.0 / (i + 1) for i in range(maximum + 1)], k=1)[0]


def _schedule(match: Match, phase: dict, start: float, end: float) -> list[tuple[float, str, dict]]:
    """Randomly place a phase's objective and fight events on its timeline."""
    rng = match.rng
    events: list[tuple[float, str, dict]] = []
    for _ in range(rng.randint(0, phase["max_dragons"])):
        events.append((rng.uniform(start, end), "dragon", {}))
    for _ in range(rng.randint(0, phase["max_barons"])):
        events.append((rng.uniform(start, end), "baron", {}))
    for _ in range(_weighted_count(rng, phase["max_towers"])):
        events.append((rng.uniform(start, end), "tower", {}))
    lo, hi = phase["skirmishes"]
    for _ in range(rng.randint(lo, hi)):
        n_att = rng.randint(*phase["skirmish_size"])
        n_def = rng.randint(1, n_att)
        events.append((rng.uniform(start, end), "skirmish", {"n_att": n_att, "n_def": n_def}))
    lo, hi = phase["teamfights"]
    for _ in range(rng.randint(lo, hi)):
        n_att = rng.randint(*phase["teamfight_size"])
        n_def = rng.randint(*phase["teamfight_size"])
        events.append((rng.uniform(start, end), "teamfight", {"n_att": n_att, "n_def": n_def}))
    events.sort(key=lambda e: e[0])
    return events


def _run_events(match: Match, events: list[tuple[float, str, dict]]) -> None:
    for minute, kind, params in events:
        if match.ended:
            return
        match.minute = minute
        match.update_cs(minute)
        if kind == "dragon":
            roll_dragon(match)
        elif kind == "baron":
            roll_baron(match)
        elif kind == "tower":
            roll_tower(match)
        else:
            blue, red = match.sides
            # the more aggressive team starts more fights, and so brings the bigger group to skirmishes
            attacker, defender = (blue, red) if match.rng.random() < match.initiative_chance(blue) else (red, blue)
            run_fight(match, attacker, defender, params["n_att"], params["n_def"], kind.upper())


def _run_phase(match: Match, phase: dict, name: str | None = None) -> None:
    match.phase = name or phase["name"]
    start, end = phase["minutes"]
    match.minute = float(start)
    match.emit("PHASE_START", name=match.phase)
    _run_events(match, _schedule(match, phase, start, end))


def _timeout_winner(match: Match) -> str:
    """No nexus fell: structures destroyed, then team gold, then a seeded coin flip."""
    weights = match.config["structures"]["timeout_weights"]
    blue, red = match.sides
    # structures a team destroyed = the enemy's destroyed structures
    sb, sr = red.structures.score(weights), blue.structures.score(weights)
    if sb != sr:
        return "BLUE" if sb > sr else "RED"
    if round(blue.gold) != round(red.gold):
        return "BLUE" if blue.gold > red.gold else "RED"
    return "BLUE" if match.rng.random() < 0.5 else "RED"


def _player_dict(p: PlayerState) -> dict:
    return {
        "player_id": p.spec.id, "name": p.spec.name, "team": p.team, "lane": p.lane,
        "champion_id": p.champion.id, "champion": p.champion.name,
        "comfort_tier": p.tier, "lane_score": round(p.lane_score, 1),
        "kills": p.kills, "deaths": p.deaths, "assists": p.assists,
        "cs": round(p.cs), "gold": round(p.gold),
        "damage_dealt": p.damage_dealt, "damage_taken": p.damage_taken,
    }


def _team_dict(match: Match, team: TeamState) -> dict:
    enemy = match.other(team)
    wr = [p.champion.win_rate for p in team.players.values()]
    return {
        "name": team.name,
        "gold": round(team.gold),
        "kills": team.kills,
        "towers": enemy.structures.total_towers_down,
        "inhibitors": enemy.structures.inhibitors_down,
        "dragons": team.dragons,
        "barons": team.barons,
        "soul": team.soul,
        "structures_lost": {"towers": team.structures.total_towers_down,
                            "inhibitors": team.structures.inhibitors_down,
                            "nexus": team.structures.nexus_destroyed},
        "comp": {"win_rate": round(sum(wr) / len(wr), 2), "damage_profile": team.damage_profile(),
                 "damage_penalty": round(team.damage_balance_penalty(match.config), 3),
                 "ally_synergy": round(ally_delta([p.champion.id for p in team.ordered_players()],
                                                  match.matchups, match.config), 1),
                 "scaling": comp_scaling(p.champion for p in team.players.values())},
    }


def _lane_dicts(match: Match) -> dict[str, dict]:
    lanes = {}
    for e in match.events:
        if e.type == "LANE_RESULT":
            p = e.payload
            lanes[p["lane"]] = {
                "blue_player": p["blue_player"], "red_player": p["red_player"],
                "blue_champion": p["blue_champion"], "red_champion": p["red_champion"],
                "blue_score": p["blue_score"], "red_score": p["red_score"],
                "gold_diff": p["gold_diff"], "winner": p["winner"], "matchup": p["matchup"],
                "counter_rate": p["counter_rate"],
            }
    return lanes


def simulate_match(blue: TeamSetup, red: TeamSetup, champions: Mapping[int, Champion],
                   seed: int, config: dict | None = None, matchups: MatchupTable | None = None) -> MatchResult:
    cfg = config or simulation_config()
    match = Match(blue, red, champions, seed, cfg, matchups)

    run_lane_phase(match)
    for phase in cfg["phases"]:
        _run_phase(match, phase)
        if match.ended:
            break

    if not match.ended:
        ot = cfg["overtime"]
        start = float(cfg["phases"][-1]["minutes"][1])
        for round_index in range(ot["max_rounds"]):
            window = {**ot, "minutes": [start, start + ot["round_minutes"]]}
            _run_phase(match, window, name="overtime")
            start += ot["round_minutes"]
            if match.ended:
                break

    if match.ended:
        duration = int(match.end_minute * 60)
        end_minute = match.end_minute
    else:
        match.minute = start
        winner = _timeout_winner(match)
        match.emit("TIMEOUT", winner=winner)
        match.end(winner, "TIMEOUT")
        duration = int(start * 60)
        end_minute = start

    match.update_cs(end_minute)
    match.emit("GAME_END", winner=match.winner, win_condition=match.win_condition, duration_seconds=duration)

    players = [_player_dict(p) for team in match.sides for p in team.ordered_players()]
    assign_ranks(players, match.rng)
    mvp, ace = pick_mvp_and_ace(players, match.winner)

    blue_t, red_t = match.sides
    return MatchResult(
        simulation_version=cfg["version"],
        seed=seed,
        winner=match.winner,
        win_condition=match.win_condition,
        duration_seconds=duration,
        mvp={k: mvp[k] for k in ("player_id", "name", "champion", "team")},
        ace={k: ace[k] for k in ("player_id", "name", "champion", "team")},
        teams={"BLUE": _team_dict(match, blue_t), "RED": _team_dict(match, red_t)},
        lanes=_lane_dicts(match),
        players=players,
        events=match.events,
    )

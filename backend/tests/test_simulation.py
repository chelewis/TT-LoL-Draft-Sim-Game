import copy
import random

import pytest

from app.data.loader import seed_team_setup
from app.game.config import LANES, simulation_config
from app.game.simulation_engine import simulate_match


def run(make_teams, champions, team_seed=1, seed=42, cfg=None):
    blue, red = make_teams(team_seed)
    return simulate_match(blue, red, champions, seed, cfg)


def test_same_seed_reproduces_result_and_events(make_teams, champions):
    a = run(make_teams, champions, seed=99)
    b = run(make_teams, champions, seed=99)
    assert a.to_dict() == b.to_dict()


def test_events_carry_gold_from_everything_but_cs(make_teams, champions):
    res = run(make_teams, champions, seed=7)
    per_cs = simulation_config()["economy"]["gold_per_cs"]
    for e in res.events:
        gold = e.payload["event_gold"]
        assert all(len(gold[side]) == len(LANES) and min(gold[side]) >= 0 for side in ("BLUE", "RED"))
    final = res.events[-1].payload["event_gold"]
    for p in res.players:
        other_gold = final[p["team"]][LANES.index(p["lane"])]
        # the result rounds CS, so the rebuilt total can be off by up to one creep's gold
        assert abs(other_gold + p["cs"] * per_cs - p["gold"]) <= per_cs


def test_different_seeds_differ(make_teams, champions):
    results = {run(make_teams, champions, seed=s).duration_seconds for s in range(10)}
    assert len(results) > 1


def test_back_to_back_simulations_are_independent(make_teams, champions):
    first = run(make_teams, champions, seed=5).to_dict()
    run(make_teams, champions, team_seed=9, seed=6)
    again = run(make_teams, champions, seed=5).to_dict()
    assert first == again


def test_config_not_mutated(make_teams, champions):
    cfg = simulation_config()
    snapshot = copy.deepcopy(cfg)
    run(make_teams, champions, cfg=cfg)
    assert cfg == snapshot


@pytest.mark.parametrize("n", range(25))
def test_invariants(make_teams, champions, n):
    res = run(make_teams, champions, team_seed=n, seed=n)
    players = res.players
    assert len(players) == 10
    blue = [p for p in players if p["team"] == "BLUE"]
    red = [p for p in players if p["team"] == "RED"]
    # kills == deaths across the match, and per-team kills match player kills
    assert sum(p["kills"] for p in players) == sum(p["deaths"] for p in players)
    assert sum(p["kills"] for p in blue) == res.teams["BLUE"]["kills"]
    assert sum(p["kills"] for p in red) == res.teams["RED"]["kills"]
    assert all(p["gold"] >= 0 for p in players)
    assert sorted(p["rank"] for p in players) == list(range(1, 11))
    # one champion per player, no champion twice
    assert len({p["champion_id"] for p in players}) == 10
    # structures
    for side, other in (("BLUE", "RED"), ("RED", "BLUE")):
        lost = res.teams[other]["structures_lost"]
        assert res.teams[side]["towers"] <= 11
        assert lost["towers"] == res.teams[side]["towers"]
    # winner
    assert res.winner in ("BLUE", "RED")
    loser = "RED" if res.winner == "BLUE" else "BLUE"
    if res.win_condition == "NEXUS":
        assert res.teams[loser]["structures_lost"]["nexus"] is True
        assert res.teams[res.winner]["structures_lost"]["nexus"] is False
    # MVP is on the winning team; ACE has the best rank
    assert res.mvp["team"] == res.winner
    assert next(p for p in players if p["player_id"] == res.ace["player_id"])["rank"] == 1
    # the game stops when the nexus falls: nothing but the siege summary follows it
    types = [e.type for e in res.events]
    if "NEXUS" in types:
        after = types[types.index("NEXUS") + 1:]
        assert set(after) <= {"SIEGE", "GAME_END"}
    assert res.duration_seconds >= 15 * 60


def test_soul_only_claimed_once_and_dragon_pool(make_teams, champions):
    for seed in range(40):
        res = run(make_teams, champions, team_seed=seed, seed=seed)
        souls = [e for e in res.events if e.type == "DRAGON_SOUL"]
        assert len(souls) <= 1
        assert len([e for e in res.events if e.type == "DRAGON"]) <= 7
        if souls:
            first_soul = res.events.index(souls[0])
            assert not any(e.type == "ELDER_DRAGON" for e in res.events[:first_soul])


def test_late_game_and_overtime_run_only_when_needed(make_teams, champions):
    phases_seen = set()
    for seed in range(60):
        res = run(make_teams, champions, team_seed=seed, seed=seed)
        phases = [e.phase for e in res.events]
        phases_seen.update(phases)
        if "overtime" in phases:
            assert "late" in phases
        if res.win_condition == "TIMEOUT":
            assert "overtime" in phases and res.duration_seconds >= 35 * 60
    assert {"lane", "early", "mid", "late"} <= phases_seen


def test_nexus_cannot_fall_before_minimum_minute(make_teams, champions):
    for seed in range(60):
        res = run(make_teams, champions, team_seed=seed, seed=seed)
        if res.win_condition == "NEXUS":
            assert res.duration_seconds >= 18 * 60


def test_timeout_tiebreaker(make_teams, champions):
    # the nexus gate is set beyond the game's end, so no game can be won by a nexus
    cfg = simulation_config({"structures": {"nexus_min_minute": 999}})
    blue, red = make_teams(3)
    res = simulate_match(blue, red, champions, 11, cfg)
    assert res.win_condition == "TIMEOUT"
    assert res.duration_seconds >= 35 * 60
    assert any(e.type == "TIMEOUT" for e in res.events)
    w = cfg["structures"]["timeout_weights"]

    def score(lost):
        return lost["towers"] * w["tower"] + lost["inhibitors"] * w["inhibitor"]

    blue_score = score(res.teams["RED"]["structures_lost"])
    red_score = score(res.teams["BLUE"]["structures_lost"])
    if blue_score != red_score:
        assert res.winner == ("BLUE" if blue_score > red_score else "RED")
    elif round(res.teams["BLUE"]["gold"]) != round(res.teams["RED"]["gold"]):
        assert res.winner == ("BLUE" if res.teams["BLUE"]["gold"] > res.teams["RED"]["gold"] else "RED")


def test_invalid_lineups_rejected(make_teams, champions):
    blue, red = make_teams(1)
    dup = dict(blue.lineup)
    dup["TOP"] = dup["MID"]
    blue.lineup = dup
    with pytest.raises(ValueError, match="duplicate"):
        simulate_match(blue, red, champions, 1)
    blue, red = make_teams(1)
    del blue.lineup["TOP"]
    with pytest.raises(ValueError, match="missing"):
        simulate_match(blue, red, champions, 1)


def test_best_pool_picks_beat_off_pool_picks(seed, champions):
    """Drafting matters: comfort picks win more often than off-pool picks for the same team."""
    rng = random.Random(1)
    pools = {lane: seed.pools[seed.rosters[1][lane]] for lane in LANES}
    good = {lane: pools[lane][0] for lane in LANES}
    assert len(set(good.values())) == 5
    in_pool = {c for p in pools.values() for c in p}
    others = [c for c in champions if c not in in_pool]
    wins_good = wins_off = 0
    for i in range(60):
        chosen = rng.sample(others, 10)
        off, opp = dict(zip(LANES, chosen[:5])), dict(zip(LANES, chosen[5:]))
        wins_good += simulate_match(seed_team_setup(seed, 1, good), seed_team_setup(seed, 2, opp),
                                    champions, i).winner == "BLUE"
        wins_off += simulate_match(seed_team_setup(seed, 1, off), seed_team_setup(seed, 2, opp),
                                   champions, i).winner == "BLUE"
    assert wins_good > wins_off

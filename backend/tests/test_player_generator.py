"""Generated CPU teams: complete, valid and sized to the season's rules."""
import random

import pytest

from app.game import player_generator as gen
from app.game.config import LANES, LOBBY_RULESETS_BY_KEY, MANAGEMENT_CONFIG

STATS = ("aggr", "aware", "pos", "dmg", "cs")


@pytest.fixture(scope="module")
def engine_champions(seed):
    return list(seed.champions)       # the loader's engine champions, with roles and pick rates


def _rules(key):
    return LOBBY_RULESETS_BY_KEY[key]["settings"]


@pytest.mark.parametrize("key", list(LOBBY_RULESETS_BY_KEY))
@pytest.mark.parametrize("strength", gen.STRENGTHS)
def test_generated_teams_fit_the_ruleset(key, strength, engine_champions):
    rules = _rules(key)
    rng = random.Random(7)
    for _ in range(5):
        team = gen.generate_team(rules, strength, engine_champions, rng)
        assert set(team["roster"]) == set(LANES)
        totals = [sum(p[s] for s in STATS) for p in team["roster"].values()]
        if rules["max_player_total"] is not None:
            assert max(totals) <= rules["max_player_total"]
        if rules["max_team_total"] is not None:
            assert sum(totals) <= rules["max_team_total"]
        lo, hi = MANAGEMENT_CONFIG["stat_range"]
        for lane, p in team["roster"].items():
            assert p["role"] == lane
            assert all(lo <= p[s] <= hi for s in STATS)
            assert len(p["pool"]) == len(set(p["pool"])) == MANAGEMENT_CONFIG["champion_pool_size"]
        assert team["style1"] != team["style2"] and team["focus1"] != team["focus2"]
        assert team["coach"]["draft"] + team["coach"]["synergy"] <= MANAGEMENT_CONFIG["coach_stat_budget"]


def test_stronger_teams_have_more_stats(engine_champions):
    rules = _rules("ANYTHING_GOES")

    def average(strength):
        rng = random.Random(3)
        teams = [gen.generate_team(rules, strength, engine_champions, rng) for _ in range(20)]
        return sum(sum(p[s] for s in STATS) for t in teams for p in t["roster"].values()) / 100

    assert average("WEAKER") < average("EVEN") < average("STRONGER")


def test_pools_come_from_the_lane(engine_champions):
    rng = random.Random(11)
    for lane in LANES:
        pool = gen.champion_pool(lane, engine_champions, rng)
        by_id = {c.id: c for c in engine_champions}
        assert all(lane in by_id[cid].roles for cid in pool)


def test_names_never_repeat(engine_champions):
    rng = random.Random(5)
    names, team_names = set(), set()
    for _ in range(16):
        team = gen.generate_team(_rules("ANYTHING_GOES"), "EVEN", engine_champions, rng, names, team_names)
        new = [p["name"].lower() for p in team["roster"].values()]
        assert not set(new) & names
        assert team["name"].lower() not in team_names
        names |= set(new)
        team_names.add(team["name"].lower())


def test_same_seed_same_team(engine_champions):
    a = gen.generate_team(_rules("PRO"), "EVEN", engine_champions, random.Random(42))
    b = gen.generate_team(_rules("PRO"), "EVEN", engine_champions, random.Random(42))
    assert a == b


def test_distribute_respects_bounds():
    rng = random.Random(1)
    for total in (3, 5, 27, 50, 70):
        stats = gen.distribute(total, {k: 1.0 for k in STATS}, rng)
        assert all(1 <= v <= 10 for v in stats.values())
        assert sum(stats.values()) == max(5, min(50, total))

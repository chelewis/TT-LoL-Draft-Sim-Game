"""Balance rules: the skill check, role-normalised lane assists, fight initiative and lane gold."""
import dataclasses
import random

import pytest

from app.game.config import LANES, simulation_config
from app.game.fights import dmg_stat_multiplier, skill_check
from app.game.lane_phase import assist_totals, role_factors, run_lane_phase
from app.game.simulation_engine import simulate_match
from app.game.state import Match


def match_for(make_teams, champions, team_seed=1, cfg=None):
    blue, red = make_teams(team_seed)
    return Match(blue, red, champions, 1, cfg or simulation_config())


def fighter(match, difficulty, comfort):
    p = match.teams["BLUE"].players["TOP"]
    p.champion = dataclasses.replace(p.champion, difficulty=difficulty)
    p.comfort = comfort
    return p


def rolls(match, p, n=4000):
    rng = random.Random(3)
    return [skill_check(p, rng, match.config) for _ in range(n)]


# ------------------------------------------------------------- skill check
def test_easy_champion_has_no_variance(make_teams, champions):
    match = match_for(make_teams, champions)
    scale = match.config["skill_check"]["scale"]
    for comfort in (0.40, 0.10, -0.10):
        assert all(r == pytest.approx(comfort * 100 * scale) for r in rolls(match, fighter(match, 1, comfort), 50))


def test_hard_champion_has_higher_ceiling_and_can_fail(make_teams, champions):
    match = match_for(make_teams, champions)
    easy = rolls(match, fighter(match, 1, 0.40))[0]
    hard = rolls(match, fighter(match, 3, 0.40))
    assert max(hard) > easy and min(hard) < easy
    assert sum(hard) / len(hard) == pytest.approx(easy, abs=1.0)    # mastered: same average, more variance


def test_unpractised_hard_champion_is_punished(make_teams, champions):
    match = match_for(make_teams, champions)
    for comfort in (0.10, -0.10):                                     # below mastery: FAMILIAR, VULNERABLE
        easy = rolls(match, fighter(match, 1, comfort))[0]
        hard = rolls(match, fighter(match, 3, comfort))
        assert sum(hard) / len(hard) < easy - 1.0


def test_dmg_stat_scales_fight_performance(make_teams, champions):
    match = match_for(make_teams, champions)
    p = match.teams["BLUE"].players["TOP"]
    values = {}
    for dmg in (1, 10):
        p.spec = dataclasses.replace(p.spec, dmg=dmg)
        values[dmg] = dmg_stat_multiplier(p, match.config)
    scale = match.config["fight"]["dmg_stat_scale"]
    assert values[1] == pytest.approx(1 - scale) and values[10] == pytest.approx(1 + scale)


# ------------------------------------------------------------- lane assists
def test_equal_players_get_equal_lane_scores_in_every_role():
    cfg = simulation_config()
    totals, factors = assist_totals(cfg), role_factors(cfg)
    assert totals["BOT"] > totals["TOP"] > totals["JUNGLE"]          # the raw shares differ by role
    evened = {l: totals[l] * factors[l] for l in LANES}
    assert max(evened.values()) == pytest.approx(min(evened.values()))
    off = simulation_config({"lane": {"normalise_assists": False}})
    assert set(role_factors(off).values()) == {1.0}


def test_lane_scaling_is_taken_out_of_fights(make_teams, champions):
    neutral = {cid: dataclasses.replace(c, scaling=2) for cid, c in champions.items()}
    blue, red = make_teams(2)
    match = Match(blue, red, neutral, 1, simulation_config())
    run_lane_phase(match)
    assert all(p.lane_unscaled_ratio == pytest.approx(1.0)
               for t in match.sides for p in t.players.values())

    early = dict(neutral)
    early[blue.lineup["TOP"]] = dataclasses.replace(neutral[blue.lineup["TOP"]], scaling=1)
    match = Match(blue, red, early, 1, simulation_config())
    run_lane_phase(match)
    assert match.teams["BLUE"].players["TOP"].lane_unscaled_ratio < 1.0


def test_lane_winner_is_paid_their_lead_and_only_they_are(make_teams, champions):
    for n in range(15):
        blue, red = make_teams(n)
        res = simulate_match(blue, red, champions, n)
        lane_results = [e for e in res.events if e.type == "LANE_RESULT"]
        final = lane_results[-1].payload["event_gold"]
        for e in lane_results:
            lane, winner, gold = e.payload["lane"], e.payload["winner"], e.payload["gold_diff"]
            assert gold >= 0
            for side in ("BLUE", "RED"):
                paid = final[side][LANES.index(lane)]
                assert paid == (gold if side == winner else 0)


# ------------------------------------------------------------- fight initiative
def test_more_aggressive_team_starts_more_fights(make_teams, champions):
    match = match_for(make_teams, champions)
    blue, red = match.sides
    for team in (blue, red):
        for p in team.players.values():
            p.spec = dataclasses.replace(p.spec, aggr=5)
    assert match.initiative_chance(blue) == pytest.approx(0.5)

    for p in blue.players.values():
        p.spec = dataclasses.replace(p.spec, aggr=7)
    assert match.initiative_chance(blue) > 0.5
    assert match.initiative_chance(blue) + match.initiative_chance(red) == pytest.approx(1.0)

    for p in blue.players.values():
        p.spec = dataclasses.replace(p.spec, aggr=10)
    for p in red.players.values():
        p.spec = dataclasses.replace(p.spec, aggr=1)
    assert match.initiative_chance(blue) == match.config["fight"]["initiative_bounds"][1]

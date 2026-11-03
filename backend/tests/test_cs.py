"""CS: role rates, lane-phase multipliers (support for bot, jungle and focus for top/mid) and farm lost in fights."""
import dataclasses

import pytest

from app.game.config import LANES, simulation_config
from app.game.fights import run_fight
from app.game.lane_phase import lane_cs_multiplier, run_lane_phase
from app.game.range_waveclear import waveclear_farm_factor
from app.game.simulation_engine import simulate_match
from app.game.state import Match


def match_for(make_teams, champions, team_seed=1, cfg=None):
    blue, red = make_teams(team_seed)
    return Match(blue, red, champions, 1, cfg or simulation_config())


def no_waveclear():
    """Waveclear also changes lane CS; switched off so one other effect can be checked on its own."""
    return simulation_config({"waveclear": {"enabled": False}})


def set_scores(match, lane, blue, red):
    match.teams["BLUE"].players[lane].lane_score = blue
    match.teams["RED"].players[lane].lane_score = red


def bot_and_top(match):
    blue, red = match.sides
    cfg = match.config
    return lane_cs_multiplier(blue, red, "BOT", cfg), lane_cs_multiplier(blue, red, "TOP", cfg)


# ------------------------------------------------------------- role rates
def test_cs_rate_follows_role(make_teams, champions):
    match = match_for(make_teams, champions)
    factors = match.config["cs"]["role_factors"]
    assert factors["JUNGLE"] < factors["TOP"] == factors["MID"] == factors["BOT"]
    for team in match.sides:
        for lane, p in team.players.items():
            assert p.cs_rate == pytest.approx(p.spec.cs * factors[lane])


def test_lane_modifiers_only_cover_the_lane_phase(make_teams, champions):
    match = match_for(make_teams, champions)
    run_lane_phase(match)
    before = {id(p): p.cs for t in match.sides for p in t.players.values()}
    match.update_cs(25)
    for t in match.sides:
        for p in t.players.values():
            assert p.cs - before[id(p)] == pytest.approx(p.cs_rate * 10)


# ------------------------------------------------------------- lane-phase multipliers
def test_support_performance_drives_bot_cs(make_teams, champions):
    match = match_for(make_teams, champions, cfg=no_waveclear())
    scale = match.config["cs"]["support_scale"]
    set_scores(match, "SUPPORT", 100, 100)
    assert bot_and_top(match)[0] == pytest.approx(1.0)
    set_scores(match, "SUPPORT", 300, 100)
    assert bot_and_top(match)[0] == pytest.approx(1.0 + scale * 0.5)
    set_scores(match, "SUPPORT", 100, 300)
    assert bot_and_top(match)[0] == pytest.approx(1.0 - scale * 0.5)


def test_jungle_performance_drives_solo_lane_cs(make_teams, champions):
    match = match_for(make_teams, champions, cfg=no_waveclear())
    match.teams["BLUE"].setup = dataclasses.replace(match.teams["BLUE"].setup, focus=[])
    set_scores(match, "JUNGLE", 100, 100)
    assert bot_and_top(match)[1] == pytest.approx(1.0)
    set_scores(match, "JUNGLE", 300, 100)
    strong = bot_and_top(match)[1]
    set_scores(match, "JUNGLE", 100, 300)
    assert strong > 1.0 > bot_and_top(match)[1]
    set_scores(match, "SUPPORT", 100, 100)
    assert bot_and_top(match)[0] == pytest.approx(1.0)      # the jungle does not change bot CS


def test_lane_focus_raises_solo_lane_cs(make_teams, champions):
    match = match_for(make_teams, champions, cfg=no_waveclear())
    blue = match.teams["BLUE"]
    set_scores(match, "JUNGLE", 100, 100)
    bonus = match.config["cs"]["focus_bonus"] * blue.synergy_factor
    for focus, expected in (([], 1.0), (["top"], 1.0 + bonus), (["mid", "top"], 1.0 + bonus / 2)):
        blue.setup = dataclasses.replace(blue.setup, focus=focus)
        assert bot_and_top(match)[1] == pytest.approx(expected)


def test_lane_phase_pays_cs_with_the_multiplier(make_teams, champions):
    match = match_for(make_teams, champions)
    base_rates = {(p.team, p.lane): p.cs_rate for t in match.sides for p in t.players.values()}
    run_lane_phase(match)
    minutes = match.config["economy"]["lane_minutes"]
    for team in match.sides:
        for lane in LANES:
            p = team.players[lane]
            base = base_rates[(p.team, lane)]
            mult = lane_cs_multiplier(team, match.other(team), lane, match.config)
            assert p.cs == pytest.approx(base * minutes * mult)
            # from the end of the lane phase on, waveclear sets the farm speed
            assert p.cs_rate == pytest.approx(base * waveclear_farm_factor(p.champion, match.config))


# ------------------------------------------------------------- farm lost in fights
def fight_once(match, phase):
    """A 5v5 in `phase`; returns everyone's CS before it and the FIGHT event."""
    match.phase = phase
    before = {(p.team, p.lane): p.cs for t in match.sides for p in t.players.values()}
    blue, red = match.sides
    run_fight(match, blue, red, 5, 5, "TEAMFIGHT")
    return before, next(e for e in match.events if e.type == "FIGHT")


@pytest.mark.parametrize("phase", ["early", "mid"])
def test_deaths_and_ganks_cost_farm(make_teams, champions, phase):
    cfg = simulation_config()
    per_cs = cfg["economy"]["gold_per_cs"]
    for seed in range(8):
        match = match_for(make_teams, champions, seed, cfg)
        run_lane_phase(match)
        before, event = fight_once(match, phase)
        deaths = {}
        for k in event.payload["log"]:
            victim_side = "RED" if k["team"] == "BLUE" else "BLUE"
            victim = next(p for p in match.teams[victim_side].players.values() if p.champion.name == k["victim"])
            deaths[(victim_side, victim.lane)] = deaths.get((victim_side, victim.lane), 0) + 1
        for team in match.sides:
            for p in team.players.values():
                minutes = deaths.get((p.team, p.lane), 0) * cfg["cs"]["death_minutes"][phase]
                if phase == "early" and p.lane == "JUNGLE":
                    minutes += cfg["cs"]["gank_minutes"]
                lost = before[(p.team, p.lane)] - p.cs
                assert lost == pytest.approx(p.cs_rate * minutes)
                assert event.payload["cs_lost"].get(p.team, {}).get(p.lane, 0) == round(lost)
                if not minutes:
                    assert lost == 0


def test_lost_farm_leaves_other_gold_untouched(make_teams, champions):
    match = match_for(make_teams, champions)
    run_lane_phase(match)
    p = match.teams["BLUE"].players["MID"]
    gold_before = match._event_gold()
    cs, gold = p.cs, p.gold
    lost = match.lose_cs(p, 2.0)
    assert lost == pytest.approx(p.cs_rate * 2.0)
    assert p.cs == pytest.approx(cs - lost) and p.gold == pytest.approx(gold - lost * match.config["economy"]["gold_per_cs"])
    assert match._event_gold() == gold_before
    match.lose_cs(p, 10_000)
    assert p.cs == 0


def test_junglers_farm_less_than_solo_laners_over_many_games(make_teams, champions):
    totals = {lane: 0.0 for lane in LANES}
    for n in range(40):
        blue, red = make_teams(n)
        res = simulate_match(blue, red, champions, n)
        for p in res.players:
            totals[p["lane"]] += p["cs"] / (res.duration_seconds / 60)
    assert totals["JUNGLE"] < min(totals["TOP"], totals["MID"])
    assert totals["SUPPORT"] < totals["JUNGLE"]

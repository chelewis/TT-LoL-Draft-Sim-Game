"""Champion scaling: early game champions are stronger early, late game champions late."""
import dataclasses
import random

import pytest

from app.game.config import LANES, simulation_config, validate_overrides
from app.game.fights import _performance
from app.game.scaling import comp_scaling, scaling_multiplier
from app.game.simulation_engine import simulate_match
from app.game.state import Match

OFF = {"champion_scaling": {"enabled": False}}


def with_scaling(champions, champion_id, score):
    """A copy of the champion map with one champion's scaling score changed."""
    out = dict(champions)
    out[champion_id] = dataclasses.replace(champions[champion_id], scaling=score)
    return out


def all_neutral(champions):
    return {cid: dataclasses.replace(c, scaling=2) for cid, c in champions.items()}


# ------------------------------------------------------------- lookup
def test_multiplier_follows_the_curves(champions):
    cfg = simulation_config()
    curves = cfg["champion_scaling"]["curves"]
    champ = next(iter(champions.values()))
    for score in (1, 2, 3):
        c = dataclasses.replace(champ, scaling=score)
        for phase in ("lane", "early", "mid", "late", "overtime"):
            assert scaling_multiplier(c, phase, cfg) == curves[str(score)][phase]
    assert scaling_multiplier(dataclasses.replace(champ, scaling=1), "lane", cfg) > 1.0
    assert scaling_multiplier(dataclasses.replace(champ, scaling=3), "late", cfg) > 1.0


def test_multiplier_is_neutral_when_disabled_or_unknown(champions):
    champ = dataclasses.replace(next(iter(champions.values())), scaling=3)
    assert scaling_multiplier(champ, "late", simulation_config(OFF)) == 1.0
    assert scaling_multiplier(champ, "setup", simulation_config()) == 1.0


def test_comp_scaling_is_the_average(champions):
    champs = list(champions.values())[:5]
    scored = [dataclasses.replace(c, scaling=s) for c, s in zip(champs, (1, 1, 2, 3, 3))]
    assert comp_scaling(scored) == 2.0
    assert comp_scaling([dataclasses.replace(c, scaling=3) for c in champs]) == 3.0


# ------------------------------------------------------------- in the simulation
def test_early_champion_scores_higher_in_lane(champions, make_teams):
    blue, red = make_teams(3)
    top = blue.lineup["TOP"]
    early = simulate_match(blue, red, with_scaling(champions, top, 1), seed=11)
    late = simulate_match(blue, red, with_scaling(champions, top, 3), seed=11)
    assert early.lanes["TOP"]["blue_score"] > late.lanes["TOP"]["blue_score"]
    assert early.lanes["TOP"]["red_score"] == late.lanes["TOP"]["red_score"]   # same RNG draws for the enemy


def test_late_champion_performs_better_in_late_fights(champions, make_teams):
    blue, red = make_teams(4)
    top = blue.lineup["TOP"]

    def perf(score, phase):
        match = Match(blue, red, with_scaling(champions, top, score), 7, simulation_config())
        player = match.teams["BLUE"].players["TOP"]
        player.lane_score, player.gold = 500.0, 5000.0
        match.phase = phase
        match.rng = random.Random(99)          # same skill check roll for both
        return _performance(match, player)

    assert perf(3, "late") > perf(1, "late")
    assert perf(1, "early") > perf(3, "early")
    assert perf(1, "mid") == pytest.approx(perf(3, "mid"))


def test_disabled_scaling_matches_all_neutral_champions(champions, make_teams):
    blue, red = make_teams(5)
    off = simulate_match(blue, red, champions, seed=21, config=simulation_config(OFF))
    neutral = simulate_match(blue, red, all_neutral(champions), seed=21)
    assert off.to_dict()["teams"]["BLUE"]["kills"] == neutral.to_dict()["teams"]["BLUE"]["kills"]
    assert [e.to_dict() for e in off.events] == [e.to_dict() for e in neutral.events]
    assert off.winner == neutral.winner and off.duration_seconds == neutral.duration_seconds


def test_result_reports_comp_scaling(champions, make_teams):
    blue, red = make_teams(6)
    result = simulate_match(blue, red, champions, seed=31)
    for side, setup in (("BLUE", blue), ("RED", red)):
        expected = comp_scaling(champions[setup.lineup[l]] for l in LANES)
        assert result.teams[side]["comp"]["scaling"] == expected


def test_scaling_is_deterministic(champions, make_teams):
    blue, red = make_teams(7)
    a = simulate_match(blue, red, champions, seed=41)
    b = simulate_match(blue, red, champions, seed=41)
    assert a.to_dict() == b.to_dict()


# ------------------------------------------------------------- admin settings
def test_curves_are_editable_settings():
    nested = validate_overrides({"champion_scaling.enabled": False, "champion_scaling.curves.3.late": 1.2})
    cfg = simulation_config(nested)
    assert cfg["champion_scaling"]["enabled"] is False
    assert cfg["champion_scaling"]["curves"]["3"]["late"] == 1.2
    assert cfg["champion_scaling"]["curves"]["3"]["lane"] == simulation_config()["champion_scaling"]["curves"]["3"]["lane"]
    with pytest.raises(ValueError):
        validate_overrides({"champion_scaling.curves.1.lane": 3.0})
    with pytest.raises(ValueError):
        validate_overrides({"champion_scaling.curves.2.lane": 1.1})    # neutral curve stays at 1

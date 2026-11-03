"""Champion range and waveclear: lane trades, lane CS, farm speed, objective priority, fights and sieges."""
import dataclasses

import pytest

from app.game.config import LANES, simulation_config
from app.game.fights import _side_power
from app.game.lane_phase import lane_cs_multiplier, run_lane_phase
from app.game.range_waveclear import (matchup_callouts, range_fight_multiplier, range_lane_multiplier,
                                      siege_chance_delta, waveclear_farm_factor, waveclear_lane_cs,
                                      waveclear_priority)
from app.game.state import Match

OFF = {"range": {"enabled": False}, "waveclear": {"enabled": False}}


def match_for(make_teams, champions, cfg=None):
    blue, red = make_teams(1)
    return Match(blue, red, champions, 1, cfg or simulation_config())


def with_attrs(champion, attack_range=None, waveclear=None):
    return dataclasses.replace(champion, attack_range=attack_range or champion.attack_range,
                               waveclear=waveclear or champion.waveclear)


def set_team(match, side, attack_range=None, waveclear=None):
    for p in match.teams[side].players.values():
        p.champion = with_attrs(p.champion, attack_range, waveclear)


@pytest.fixture
def champ(champions):
    return next(iter(champions.values()))


# ------------------------------------------------------------- switched off / even
def test_everything_is_neutral_when_switched_off(champ):
    cfg = simulation_config(OFF)
    long_strong, melee_weak = with_attrs(champ, 3, 3), with_attrs(champ, 1, 1)
    assert waveclear_lane_cs(long_strong, melee_weak, cfg) == 1.0
    assert waveclear_farm_factor(long_strong, cfg) == 1.0
    assert waveclear_priority({l: long_strong for l in LANES}, cfg) == 1.0
    assert range_lane_multiplier([long_strong], [melee_weak], cfg) == 1.0
    assert range_fight_multiplier([long_strong] * 5, [melee_weak] * 5, 5, cfg) == 1.0
    assert siege_chance_delta([long_strong] * 5, [melee_weak] * 5, cfg) == 0.0


def test_even_comps_change_nothing(champ):
    cfg = simulation_config()
    c = with_attrs(champ, 3, 3)
    assert waveclear_lane_cs(c, c, cfg) == pytest.approx(1.0)
    assert range_lane_multiplier([c], [c], cfg) == pytest.approx(1.0)
    for size in (2, 5):
        assert range_fight_multiplier([c] * size, [c] * size, size, cfg) == pytest.approx(1.0)
    assert siege_chance_delta([c] * 5, [c] * 5, cfg) == pytest.approx(0.0)
    assert waveclear_farm_factor(with_attrs(champ, waveclear=2), cfg) == pytest.approx(1.0)
    assert waveclear_priority({l: with_attrs(champ, waveclear=2) for l in LANES}, cfg) == pytest.approx(1.0)


# ------------------------------------------------------------- waveclear
def test_waveclear_raises_lane_cs(make_teams, champions):
    match = match_for(make_teams, champions)
    blue, red = match.sides
    for lane in ("TOP", "MID", "BOT"):
        red.players[lane].champion = with_attrs(red.players[lane].champion, waveclear=2)
        values = []
        for wc in (1, 2, 3):
            blue.players[lane].champion = with_attrs(blue.players[lane].champion, waveclear=wc)
            values.append(lane_cs_multiplier(blue, red, lane, match.config))
        assert values[0] < values[1] < values[2]


def test_waveclear_sets_farm_speed_after_lane(champ):
    cfg = simulation_config()
    scale = cfg["waveclear"]["farm_scale"]
    assert waveclear_farm_factor(with_attrs(champ, waveclear=3), cfg) == pytest.approx(1.0 + scale)
    assert waveclear_farm_factor(with_attrs(champ, waveclear=1), cfg) == pytest.approx(1.0 - scale)


def test_waveclear_gives_objective_priority(make_teams, champions):
    match = match_for(make_teams, champions)
    blue = match.teams["BLUE"]
    control = {}
    for wc in (1, 3):
        set_team(match, "BLUE", waveclear=wc)
        control[wc] = match.objective_control(blue, roll=False)
    assert control[3] > control[1]
    scale = match.config["waveclear"]["priority_scale"]
    assert control[3] / control[1] == pytest.approx((1 + scale) / (1 - scale))


def test_mid_waveclear_matters_more_than_support(champ):
    cfg = simulation_config()
    base = {l: with_attrs(champ, waveclear=2) for l in LANES}
    strong_mid = {**base, "MID": with_attrs(champ, waveclear=3)}
    strong_support = {**base, "SUPPORT": with_attrs(champ, waveclear=3)}
    assert waveclear_priority(strong_mid, cfg) > waveclear_priority(strong_support, cfg) > 1.0


def test_waveclear_attacks_and_holds_sieges(champ):
    cfg = simulation_config({"range": {"enabled": False}})
    strong, weak = [with_attrs(champ, waveclear=3)] * 5, [with_attrs(champ, waveclear=1)] * 5
    assert siege_chance_delta(strong, weak, cfg) == pytest.approx(2 * cfg["waveclear"]["siege_scale"])
    assert siege_chance_delta(weak, strong, cfg) == pytest.approx(-2 * cfg["waveclear"]["siege_scale"])


# ------------------------------------------------------------- range
def test_range_wins_lane_trades(make_teams, champions):
    """Same seed, same rolls: only blue top's range changes, so only the range multiplier moves its score."""
    scores = {}
    for rng in (1, 3):
        match = match_for(make_teams, champions)
        blue, red = match.sides
        red.players["TOP"].champion = with_attrs(red.players["TOP"].champion, attack_range=1)
        blue.players["TOP"].champion = with_attrs(blue.players["TOP"].champion, attack_range=rng)
        run_lane_phase(match)
        scores[rng] = blue.players["TOP"].base_score
    scale = simulation_config()["range"]["lane_scale"]
    assert scores[3] / scores[1] == pytest.approx((1 + 2 * scale) / 1.0)


def test_bot_lane_compares_duo_range(make_teams, champions):
    match = match_for(make_teams, champions)
    blue, red = match.sides
    for side, rng in (("BLUE", 3), ("RED", 1)):
        for lane in ("BOT", "SUPPORT"):
            p = match.teams[side].players[lane]
            p.champion = with_attrs(p.champion, attack_range=rng)
    cfg = match.config
    mine = [blue.players[l].champion for l in ("BOT", "SUPPORT")]
    theirs = [red.players[l].champion for l in ("BOT", "SUPPORT")]
    assert range_lane_multiplier(mine, theirs, cfg) == pytest.approx(1 + 2 * cfg["range"]["lane_scale"])


def test_range_wins_teamfights_and_melee_wins_skirmishes(champ):
    cfg = simulation_config()
    ranged, melee = with_attrs(champ, attack_range=3), with_attrs(champ, attack_range=1)
    assert range_fight_multiplier([ranged] * 5, [melee] * 5, 5, cfg) > 1.0
    assert range_fight_multiplier([melee] * 5, [ranged] * 5, 5, cfg) < 1.0
    assert range_fight_multiplier([ranged] * 2, [melee] * 2, 2, cfg) < 1.0
    assert range_fight_multiplier([melee] * 2, [ranged] * 2, 2, cfg) > 1.0


def test_range_feeds_fight_power(make_teams, champions):
    match = match_for(make_teams, champions)
    match.phase = "late"
    blue, red = match.sides
    set_team(match, "RED", attack_range=1)
    perf = {l: 100.0 for l in LANES}
    power = {}
    for rng in (1, 3):
        set_team(match, "BLUE", attack_range=rng)
        power[rng], _ = _side_power(match, blue, blue.ordered_players(), perf, red.ordered_players())
    scale = match.config["range"]["teamfight_scale"]
    assert power[3] / power[1] == pytest.approx(1 + 2 * scale)


def test_range_pokes_sieges(champ):
    cfg = simulation_config({"waveclear": {"enabled": False}})
    ranged, melee = [with_attrs(champ, attack_range=3)] * 5, [with_attrs(champ, attack_range=1)] * 5
    assert siege_chance_delta(ranged, melee, cfg) == pytest.approx(2 * cfg["range"]["siege_scale"])


# ------------------------------------------------------------- matchup panel callouts
def lineup_champs(champions, blue_attrs, red_attrs):
    """Ten distinct champions with given (range, waveclear) per lane; returns (lineups, champions by id)."""
    pool = list(champions.values())
    by_id, lineups = {}, {"BLUE": {}, "RED": {}}
    for offset, (side, attrs) in enumerate((("BLUE", blue_attrs), ("RED", red_attrs))):
        for i, lane in enumerate(LANES):
            c = with_attrs(pool[offset * 5 + i], *attrs[lane])
            by_id[c.id] = c
            lineups[side][lane] = c.id
    return lineups, by_id


def test_callouts_for_clear_edges(champions):
    even = {l: (2, 2) for l in LANES}
    blue = {**even, "MID": (3, 3), "TOP": (3, 3)}
    red = {**even, "MID": (1, 2), "TOP": (1, 2)}
    lineups, by_id = lineup_champs(champions, blue, red)
    notes = matchup_callouts(lineups, by_id, simulation_config())
    text = " | ".join(notes)
    assert "Blue out-ranges Red (12 vs 8)" in text
    assert "Blue has stronger waveclear (12 vs 10)" in text
    assert any(n.startswith("Top: Blue's") for n in notes) and any(n.startswith("Mid: Blue's") for n in notes)
    assert not any(n.startswith("Bot lane") for n in notes)

    assert matchup_callouts(lineups, by_id, simulation_config(OFF)) == []
    only_waveclear = matchup_callouts(lineups, by_id, simulation_config({"range": {"enabled": False}}))
    assert only_waveclear == [n for n in notes if "waveclear" in n]


def test_no_callouts_for_even_comps(champions):
    even = {l: (2, 2) for l in LANES}
    lineups, by_id = lineup_champs(champions, even, even)
    assert matchup_callouts(lineups, by_id, simulation_config()) == []


def test_bot_duo_callout(champions):
    even = {l: (2, 2) for l in LANES}
    red = {**even, "BOT": (3, 2), "SUPPORT": (3, 2)}
    blue = {**even, "BOT": (2, 2), "SUPPORT": (1, 2)}
    lineups, by_id = lineup_champs(champions, blue, red)
    notes = matchup_callouts(lineups, by_id, simulation_config())
    assert "Bot lane: Red's duo out-ranges its opponents in lane." in notes

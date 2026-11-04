"""Lineup-stage previews: the matchup wheel per lane, graded expected lane scores and role status."""
import dataclasses

import pytest

from app.game import draft_ai
from app.game.config import simulation_config
from app.game.lane_preview import (expected_lane_score, grade_for, lane_grade, off_role_penalty, role_status,
                                   wheel_summary)
from app.game.matchup import lane_matchup
from app.game.models import Champion, MatchupTable, PlayerSpec

CFG = simulation_config()
EMPTY = MatchupTable()
# damage, sturdiness, cc, mobility, utility
OFFENCE = Champion(1, "Striker", "Assassin", 5, 2, "P", 5, 1, 1, 4, 1, roles=("MID", "TOP"))       # offence 9
DEFENCE = Champion(2, "Wall", "Tank", 5, 2, "P", 1, 5, 3, 1, 1, roles=("TOP",))                    # defence 8
CONTROL = Champion(3, "Mage", "Mage", 5, 2, "M", 2, 1, 3, 1, 5, roles=("SUPPORT", "MID"))          # control 8
NO_ROLES = Champion(4, "Unknown", "Fighter", 5, 2, "P", 3, 3, 2, 2, 1)


def player(pool=(10, 11, 12, 13, 14), **stats):
    base = {"aggr": 6, "aware": 6, "pos": 6, "dmg": 6}
    base.update(stats)
    return PlayerSpec(1, "P", "MID", 20, base["aggr"], base["aware"], base["pos"], base["dmg"], 5, tuple(pool))


def score(p, champion, lane="MID", opponents=None, **kw):
    kw = {"partner": None, "my_draft": 5, "enemy_draft": 5, "table": EMPTY, "config": CFG, **kw}
    return expected_lane_score(p, champion, lane, opponents=opponents or {}, **kw)


def test_role_status_covers_every_case():
    assert role_status(OFFENCE, "MID", player(), CFG) == "MAIN"
    assert role_status(OFFENCE, "TOP", player(), CFG) == "SECONDARY"
    assert role_status(OFFENCE, "BOT", player(), CFG) == "OFF_ROLE"
    assert role_status(OFFENCE, "BOT", player(pool=(1, 10, 11)), CFG) == "OFF_ROLE_EXEMPT"
    assert role_status(OFFENCE, "BOT", None, CFG) == "OFF_ROLE"          # pool hidden: exemption unknown
    assert role_status(NO_ROLES, "BOT", player(), CFG) is None


def test_off_role_penalty_matches_the_simulation_rule():
    assert off_role_penalty(OFFENCE, "BOT", player(), CFG) == CFG["off_role"]["lane_penalty"]
    assert off_role_penalty(OFFENCE, "BOT", player(pool=(1,)), CFG) == 0.0
    assert off_role_penalty(OFFENCE, "TOP", player(), CFG) == 0.0


def test_wheel_summary_matches_lane_matchup():
    for blue, red in ((OFFENCE, DEFENCE), (DEFENCE, OFFENCE), (OFFENCE, OFFENCE), (CONTROL, OFFENCE)):
        _, _, label = lane_matchup(blue, red, CFG)
        wheel = wheel_summary(blue, red, 5, 5, CFG)
        assert wheel["blue"]["strength"] == blue.strength and wheel["red"]["weakness"] == red.weakness
        if label is None:
            assert wheel["winner"] is None and wheel["blue_multiplier"] == wheel["red_multiplier"] == 1.0
        else:
            assert wheel["winner"] == ("BLUE" if label.startswith("A") else "RED")
            assert wheel["kind"] == label.split("_")[1]
            winner_mult = wheel["blue_multiplier"] if wheel["winner"] == "BLUE" else wheel["red_multiplier"]
            assert winner_mult > 1.0


def test_without_an_opponent_the_score_is_the_cpu_lane_fit():
    p = player()
    value, factors = score(p, OFFENCE)
    mid = sum(CFG["lane"]["roll_range"]) / 2
    expected = mid * CFG["lane"]["scale"] * draft_ai.lane_fit(p, OFFENCE, CFG, "MID") * factors["scaling"]
    assert value == pytest.approx(expected)


def test_winning_the_wheel_raises_the_score():
    p = player()
    neutral, _ = score(p, OFFENCE, opponents={"MID": OFFENCE})
    winning, factors = score(p, OFFENCE, opponents={"MID": DEFENCE})
    losing, _ = score(p, DEFENCE, opponents={"MID": OFFENCE})
    alone, _ = score(p, DEFENCE)
    assert factors["wheel"] > 1.0 and winning > neutral
    assert losing < alone


def test_lane_counter_win_rate_moves_the_score():
    p = player()
    table = MatchupTable(enemy={(1, 2): 58.0})                # Striker wins 58% against Wall
    up, f_up = score(p, OFFENCE, "TOP", opponents={"TOP": DEFENCE}, table=table)
    flat, _ = score(p, OFFENCE, "TOP", opponents={"TOP": DEFENCE})
    assert f_up["counter"] > 1.0 and up > flat


def test_off_role_grades_lower_than_on_role():
    p = player()
    on, _ = score(p, OFFENCE, "MID")
    off, factors = score(p, OFFENCE, "BOT")
    assert factors["off_role"] == 1.0 - CFG["off_role"]["lane_penalty"]
    assert off < on


def test_grade_ranks_against_the_candidates():
    p = player(pool=(3, 10, 11), dmg=9, pos=9)
    pool = [OFFENCE, DEFENCE, CONTROL, NO_ROLES] + [
        dataclasses.replace(DEFENCE, id=100 + i, name=f"Filler{i}", sturdiness=1, damage=1) for i in range(16)]
    kw = {"opponents": {}, "partner": None, "my_draft": 5, "enemy_draft": 5, "table": EMPTY, "config": CFG}
    grades = {c.id: lane_grade(p, c, "MID", pool, **kw) for c in pool[:4]}
    scores = {cid: g["expected"] for cid, g in grades.items()}
    best = max(scores, key=scores.get)
    assert grades[best]["percentile"] == max(g["percentile"] for g in grades.values())
    assert grades[best]["grade"] in ("S", "A")
    filler = lane_grade(p, pool[5], "MID", pool, **kw)
    assert filler["percentile"] < grades[best]["percentile"]


@pytest.mark.parametrize("percentile,grade", [(1.0, "S"), (0.95, "S"), (0.9, "A"), (0.7, "B"), (0.5, "C"),
                                              (0.2, "D"), (0.1, "F"), (0.0, "F")])
def test_grade_thresholds(percentile, grade):
    assert grade_for(percentile, CFG) == grade

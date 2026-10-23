"""Damage dealt and taken: reporting figures built from each fight, with no effect on the simulation."""
import dataclasses

from app.game.config import LANES, simulation_config
from app.game.fights import _record_damage
from app.game.simulation_engine import simulate_match
from app.game.state import Match


def run(make_teams, champions, n, cfg=None):
    blue, red = make_teams(n)
    return simulate_match(blue, red, champions, n, cfg)


def fights(result):
    return [e for e in result.events if e.type == "FIGHT"]


def test_every_fight_deals_what_it_takes(make_teams, champions):
    for n in range(10):
        for e in fights(run(make_teams, champions, n)):
            damage = e.payload["damage"]
            dealt = sum(v[0] for side in damage.values() for v in side.values())
            taken = sum(v[1] for side in damage.values() for v in side.values())
            assert abs(dealt - taken) <= 10            # per-fighter rounding only
            fighters = {e.payload["attacker"]: e.payload["attackers"], e.payload["defender"]: e.payload["defenders"]}
            assert {s: sorted(v) for s, v in damage.items()} == {s: sorted(v) for s, v in fighters.items()}


def test_totals_are_the_sum_of_the_fights(make_teams, champions):
    for n in range(10):
        res = run(make_teams, champions, n)
        totals = {(p["team"], p["lane"]): [0, 0] for p in res.players}
        for e in fights(res):
            for side, lanes in e.payload["damage"].items():
                for lane, (dealt, taken) in lanes.items():
                    totals[(side, lane)][0] += dealt
                    totals[(side, lane)][1] += taken
        for p in res.players:
            assert [p["damage_dealt"], p["damage_taken"]] == totals[(p["team"], p["lane"])]
            if not any(p["lane"] in lanes for e in fights(res) for side, lanes in e.payload["damage"].items()
                       if side == p["team"]):
                assert p["damage_dealt"] == p["damage_taken"] == 0


def test_damage_report_does_not_change_the_game(make_teams, champions):
    silent = simulation_config({"fight": {"damage_report_scale": 0.0}})

    def strip(result):
        out = result.to_dict()
        for p in out["players"]:
            p.pop("damage_dealt"), p.pop("damage_taken")
        for e in out["events"]:
            e["payload"].pop("damage", None)
        return out

    for n in range(10):
        assert strip(run(make_teams, champions, n)) == strip(run(make_teams, champions, n, silent))


def test_hitters_deal_more_and_sturdy_fighters_take_more(make_teams, champions):
    blue, red = make_teams(1)
    match = Match(blue, red, champions, 1, simulation_config())
    team, enemy = match.sides
    top, mid = team.players["TOP"], team.players["MID"]
    top.champion = dataclasses.replace(top.champion, damage=3, sturdiness=1)
    mid.champion = dataclasses.replace(mid.champion, damage=1, sturdiness=3)
    foe = enemy.players["TOP"]
    offence = {"TOP": 300.0, "MID": 100.0}
    out = _record_damage(match, [(team, [top, mid], offence), (enemy, [foe], {"TOP": 400.0})], [])
    assert out["BLUE"]["TOP"][0] > out["BLUE"]["MID"][0]           # dealt
    assert out["BLUE"]["MID"][1] > out["BLUE"]["TOP"][1]           # taken
    assert (top.damage_dealt, mid.damage_taken) == (out["BLUE"]["TOP"][0], out["BLUE"]["MID"][1])

    # dying in the fight means taking a bigger share
    before = out["BLUE"]["TOP"][1]
    out = _record_damage(match, [(team, [top, mid], offence), (enemy, [foe], {"TOP": 400.0})], [(foe, top)])
    assert out["BLUE"]["TOP"][1] > before


def test_result_lists_damage_for_every_player(make_teams, champions):
    res = run(make_teams, champions, 3)
    assert all(isinstance(p["damage_dealt"], int) and isinstance(p["damage_taken"], int) for p in res.players)
    assert len({(p["team"], p["lane"]) for p in res.players}) == 2 * len(LANES)

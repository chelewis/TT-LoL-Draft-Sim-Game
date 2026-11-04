"""Off-role champions: a champion played outside its usual roles (Champions.csv Roles) loses lane score, unless
it is one of the player's top pool picks."""
import dataclasses

from app.data.loader import seed_team_setup
from app.game.comfort import off_role, off_role_multiplier
from app.game.config import LANES, simulation_config
from app.game.models import Champion, PlayerSpec
from app.game.simulation_engine import simulate_match

CFG = simulation_config()
PENALTY = CFG["off_role"]["lane_penalty"]
JUNGLER = Champion(500, "Junglechamp", "Fighter", 5, 2, "P", 3, 2, 2, 2, 1, roles=("JUNGLE", "TOP"))


def player(pool=(1, 2, 3, 4, 5)):
    return PlayerSpec(1, "P", "BOT", 20, 5, 5, 5, 5, 5, tuple(pool))


def test_on_role_champions_are_not_penalised():
    assert off_role_multiplier(JUNGLER, "JUNGLE", player(), CFG) == 1.0
    assert off_role_multiplier(JUNGLER, "TOP", player(), CFG) == 1.0          # its second role counts too


def test_off_role_champions_lose_lane_score():
    assert off_role(JUNGLER, "BOT", player(), CFG)
    assert off_role_multiplier(JUNGLER, "BOT", player(), CFG) == 1.0 - PENALTY


def test_a_top_3_pool_pick_is_exempt_but_slots_4_and_5_are_not():
    for slot in range(3):
        pool = [1, 2, 3, 4, 5]
        pool[slot] = JUNGLER.id
        assert off_role_multiplier(JUNGLER, "BOT", player(pool), CFG) == 1.0
    for slot in (3, 4):
        pool = [1, 2, 3, 4, 5]
        pool[slot] = JUNGLER.id
        assert off_role_multiplier(JUNGLER, "BOT", player(pool), CFG) == 1.0 - PENALTY


def test_no_role_data_and_the_setting_off_mean_no_penalty():
    blank = dataclasses.replace(JUNGLER, roles=())
    assert off_role_multiplier(blank, "BOT", player(), CFG) == 1.0
    off = simulation_config({"off_role": {"enabled": False}})
    assert off_role_multiplier(JUNGLER, "BOT", player(), off) == 1.0
    assert not off_role(JUNGLER, "BOT", player(), off)


def _mid_result(seed, champions, roles):
    """Simulate with the blue mid laner on a champion whose roles are `roles` (same rolls every time)."""
    blue = seed_team_setup(seed, 1, {})
    pools = {cid for p in blue.roster.values() for cid in p.pool}
    picks = [c.id for c in champions.values() if c.id not in pools][:10]
    mid = champions[picks[LANES.index("MID")]]
    pool = {**champions, mid.id: dataclasses.replace(mid, roles=roles)}
    blue = dataclasses.replace(blue, lineup=dict(zip(LANES, picks[:5])))
    red = dataclasses.replace(seed_team_setup(seed, 2, {}), lineup=dict(zip(LANES, picks[5:])))
    result = simulate_match(blue, red, pool, 11, CFG)
    return next(p for p in result.players if p["team"] == "BLUE" and p["lane"] == "MID")


def test_an_off_role_champion_scores_less_in_a_match(seed, champions):
    on = _mid_result(seed, champions, ("MID",))
    off = _mid_result(seed, champions, ("BOT", "SUPPORT"))
    assert on["off_role"] is False and off["off_role"] is True
    assert off["lane_score"] < on["lane_score"]

"""Champion win rate matrices and damage balance in the simulation."""
import pytest

from app.data.loader import seed_team_setup
from app.game.config import LANES, simulation_config, validate_overrides, flatten_overrides
from app.game.models import MatchupTable
from app.game.simulation_engine import simulate_match
from app.game.state import Match
from app.game.win_rates import ally_delta, counter_delta, multiplier

OFF = {"win_rates": {"enabled": False}, "damage_balance": {"enabled": False}}


# ------------------------------------------------------------- matchup table + deltas
def test_table_lookups_either_way_round():
    table = MatchupTable(ally={(1, 2): 54.0}, enemy={(1, 2): 60.0})
    assert table.ally_rate(1, 2) == table.ally_rate(2, 1) == 54.0
    assert table.enemy_rate(1, 2) == 60.0
    assert table.enemy_rate(2, 1) == 40.0                    # 2 beats 1 forty percent of the time
    assert table.ally_rate(1, 3) is None and table.enemy_rate(3, 1) is None


def test_deltas_skip_missing_pairs_and_are_capped():
    cfg = simulation_config()
    table = MatchupTable(ally={(1, 2): 54.0, (1, 3): 50.0}, enemy={(1, 9): 90.0})
    assert ally_delta([1, 2, 3], table, cfg) == pytest.approx(2.0)    # (2,3) has no data: mean of 54 and 50
    assert ally_delta([4, 5], table, cfg) == 0.0                       # nothing known: no effect
    assert counter_delta([1], [9], table, cfg) == cfg["win_rates"]["max_points"]
    assert counter_delta([9], [1], table, cfg) == -cfg["win_rates"]["max_points"]
    assert multiplier(5.0, 0.02, cfg) == pytest.approx(1.10)
    assert multiplier(5.0, 0.02, simulation_config(OFF)) == 1.0


# ------------------------------------------------------------- damage balance
def team_with(seed, champions, damage_types):
    """A Match whose blue team's champions have the given damage types (red is irrelevant)."""
    by_type = {t: [c.id for c in champions.values() if c.damage_type == t and c.damage == 3] for t in ("P", "M", "PM")}
    used = {t: iter(ids) for t, ids in by_type.items()}
    lineup = {lane: next(used[t]) for lane, t in zip(LANES, damage_types)}
    other = [c for c in champions if c not in lineup.values()][:5]
    blue = seed_team_setup(seed, 1, lineup)
    red = seed_team_setup(seed, 2, dict(zip(LANES, other)))
    return Match(blue, red, champions, 1, simulation_config()).teams["BLUE"]


def test_damage_penalty_grows_with_one_sided_damage(seed, champions):
    cfg = simulation_config()
    db = cfg["damage_balance"]
    assert team_with(seed, champions, "PPMMM").damage_balance_penalty(cfg) == 0.0          # 60% magic: free
    assert team_with(seed, champions, "PPPPP").damage_balance_penalty(cfg) == pytest.approx(db["max_penalty"])
    four_one = team_with(seed, champions, "PPPPM").damage_balance_penalty(cfg)              # 80% physical
    assert four_one == pytest.approx(db["max_penalty"] * (0.8 - db["threshold"]) / (1 - db["threshold"]))
    assert team_with(seed, champions, "PPPPP").damage_balance_penalty(simulation_config(OFF)) == 0.0


# ------------------------------------------------------------- in the simulation
def lane_scores(result):
    return {lane: (v["blue_score"], v["red_score"]) for lane, v in result.lanes.items()}


def test_counter_win_rate_raises_the_lane_score(make_teams, champions):
    blue, red = make_teams(3)
    b, r = blue.lineup["MID"], red.lineup["MID"]
    plain = simulate_match(blue, red, champions, 11)
    countered = simulate_match(blue, red, champions, 11,
                               matchups=MatchupTable(enemy={(min(b, r), max(b, r)): 60.0 if b < r else 40.0}))
    assert countered.lanes["MID"]["counter_rate"] == 60.0
    assert countered.lanes["MID"]["blue_score"] > plain.lanes["MID"]["blue_score"]
    assert countered.lanes["MID"]["red_score"] < plain.lanes["MID"]["red_score"]


def test_bot_lane_duo_synergy_raises_both_bot_lane_scores(make_teams, champions):
    blue, red = make_teams(4)
    bot, sup = blue.lineup["BOT"], blue.lineup["SUPPORT"]
    plain = simulate_match(blue, red, champions, 12)
    duo = simulate_match(blue, red, champions, 12, matchups=MatchupTable(ally={(min(bot, sup), max(bot, sup)): 58.0}))
    # lane scores include assists from teammates, so compare BOT and SUPPORT, which get the duo bonus directly
    assert duo.lanes["BOT"]["blue_score"] > plain.lanes["BOT"]["blue_score"]
    assert duo.lanes["SUPPORT"]["blue_score"] > plain.lanes["SUPPORT"]["blue_score"]
    assert duo.lanes["BOT"]["red_score"] == plain.lanes["BOT"]["red_score"]
    assert duo.teams["BLUE"]["comp"]["ally_synergy"] == 8.0        # the only pair with data: 58 - 50


def test_disabled_or_zero_scales_match_no_matrices(make_teams, champions):
    blue, red = make_teams(5)
    ids = list(blue.lineup.values()) + list(red.lineup.values())
    table = MatchupTable(ally={(min(a, b), max(a, b)): 56.0 for a in ids for b in ids if a < b},
                         enemy={(min(a, b), max(a, b)): 62.0 for a in ids for b in ids if a < b})
    no_dmg = {"damage_balance": {"enabled": False}}
    baseline = simulate_match(blue, red, champions, 21, simulation_config(no_dmg)).to_dict()
    disabled = simulate_match(blue, red, champions, 21, simulation_config(OFF), table).to_dict()
    zero = simulate_match(blue, red, champions, 21, simulation_config({**no_dmg, "win_rates": {
        "lane_counter_scale": 0, "lane_duo_scale": 0, "fight_synergy_scale": 0, "fight_counter_scale": 0}}), table)
    def strip(d):
        """Everything but the reported win rates (comp synergy, lane counter rates), which are there either way."""
        out = {k: v for k, v in d.items() if k not in ("teams", "lanes")}
        out["events"] = [{**e, "payload": {k: v for k, v in e["payload"].items() if k != "counter_rate"}}
                         for e in d["events"]]
        return out
    assert strip(disabled) == strip(baseline)
    assert strip(zero.to_dict()) == strip(baseline)
    with_table = simulate_match(blue, red, champions, 21, simulation_config(no_dmg), table).to_dict()
    assert with_table != baseline


def test_same_seed_and_table_reproduce(make_teams, champions):
    blue, red = make_teams(6)
    ids = sorted(list(blue.lineup.values()) + list(red.lineup.values()))
    table = MatchupTable(ally={(ids[0], ids[1]): 55.0}, enemy={(ids[0], ids[2]): 57.0, (ids[3], ids[9]): 44.0})
    a =simulate_match(blue, red, champions, 33, matchups=table).to_dict()
    b = simulate_match(blue, red, champions, 33, matchups=table).to_dict()
    assert a == b


# ------------------------------------------------------------- editable settings
def test_overrides_are_validated():
    nested = validate_overrides({"win_rates.lane_counter_scale": 0.05, "damage_balance.enabled": False})
    assert nested == {"win_rates": {"lane_counter_scale": 0.05}, "damage_balance": {"enabled": False}}
    assert flatten_overrides(nested) == {"win_rates.lane_counter_scale": 0.05, "damage_balance.enabled": False}
    assert simulation_config(nested)["win_rates"]["lane_counter_scale"] == 0.05
    with pytest.raises(ValueError):
        validate_overrides({"economy.kill": 500})                         # not editable
    with pytest.raises(ValueError):
        validate_overrides({"win_rates.lane_counter_scale": 5})           # out of range
    with pytest.raises(ValueError):
        validate_overrides({"win_rates.enabled": 1})                      # not a bool
    with pytest.raises(ValueError):
        validate_overrides({"damage_balance.threshold": True})            # not a number


# ------------------------------------------------------------- estimated against-team seed file
def test_estimated_counters_mirror_and_cover_every_pair(seed, tmp_path):
    from app.data.loader import _norm
    from app.data.matchup_seed import read_matchup_csv
    from scripts.estimate_counters import expected_versus, write_estimates

    assert expected_versus(52.0, 48.0) == 52.0
    assert expected_versus(48.0, 52.0) == 48.0
    n = len(seed.champions)
    assert write_estimates(tmp_path / "champion_counter.csv") == n * (n - 1) // 2
    cells = read_matchup_csv("enemy", {_norm(c.name): c.id for c in seed.champions}, tmp_path)
    assert len(cells) == n * (n - 1) // 2
    by_id = {c.id: c for c in seed.champions}
    for (a, b), cell in list(cells.items())[:50]:          # stored from the lower id's side
        assert cell["win_rate"] == round(expected_versus(by_id[a].win_rate, by_id[b].win_rate), 1)
        assert cell["games"] == 0

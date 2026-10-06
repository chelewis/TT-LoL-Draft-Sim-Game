import pytest

from app.integrations.riot import stat_mapper
from app.integrations.riot.errors import NotEnoughData
from tests.riot_fixtures import STRONG, WEAK, make_match

BUDGET = 32


def games(n, **kw):
    return [make_match("me", **kw) for _ in range(n)]


def test_scale_is_clamped_and_invertible():
    assert stat_mapper.scale(5, 0, 10) == pytest.approx(5.5)
    assert stat_mapper.scale(-3, 0, 10) == 1.0
    assert stat_mapper.scale(99, 0, 10) == 10.0
    assert stat_mapper.scale(10, 0, 10, lower_is_better=True) == 1.0


def test_strong_player_outscores_weak_player_in_every_stat():
    strong = stat_mapper.analyse(games(12, mine=STRONG), "me", 100)
    weak = stat_mapper.analyse(games(12, mine=WEAK), "me", 100)
    for stat in stat_mapper.STATS:
        assert strong.raw_stats[stat] > weak.raw_stats[stat], stat
    assert all(1 <= v <= 10 for v in strong.stats.values())


def test_stats_fit_the_soft_ceiling_by_default():
    a = stat_mapper.analyse(games(12, mine=STRONG), "me", BUDGET)
    assert sum(a.stats.values()) <= BUDGET and a.fitted_to_budget is True
    assert all(v >= 1 for v in a.stats.values())
    b = stat_mapper.analyse(games(12, mine=WEAK), "me", BUDGET)
    assert b.fitted_to_budget is False and sum(b.stats.values()) <= BUDGET


def test_fit_to_budget_trims_to_exactly_within_budget():
    for stats in ({"a": 10, "b": 10, "c": 10, "d": 10, "e": 10}, {"a": 9, "b": 8, "c": 7, "d": 10, "e": 6}):
        fitted, changed = stat_mapper.fit_to_budget({k: float(v) for k, v in stats.items()}, 32)
        assert changed and sum(fitted.values()) <= 32 and min(fitted.values()) >= 1


def test_raise_to_floor_scales_up_to_exactly_the_floor():
    stats = {"aggr": 2, "aware": 3, "pos": 1, "dmg": 4, "cs": 5}             # 15
    assert stat_mapper.raise_to_floor(stats, 15) == (stats, False)
    assert stat_mapper.raise_to_floor(stats, 0) == (stats, False)
    for floor in (16, 28, 36, 40, 50):
        raised, changed = stat_mapper.raise_to_floor(stats, floor)
        assert changed and sum(raised.values()) == floor and max(raised.values()) <= 10
        assert all(raised[k] >= stats[k] for k in stats)                     # nothing goes down
        assert sorted(raised, key=raised.get) == sorted(stats, key=stats.get) or floor == 50   # order of strengths kept
    # a stat already near 10 cannot absorb its share, so the others take it
    lopsided, _ = stat_mapper.raise_to_floor({"aggr": 9, "aware": 1, "pos": 1, "dmg": 1, "cs": 1}, 28)
    assert sum(lopsided.values()) == 28 and lopsided["aggr"] == 10


def test_floor_applies_to_weak_games_and_not_to_strong_ones():
    weak = stat_mapper.analyse(games(12, mine=WEAK), "me", 40, floor=36)
    assert weak.raised_to_floor is True and sum(weak.stats.values()) == 36 and weak.floor == 36
    assert weak.total_before_fit < 36                                        # what the games alone were worth
    strong = stat_mapper.analyse(games(12, mine=STRONG), "me", 40, floor=36)
    assert strong.raised_to_floor is False and strong.fitted_to_budget is True
    assert stat_mapper.analyse(games(12, mine=WEAK), "me", 40).raised_to_floor is False      # no floor by default


def test_role_is_the_most_played_lane_and_can_be_overridden():
    matches = games(8, lane="JUNGLE") + games(4, lane="MIDDLE")
    assert stat_mapper.analyse(matches, "me", BUDGET).lane == "JUNGLE"
    forced = stat_mapper.analyse(matches, "me", BUDGET, role="MID")
    assert forced.lane == "MID"
    assert stat_mapper.analyse(games(12, lane="UTILITY"), "me", BUDGET).lane == "SUPPORT"


def test_stats_are_relative_to_the_role():
    # 1.0 vision per minute is a lot for a mid laner but very low for a support
    mine = dict(vision=30)
    mid = stat_mapper.analyse(games(12, lane="MIDDLE", mine=mine), "me", 100)
    sup = stat_mapper.analyse(games(12, lane="UTILITY", mine=mine), "me", 100)
    assert mid.raw_stats["aware"] > sup.raw_stats["aware"]


def test_remakes_and_foreign_games_are_ignored():
    matches = games(10) + [make_match("me", minutes=3)] + [make_match("someone-else")]
    a = stat_mapper.analyse(matches, "me", BUDGET)
    assert a.games == 10


def test_not_enough_games_is_a_clear_error():
    with pytest.raises(NotEnoughData, match="at least 10"):
        stat_mapper.analyse(games(6), "me", BUDGET)


def test_old_matches_reporting_milliseconds_still_work():
    match = make_match("me")
    match["info"]["gameDuration"] *= 1000
    assert stat_mapper.sample_game(match, "me").metrics["cs_per_min"] == pytest.approx(200 / 30)


def test_challenges_block_is_used_when_present():
    match = make_match("me")
    match["info"]["participants"][0]["challenges"] = {"killParticipation": 0.9, "damagePerMinute": 1234.0}
    metrics = stat_mapper.sample_game(match, "me").metrics
    assert metrics["kill_participation"] == 0.9 and metrics["damage_per_min"] == 1234.0


def test_pool_prefers_games_played_then_mastery_and_skips_unknown_champions():
    # championId 103 played most, then 266; 9999 is not in our game; mastery adds 62 and 266
    matches = [make_match("me", champion=103) for _ in range(6)] + [make_match("me", champion=266) for _ in range(3)] \
        + [make_match("me", champion=9999) for _ in range(3)]
    a = stat_mapper.analyse(matches, "me", BUDGET)
    mapping = {103: 1, 266: 2, 62: 3}
    pool, unmapped = stat_mapper.build_pool(
        a, [{"championId": 62, "championPoints": 5}, {"championId": 266, "championPoints": 9}], mapping.get)
    assert pool == [1, 2, 3]               # no duplicates, ordered by games then mastery
    assert unmapped == [9999]


def entry(queue_type, tier, division="II", lp=45, wins=60, losses=40):
    return {"queueType": queue_type, "tier": tier, "rank": division, "leaguePoints": lp, "wins": wins, "losses": losses}


def test_rank_comes_from_the_queue_the_stats_came_from():
    entries = [entry("RANKED_SOLO_5x5", "EMERALD"), entry("RANKED_FLEX_SR", "GOLD", "IV")]
    solo = stat_mapper.pick_rank(entries, "SOLO")
    assert solo == {"queue": "SOLO", "tier": "EMERALD", "division": "II", "lp": 45, "wins": 60, "losses": 40}
    assert stat_mapper.pick_rank(entries, "FLEX")["tier"] == "GOLD"
    assert stat_mapper.pick_rank(entries, "NORMAL")["queue"] == "SOLO"          # normals borrow solo rank first
    assert stat_mapper.pick_rank(entries[1:], "NORMAL")["queue"] == "FLEX"      # then flex
    assert stat_mapper.pick_rank(entries[1:], "SOLO") is None                   # a flex rank never stands in for solo
    assert stat_mapper.pick_rank([], "SOLO") is None
    assert stat_mapper.pick_rank([entry("RANKED_SOLO_5x5", "WOOD")], "SOLO") is None      # unknown tier


def test_apex_tiers_have_no_division():
    assert stat_mapper.pick_rank([entry("RANKED_SOLO_5x5", "CHALLENGER", "I", lp=900)], "SOLO")["division"] is None


def test_breakdown_explains_every_stat_and_adds_up():
    a = stat_mapper.analyse(games(12, mine=STRONG), "me", BUDGET)
    assert set(a.breakdown) == set(stat_mapper.STATS)
    for stat, rows in a.breakdown.items():
        assert rows, stat
        # the raw stat is exactly the average of its metric scores
        assert sum(r["score"] for r in rows) / len(rows) == pytest.approx(a.raw_stats[stat], abs=0.01)
        for r in rows:
            assert r["label"] and r["how"] and r["low"] < r["high"] and 1 <= r["score"] <= 10
            # the displayed score follows the displayed formula
            expected = stat_mapper.scale(r["value"], r["low"], r["high"], r["lower_is_better"])
            assert r["score"] == pytest.approx(expected, abs=0.01)
    assert any(r["lower_is_better"] for r in a.breakdown["pos"])
    assert a.budget == BUDGET and a.total_before_fit >= sum(a.stats.values())

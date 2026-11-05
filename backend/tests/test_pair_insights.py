"""Champion pair notes for Meta → Champion Pairs (game/pair_insights.py)."""
import copy
from dataclasses import replace

from app.game import pair_insights
from app.game.config import simulation_config
from app.game.models import Champion, MatchupTable
from app.game.win_rates import multiplier

CFG = simulation_config()


def champ(cid, roles=("TOP",), **kw):
    """An unremarkable champion: average control, short range, neutral scaling, physical damage."""
    base = dict(id=cid, name=f"C{cid}", champ_class="Fighter", style=1, difficulty=1, damage_type="P", damage=5,
                sturdiness=5, cc=2, mobility=2, utility=1, roles=tuple(roles))
    return Champion(**{**base, **kw})


def titles(notes):
    return [n["title"] for n in notes]


def test_same_lane_rivals_get_the_matchup_wheel():
    offence = champ(1, damage=8, mobility=6, sturdiness=3, cc=2, utility=1)       # Offence, weak to Control
    control = champ(2, damage=2, mobility=2, sturdiness=3, cc=4, utility=8)       # Control beats Offence
    out = pair_insights.analyse_pair(offence, control, MatchupTable(), CFG)
    assert out["against"]["lane"] == "TOP" and out["against"]["head_to_head"]
    wheel = next(n for n in out["against"]["notes"] if "wheel" in n["title"])
    assert wheel["kind"] == "b" and "x1.50" in wheel["detail"]                     # a strong win

    # in different lanes they never face each other in lane, so no wheel
    apart = pair_insights.analyse_pair(offence, replace(control, roles=("MID",)), MatchupTable(), CFG)
    assert apart["against"]["lane"] is None
    assert not any("wheel" in t for t in titles(apart["against"]["notes"]))


def test_bot_and_support_are_a_duo_on_one_team_and_meet_across_the_bot_lane():
    bot, sup = champ(1, roles=("BOT",)), champ(2, roles=("SUPPORT",), damage_type="M")
    table = MatchupTable(ally={(1, 2): 56.0}, enemy={(1, 2): 60.0})
    out = pair_insights.analyse_pair(bot, sup, table, CFG)

    synergy = next(n for n in out["same_team"]["notes"] if n["title"] == "Strong synergy")
    fight = multiplier(6.0, CFG["win_rates"]["fight_synergy_scale"], CFG)
    duo = multiplier(6.0, CFG["win_rates"]["lane_duo_scale"], CFG)
    assert f"x{fight:.2f} fight power" in synergy["detail"] and f"x{duo:.2f} lane score" in synergy["detail"]

    assert out["against"]["lane"] == "BOT" and not out["against"]["head_to_head"]
    counter = next(n for n in out["against"]["notes"] if "counters" in n["title"])
    assert counter["kind"] == "a" and "lane score in Bot lane" in counter["detail"]
    assert not any("wheel" in t for t in titles(out["against"]["notes"]))


def test_one_sided_damage_is_a_weakness_and_mixed_damage_a_strength():
    same = pair_insights.same_team(champ(1, roles=("TOP",)), champ(2, roles=("MID",)), MatchupTable(), CFG)
    assert "Both physical damage" in titles(same)
    mixed = pair_insights.same_team(champ(1, roles=("TOP",)), champ(2, roles=("MID",), damage_type="M"),
                                    MatchupTable(), CFG)
    assert "Mixed damage" in titles(mixed)


def test_champions_that_only_play_one_lane_clash_on_one_team():
    notes = pair_insights.same_team(champ(1, roles=("MID",)), champ(2, roles=("MID",)), MatchupTable(), CFG)
    assert "Both want Mid" in titles(notes)
    # a second usual role means they can both fit
    assert pair_insights.lane_clash(champ(1, roles=("MID",)), champ(2, roles=("MID", "TOP"))) is None


def test_against_win_rate_flips_when_the_pair_is_swapped():
    a, b = champ(1), champ(2, roles=("MID",))
    table = MatchupTable(enemy={(1, 2): 58.0})
    assert pair_insights.analyse_pair(a, b, table, CFG)["against"]["win_rate"] == 58.0
    assert pair_insights.analyse_pair(b, a, table, CFG)["against"]["win_rate"] == 42.0
    note = pair_insights.analyse_pair(b, a, table, CFG)["against"]["notes"][0]
    assert note["title"] == "C1 counters C2" and note["kind"] == "b"


def test_always_two_or_three_notes_per_side():
    pairs = [
        (champ(1), champ(2)),                                                      # plain same-lane pair, no data
        (champ(1, roles=("JUNGLE",)), champ(2, roles=("SUPPORT",))),               # never meet in lane
        (champ(1, scaling=1, attack_range=3, waveclear=3, damage_type="M", cc=5, utility=5),
         champ(2, scaling=3, attack_range=1, waveclear=1, cc=5, utility=5)),       # lots going on
    ]
    table = MatchupTable(ally={(1, 2): 45.0}, enemy={(1, 2): 65.0})
    for a, b in pairs:
        for t in (MatchupTable(), table):
            out = pair_insights.analyse_pair(a, b, t, CFG)
            assert 2 <= len(out["same_team"]["notes"]) <= 3
            assert 2 <= len(out["against"]["notes"]) <= 3


def test_effects_switched_off_give_no_notes():
    cfg = copy.deepcopy(CFG)
    for section in ("win_rates", "range", "waveclear", "champion_scaling", "damage_balance", "off_role"):
        cfg[section]["enabled"] = False
    a = champ(1, roles=("MID",), scaling=1, attack_range=3, waveclear=3)
    b = champ(2, roles=("MID",), scaling=3, attack_range=1, waveclear=1)
    out = pair_insights.analyse_pair(a, b, MatchupTable(ally={(1, 2): 60.0}, enemy={(1, 2): 60.0}), cfg)
    every = titles(out["same_team"]["notes"]) + titles(out["against"]["notes"])
    for word in ("synergy", "counters", "out-ranges", "waves", "damage", "want", "early", "late", "Long-range"):
        assert not any(word in t for t in every), (word, every)

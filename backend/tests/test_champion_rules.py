from app.game.comfort import comfort_modifier, comfort_tier
from app.game.config import simulation_config
from app.game.matchup import apply_coach_draft, lane_matchup
from app.game.models import FAVOURABLE, Champion, PlayerSpec

CFG = simulation_config()


def champ(cid=1, damage=2, sturdiness=2, cc=2, mobility=2, utility=2, difficulty=2):
    return Champion(cid, f"C{cid}", "Mage", 5, difficulty, "M", damage, sturdiness, cc, mobility, utility)


def test_strength_and_weakness_for_every_champion(champions):
    for c in champions.values():
        assert c.strength in FAVOURABLE
        # the weakness is the type that beats the strength
        assert FAVOURABLE[c.weakness] == c.strength


def test_matchup_wheel_is_cyclic():
    assert FAVOURABLE == {"Offence": "Defence", "Defence": "Control", "Control": "Offence"}
    assert sorted(FAVOURABLE.values()) == sorted(FAVOURABLE)


def test_strength_tie_break_is_offence_first():
    assert champ(damage=2, mobility=2, sturdiness=2, cc=2, utility=2).strength == "Offence"


def test_offence_beats_defence_in_lane():
    off = champ(1, damage=3, mobility=3, sturdiness=1, cc=1, utility=1)   # Offence 6
    dfn = champ(2, damage=1, mobility=1, sturdiness=3, cc=3, utility=1)   # Defence 6
    assert off.strength == "Offence" and dfn.strength == "Defence"
    ma, mb, label = lane_matchup(off, dfn, CFG)
    assert ma > 1.0 and mb == 1.0 and label.startswith("A")
    ma2, mb2, label2 = lane_matchup(dfn, off, CFG)
    assert mb2 > 1.0 and ma2 == 1.0 and label2.startswith("B")


def test_same_strength_is_even():
    assert lane_matchup(champ(1), champ(2), CFG) == (1.0, 1.0, None)


def test_strong_vs_slight_multiplier_values():
    mm = CFG["lane"]["matchup_multiplier"]
    off = champ(1, damage=3, mobility=3, sturdiness=1, cc=1, utility=1)        # Offence 6
    big_def = champ(2, damage=1, mobility=1, sturdiness=3, cc=3, utility=1)    # Defence 6, Control 4 -> diff 6-4 = 2
    ma, _, _ = lane_matchup(off, big_def, CFG)
    assert ma == mm["strong"]
    small = champ(3, damage=2, mobility=2, sturdiness=3, cc=2, utility=1)      # Defence 5, Offence 4
    assert small.strength == "Defence"
    ma, _, _ = lane_matchup(off, small, CFG)   # diff = 6 - small.offence(4)... wheel gives Offence > Defence
    assert ma in (mm["slight"], mm["strong"])


def test_coach_draft_scales_only_favourable_bonus():
    assert apply_coach_draft(1.0, 10, CFG) == 1.0
    assert apply_coach_draft(1.25, 5, CFG) == 1.25
    assert apply_coach_draft(1.25, 10, CFG) > 1.25
    assert apply_coach_draft(1.25, 1, CFG) < 1.25


def test_comfort_tiers_follow_pool_position():
    p = PlayerSpec(1, "P", "TOP", 20, 5, 5, 5, 5, 5, (10, 20, 30, 40, 50))
    assert [comfort_tier(p, cid, CFG) for cid in (10, 20, 30, 40, 50)] == \
        ["BEST", "COMFORT", "COMFORT", "FAMILIAR", "FAMILIAR"]
    assert comfort_tier(p, 99, CFG) == "VULNERABLE"


def test_comfort_modifiers_are_fractions():
    assert comfort_modifier("BEST", CFG) == 0.40
    assert comfort_modifier("COMFORT", CFG) == 0.25
    assert comfort_modifier("FAMILIAR", CFG) == 0.10
    assert comfort_modifier("VULNERABLE", CFG) == -0.10

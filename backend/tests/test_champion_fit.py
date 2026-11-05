"""Champion fit ranking: the lane formula with the dice left out (POST /champion-fit)."""
import pytest

from app.game.comfort import comfort_modifier, comfort_tier
from app.game.config import SIMULATION_CONFIG, simulation_config
from app.game.lane_phase import champion_synergy, strength_fit
from app.game.models import Champion, PlayerSpec

STATS = {"aggr": 4, "aware": 6, "pos": 5, "dmg": 8}


def fit(alice, **body):
    return alice.post("/champion-fit", json={**STATS, **body})


def test_ranking_matches_the_lane_formula(alice, champions):
    res = fit(alice, pool=[1, 2, 3, 4, 5], limit=50)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 50
    assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)

    spec = PlayerSpec(0, "", "", 0, STATS["aggr"], STATS["aware"], STATS["pos"], STATS["dmg"], 0, (1, 2, 3, 4, 5))
    for row in rows:
        weights = champion_synergy(champions[row["champion_id"]], SIMULATION_CONFIG)
        base = sum(STATS[s] * weights[s] for s in STATS)
        tier = comfort_tier(spec, row["champion_id"], SIMULATION_CONFIG)
        assert row["comfort_tier"] == tier
        assert row["base"] == round(base, 2)
        fit_mult = strength_fit(spec, champions[row["champion_id"]], SIMULATION_CONFIG)
        assert row["strength"] == champions[row["champion_id"]].strength
        assert row["strength_fit"] == round(fit_mult, 2)
        assert row["score"] == round(base * (1 + comfort_modifier(tier, SIMULATION_CONFIG)) * fit_mult, 2)


def test_limit_defaults_to_ten(alice):
    assert len(fit(alice).json()) == 10


def test_no_limit_returns_every_enabled_champion(alice, champions):
    rows = fit(alice, limit=None).json()
    assert len(rows) == len(alice.get("/champions").json())
    assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)
    assert all(r["class"] == champions[r["champion_id"]].champ_class for r in rows)


def test_best_pick_slot_adds_forty_percent(alice, champions):
    unpooled = {r["champion_id"]: r for r in fit(alice, limit=50).json()}
    champ_id, row = next(iter(unpooled.items()))
    pooled = next(r for r in fit(alice, pool=[champ_id], limit=50).json() if r["champion_id"] == champ_id)
    assert row["comfort_tier"] == "VULNERABLE" and pooled["comfort_tier"] == "BEST"
    assert pooled["base"] == row["base"]
    spec = PlayerSpec(0, "", "", 0, STATS["aggr"], STATS["aware"], STATS["pos"], STATS["dmg"], 0, ())
    fit_mult = strength_fit(spec, champions[champ_id], SIMULATION_CONFIG)
    assert pooled["score"] == round(row["base"] * 1.40 * fit_mult, 2)
    assert row["score"] == round(row["base"] * 0.90 * fit_mult, 2)


def test_stats_behind_the_strength_decide_the_top_picks(alice):
    offence = alice.post("/champion-fit", json={"aggr": 1, "aware": 1, "pos": 10, "dmg": 10}).json()
    control = alice.post("/champion-fit", json={"aggr": 1, "aware": 10, "pos": 1, "dmg": 1}).json()
    assert all(r["strength"] == "Offence" and r["strength_fit"] == 1.25 for r in offence[:5])
    assert all(r["strength"] == "Control" and r["strength_fit"] == 1.25 for r in control[:5])
    assert not {r["champion_id"] for r in offence[:5]} & {r["champion_id"] for r in control[:5]}


# ------------------------------------------------------------ strength fit (engine)
def player(aggr=5, aware=5, pos=5, dmg=5):
    return PlayerSpec(0, "", "", 0, aggr, aware, pos, dmg, 0, ())


def champ(damage=1, sturdiness=1, cc=1, mobility=1, utility=1):
    return Champion(0, "", "", 0, 0, "P", damage, sturdiness, cc, mobility, utility)


OFFENCE, DEFENCE, CONTROL = champ(damage=5, mobility=5), champ(sturdiness=5, cc=4), champ(utility=5, cc=4)


def test_strength_fit_reads_the_stats_behind_each_strength():
    assert (OFFENCE.strength, DEFENCE.strength, CONTROL.strength) == ("Offence", "Defence", "Control")
    cfg = SIMULATION_CONFIG
    assert strength_fit(player(dmg=10, pos=10), OFFENCE, cfg) == pytest.approx(1.25)
    assert strength_fit(player(dmg=10, pos=1), OFFENCE, cfg) == pytest.approx(1.0)   # averaged
    assert strength_fit(player(aggr=1), DEFENCE, cfg) == pytest.approx(0.75)
    assert strength_fit(player(aware=10, aggr=1), CONTROL, cfg) == pytest.approx(1.25)
    assert strength_fit(PlayerSpec(0, "", "", 0, 6, 6, 6, 6, 0, ()), OFFENCE, cfg) == pytest.approx(1 + 0.25 * 0.5 / 4.5)


def test_strength_fit_can_be_switched_off():
    cfg = simulation_config()
    cfg["lane"]["strength_fit"]["enabled"] = False
    assert strength_fit(player(aggr=1), DEFENCE, cfg) == 1.0


def test_top_stat_follows_the_strongest_attribute(alice):
    rows = alice.post("/champion-fit", json={"aggr": 1, "aware": 1, "pos": 1, "dmg": 10}).json()
    assert all(r["top_stat"] == "dmg" for r in rows)


def test_rejects_out_of_range_stats_and_big_pools(alice):
    assert fit(alice, dmg=11).status_code == 422
    assert fit(alice, aggr=0).status_code == 422
    assert fit(alice, pool=[1, 2, 3, 4, 5, 6]).status_code == 422
    assert fit(alice, limit=0).status_code == 422


def test_requires_login(client):
    assert client.post("/api/v1/champion-fit", json=STATS).status_code == 401


# ------------------------------------------------------------ roles
def by_id(rows):
    return {r["champion_id"]: r for r in rows}


def off_role_for(champions, lane):
    """An enabled champion with role data that never plays `lane`."""
    return next(c for c in champions.values() if c.roles and lane not in c.roles)


def test_no_role_means_no_off_role_penalty(alice):
    rows = fit(alice, limit=None).json()
    assert all(r["lane"] is None and r["role_status"] is None and r["off_role_penalty"] == 0 for r in rows)


def test_off_role_champions_lose_score_and_sink(alice, champions):
    champ = off_role_for(champions, "SUPPORT")
    plain = by_id(fit(alice, limit=None).json())[champ.id]
    rows = fit(alice, limit=None, role="SUPPORT").json()
    row = by_id(rows)[champ.id]
    penalty = SIMULATION_CONFIG["off_role"]["lane_penalty"]
    assert row["role_status"] == "OFF_ROLE" and row["lane"] == "SUPPORT"
    assert row["off_role_penalty"] == pytest.approx(penalty)
    assert row["score"] == pytest.approx(plain["score"] * (1 - penalty), abs=0.02)
    penalised = [r["off_role_penalty"] > 0 for r in rows]
    assert penalised == sorted(penalised)   # every unpenalised row comes first
    first = next(r for r in rows if r["off_role_penalty"] == 0)
    assert first["role_status"] in ("MAIN", "SECONDARY", None, "OFF_ROLE_EXEMPT")


def test_top_pool_picks_are_exempt_off_role(alice, champions):
    champ = off_role_for(champions, "SUPPORT")
    plain = by_id(fit(alice, limit=None, pool=[champ.id]).json())[champ.id]
    row = by_id(fit(alice, limit=None, pool=[champ.id], role="SUPPORT").json())[champ.id]
    assert row["role_status"] == "OFF_ROLE_EXEMPT" and row["off_role_penalty"] == 0
    assert row["score"] == plain["score"]


def test_secondary_role_counts_when_it_suits_better(alice, champions):
    champ = next(c for c in champions.values() if c.roles and "SUPPORT" not in c.roles)
    row = by_id(fit(alice, limit=None, role="SUPPORT", secondary_role=champ.roles[0]).json())[champ.id]
    assert row["lane"] == champ.roles[0] and row["role_status"] == "MAIN" and row["off_role_penalty"] == 0


def test_primary_role_wins_ties(alice, champions):
    champ = next(c for c in champions.values() if c.roles)
    lane = champ.roles[0]
    other = next(ln for ln in ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT") if ln not in champ.roles)
    row = by_id(fit(alice, limit=None, role=lane, secondary_role=other).json())[champ.id]
    assert row["lane"] == lane


def test_rejects_unknown_roles(alice):
    assert fit(alice, role="ADC").status_code == 422

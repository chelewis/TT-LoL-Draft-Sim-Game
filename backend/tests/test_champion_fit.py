"""Champion fit ranking: the lane formula with the dice left out (POST /champion-fit)."""
from app.game.comfort import comfort_modifier, comfort_tier
from app.game.config import SIMULATION_CONFIG
from app.game.lane_phase import champion_synergy
from app.game.models import PlayerSpec

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
        assert row["score"] == round(base * (1 + comfort_modifier(tier, SIMULATION_CONFIG)), 2)


def test_limit_defaults_to_ten(alice):
    assert len(fit(alice).json()) == 10


def test_best_pick_slot_adds_forty_percent(alice):
    unpooled = {r["champion_id"]: r for r in fit(alice, limit=50).json()}
    champ_id, row = next(iter(unpooled.items()))
    pooled = next(r for r in fit(alice, pool=[champ_id], limit=50).json() if r["champion_id"] == champ_id)
    assert row["comfort_tier"] == "VULNERABLE" and pooled["comfort_tier"] == "BEST"
    assert pooled["base"] == row["base"]
    assert pooled["score"] == round(row["base"] * 1.40, 2)
    assert row["score"] == round(row["base"] * 0.90, 2)


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

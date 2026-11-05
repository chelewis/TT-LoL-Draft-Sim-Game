"""Meta views: champion lane win rates (from the against-team win rate table) and pick rates, for every player."""
from sqlalchemy import delete, or_

from app.core.database import SessionLocal
from app.models import ChampionMatchup
from app.services.meta_service import lane_win_rate, soften
from tests.test_api_admin import admin, cells, put  # noqa: F401  (admin is a fixture)


def by_name(api):
    res = api.get("/meta/champions")
    assert res.status_code == 200, res.text
    return {row["name"]: row for row in res.json()}


def clear_against_rates(champion_id):
    with SessionLocal() as db:
        db.execute(delete(ChampionMatchup).where(
            ChampionMatchup.kind == "enemy",
            or_(ChampionMatchup.champion_a_id == champion_id, ChampionMatchup.champion_b_id == champion_id)))
        db.commit()


def test_every_player_sees_every_enabled_champion(alice):
    rows = by_name(alice)
    champions = alice.get("/champions").json()
    assert set(rows) == {c["name"] for c in champions}
    row = rows[champions[0]["name"]]
    assert set(row) == {"id", "name", "class", "roles", "role", "win_rate", "win_rate_source", "opponents", "pick_rate"}
    assert row["pick_rate"] == champions[0]["pick_rate"]
    assert alice.client.get("/api/v1/meta/champions").status_code == 401              # not signed in


def test_win_rate_only_counts_opponents_with_the_same_main_role(admin):  # noqa: F811
    champions = admin.get("/champions").json()
    me = next(c for c in champions if c["roles"])
    same = [c for c in champions if c["roles"] and c["roles"][0] == me["roles"][0] and c["id"] != me["id"]]
    other = next(c for c in champions if c["roles"] and c["roles"][0] != me["roles"][0])
    foe = same[0]
    clear_against_rates(me["id"])
    assert put(admin, "enemy", (me["id"], foe["id"], 60), (other["id"], me["id"], 10)).status_code == 200

    rows = by_name(admin)
    assert rows[me["name"]]["role"] == me["roles"][0]
    assert rows[me["name"]]["win_rate"] == round(soften(60), 1)       # the off-lane 90% matchup is ignored
    assert rows[me["name"]]["win_rate_source"] == "matchups"
    assert rows[me["name"]]["opponents"] == 1

    # the opponent's side of the pair counts too
    assert rows[foe["name"]]["opponents"] == len(same)                # every same-lane champion, me included


def test_matchups_are_weighted_by_opponent_pick_rate():
    # a rare counter barely moves the result; a common one does
    assert lane_win_rate([(55, 10), (55, 10), (20, 0.5)]) > 54
    assert lane_win_rate([(55, 10), (55, 10), (20, 20)]) < 46
    # opponents with no pick rate still count a little
    assert abs(lane_win_rate([(60, 0)]) - soften(60)) < 1e-9


def test_extreme_matchups_are_softened():
    assert soften(50) == 50
    assert abs(soften(52) - 52) < 0.05                                # small gaps pass almost unchanged
    assert 35 < soften(0) < soften(30) < 40                           # a hopeless matchup counts as at most 15 below
    assert soften(100) < 65
    assert abs(soften(30) + soften(70) - 100) < 1e-9          # the same either side of 50


def test_champion_without_against_team_data_uses_its_own_win_rate(alice):
    champion = alice.get("/champions").json()[0]
    clear_against_rates(champion["id"])
    row = by_name(alice)[champion["name"]]
    assert row["win_rate"] == champion["win_rate"]
    assert row["win_rate_source"] == "base"
    assert row["opponents"] == 0


# ------------------------------------------------------------- champion pairs
def pair(api, a, b):
    return api.get(f"/meta/pair?a={a}&b={b}")


def test_pair_shows_both_win_rates_and_notes(admin):  # noqa: F811
    a, b = admin.get("/champions").json()[:2]
    assert put(admin, "ally", (a["id"], b["id"], 57)).status_code == 200
    assert put(admin, "enemy", (b["id"], a["id"], 40)).status_code == 200           # b's side: a wins 60%

    res = pair(admin, a["id"], b["id"])
    assert res.status_code == 200, res.text
    out = res.json()
    assert [c["name"] for c in out["champions"]] == [a["name"], b["name"]]
    assert out["same_team"]["win_rate"] == 57 and out["same_team"]["edited"] is True
    assert out["against"]["win_rate"] == 60 and out["against"]["edited"] is True
    for side in ("same_team", "against"):
        assert 2 <= len(out[side]["notes"]) <= 3
        assert all(set(n) == {"kind", "title", "detail", "weight"} for n in out[side]["notes"])

    assert pair(admin, b["id"], a["id"]).json()["against"]["win_rate"] == 40          # seen from b's side


def test_pair_without_data_still_has_notes(alice):
    a, b = alice.get("/champions").json()[:2]
    clear_against_rates(a["id"])
    out = pair(alice, a["id"], b["id"]).json()
    assert out["against"]["win_rate"] is None and out["against"]["games"] == 0 and out["against"]["edited"] is False
    assert len(out["against"]["notes"]) >= 2


def test_pair_needs_two_known_champions(alice):
    a = alice.get("/champions").json()[0]
    assert pair(alice, a["id"], a["id"]).status_code == 400
    assert pair(alice, a["id"], 999999).status_code == 404
    assert alice.client.get(f"/api/v1/meta/pair?a={a['id']}&b=1").status_code == 401   # not signed in

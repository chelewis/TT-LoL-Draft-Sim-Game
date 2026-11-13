"""Seasons (phase 2): round robin playoffs, and Swiss stages that end in a bracket."""
from collections import Counter

from tests.test_season_flow import started


def sim_to_end(alice, season_id, limit=40):
    """Auto-sim your match and advance until the season is over. Returns every hub view on the way."""
    views = []
    for _ in range(limit):
        view = alice.get(f"/seasons/{season_id}").json()
        views.append(view)
        if view["status"] == "COMPLETED":
            return views
        mine = view["my_match"]
        if mine and mine["status"] != "COMPLETED":
            res = alice.post(f"/seasons/matches/{mine['id']}/auto")
            assert res.status_code == 200, res.text
        res = alice.post(f"/seasons/{season_id}/advance")
        assert res.status_code == 200, res.text
    raise AssertionError("the season never finished")


def test_round_robin_then_a_final(alice, default_team_ids):
    season = started(alice, default_team_ids, playoff_size=2, final_series="BO3")
    assert season["bracket"]["size"] == 2 and season["bracket"]["rounds"][0]["name"] == "Final"
    views = sim_to_end(alice, season["id"])
    playoff_views = [v for v in views if v["status"] == "PLAYOFFS"]
    assert playoff_views and playoff_views[0]["stage"] == "PLAYOFF" and playoff_views[0]["total_rounds"] == 1
    top_two = {r["team"]["id"] for r in playoff_views[0]["standings"][:2]}
    final = views[-1]["bracket"]["rounds"][0]["matches"]
    assert len(final) == 1 and {final[0]["home"]["id"], final[0]["away"]["id"]} == top_two
    assert final[0]["format"] == "BO3" and max(final[0]["home_score"], final[0]["away_score"]) == 2
    # the regular season's top seed is home in the final, and the final's winner is champion
    assert final[0]["home"]["id"] == playoff_views[0]["standings"][0]["team"]["id"]
    assert views[-1]["champion"]["id"] == final[0]["winner_team_id"]
    # teams that missed the playoffs are marked out
    out = {r["team"]["id"] for r in views[-1]["standings"] if r["eliminated"]}
    assert len(out) == 3


def test_playoffs_need_room(alice):
    res = alice.post("/seasons", {"name": "x", "options": {"team_count": 4, "playoff_size": 8}})
    assert res.status_code == 422
    res = alice.post("/seasons", {"name": "x", "options": {"team_count": 4, "playoff_size": 3}})
    assert res.status_code == 422


def test_swiss_needs_8_or_16_teams(alice):
    assert alice.post("/seasons", {"name": "x", "format": "SWISS", "options": {"team_count": 6}}).status_code == 422


def test_swiss_stage_into_a_bracket(alice, default_team_ids):
    season = started(alice, default_team_ids, team_count=8, regular_series="BO1", playoff_series="BO1",
                     final_series="BO1", format="SWISS")
    assert season["format"] == "SWISS" and season["stage"] == "SWISS"
    assert season["options"]["swiss_wins"] == 2 and season["options"]["playoff_size"] == 4
    assert len(season["round_matches"]) == 4 and season["total_rounds"] == 3
    views = sim_to_end(alice, season["id"])
    swiss = [v for v in views if v["stage"] == "SWISS"]
    assert 2 <= len(swiss) <= 3
    last = views[-1]
    statuses = Counter(r["swiss_status"] for r in last["standings"])
    assert statuses == {"QUALIFIED": 4, "ELIMINATED": 4}
    qualified = {r["team"]["id"] for r in last["standings"] if r["swiss_status"] == "QUALIFIED"}
    semis, final = last["bracket"]["rounds"]
    assert [semis["name"], final["name"]] == ["Semifinals", "Final"]
    assert {t for m in semis["matches"] for t in (m["home"]["id"], m["away"]["id"])} == qualified
    assert len(final["matches"]) == 1
    assert {final["matches"][0]["home"]["id"], final["matches"][0]["away"]["id"]} == \
        {m["winner_team_id"] for m in semis["matches"]}
    assert last["champion"]["id"] == final["matches"][0]["winner_team_id"]
    schedule = alice.get(f"/seasons/{season['id']}/schedule").json()
    assert [r["stage"] for r in schedule["rounds"]][-2:] == ["PLAYOFF", "PLAYOFF"]
    assert schedule["rounds"][-1]["name"] == "Final"

"""Seasons (phase 1): a single player Bring Your Own round robin against generated CPU teams."""
import pytest

from tests.test_cpu_mode import let_cpu_think, play_my_turns


def create(alice, format="ROUND_ROBIN", **options):
    body = {"name": "Spring Split", "format": format, "rules": {"timers_enabled": False},
            "options": {"team_count": 4, **options}}
    res = alice.post("/seasons", body)
    assert res.status_code == 201, res.text
    return res.json()


def entered(alice, default_team_ids, **options):
    season = create(alice, **options)
    res = alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    assert res.status_code == 201, res.text
    return res.json()


def started(alice, default_team_ids, **options):
    season = entered(alice, default_team_ids, **options)
    res = alice.post(f"/seasons/{season['id']}/start")
    assert res.status_code == 200, res.text
    return res.json()


def finish_live_game(alice, gid):
    """Play the user's turns of a live season game against the CPU, then confirm the lineup."""
    state = alice.get(f"/games/{gid}/state").json()
    me = state["you"]["team"]
    play_my_turns(alice, gid, me)
    res = alice.post(f"/games/{gid}/lineup/ready")
    assert res.status_code == 200, res.text
    return res.json()


def test_create_season_starts_in_setup(alice):
    season = create(alice)
    assert season["status"] == "SETUP" and season["is_creator"] and len(season["code"]) == 6
    assert season["options"]["team_count"] == 4 and season["options"]["human_slots"] == 1
    assert season["can_start"] is False                     # no team entered yet
    assert [s["id"] for s in alice.get("/seasons").json()] == [season["id"]]


def test_entering_a_team_copies_it_into_the_season(alice, default_team_ids):
    before_teams = alice.get("/teams").json()
    before_players = alice.get("/players").json()
    season = entered(alice, default_team_ids)
    mine = next(t for t in season["teams"] if t["is_you"])
    assert mine["team_id"] != default_team_ids[0]           # a frozen copy, not the team itself
    assert season["can_start"] is True
    # the season's copies never show up on the management pages
    assert alice.get("/teams").json() == before_teams
    assert alice.get("/players").json() == before_players
    assert alice.get(f"/teams/{mine['team_id']}").status_code == 404
    # one team per manager
    res = alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[1]})
    assert res.status_code == 409


def test_withdraw_a_team(alice, default_team_ids):
    season = entered(alice, default_team_ids)
    res = alice.delete(f"/seasons/{season['id']}/teams/mine")
    assert res.status_code == 200 and res.json()["teams"] == []


def test_teams_must_meet_the_season_rules(alice, default_team_ids):
    body = {"name": "Low elo", "rules": {"ruleset": "LOW_ELO", "max_rank": "BRONZE", "max_player_total": 28,
                                         "max_team_total": 135}, "options": {"team_count": 4}}
    season = alice.post("/seasons", body).json()
    res = alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    assert res.status_code == 400 and "rules" in res.json()["detail"]


def test_only_members_can_see_a_season(alice, bob):
    season = create(alice)
    assert bob.get(f"/seasons/{season['id']}").status_code == 404


def test_start_fills_with_cpu_teams_and_draws_the_schedule(alice, default_team_ids):
    season = started(alice, default_team_ids)
    assert season["status"] == "REGULAR" and season["current_round"] == 1 and season["total_rounds"] == 3
    assert len(season["teams"]) == 4 and sum(t["is_cpu"] for t in season["teams"]) == 3
    assert sorted(t["seed"] for t in season["teams"]) == [1, 2, 3, 4]
    assert len(season["round_matches"]) == 2
    assert season["my_match"] is not None and season["my_match"]["status"] == "SCHEDULED"
    schedule = alice.get(f"/seasons/{season['id']}/schedule").json()
    assert [len(r["matches"]) for r in schedule["rounds"]] == [2, 2, 2]
    # the CPU teams are season content too
    cpu = next(t for t in season["teams"] if t["is_cpu"])
    detail = alice.get(f"/seasons/{season['id']}/teams/{cpu['id']}").json()
    assert all(detail["view"]["roster"][lane] for lane in ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT"))
    assert detail["view"]["selectable"]


def test_a_round_waits_for_the_managers_match(alice, default_team_ids):
    season = started(alice, default_team_ids)
    res = alice.post(f"/seasons/{season['id']}/advance")
    assert res.status_code == 409 and "still to play" in res.json()["detail"]


def test_play_a_match_live_against_the_cpu(alice, default_team_ids):
    season = started(alice, default_team_ids)
    match = season["my_match"]
    res = alice.post(f"/seasons/matches/{match['id']}/play")
    assert res.status_code == 200, res.text
    gid = res.json()["game_id"]
    # pressing play again returns the same game
    assert alice.post(f"/seasons/matches/{match['id']}/play").json()["game_id"] == gid
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "DRAFTING"
    assert state["season"]["season_id"] == season["id"] and state["season"]["match_id"] == match["id"]
    assert state["rematch"] is None or state["rematch"]["available"] is False
    # the teams are fixed by the fixture
    assert alice.post(f"/lobbies/{state['lobby_id']}/team", {"team_id": default_team_ids[1], "side": "BLUE"}) \
        .status_code == 409
    assert alice.post(f"/lobbies/{state['lobby_id']}/leave").status_code == 409
    final = finish_live_game(alice, gid)
    assert final["status"] == "COMPLETED"
    assert alice.post(f"/games/{gid}/rerun").status_code == 409
    view = alice.get(f"/seasons/{season['id']}").json()
    mine = next(m for m in view["round_matches"] if m["id"] == match["id"])
    assert mine["status"] == "COMPLETED" and mine["played_mode"] == "LIVE"
    assert sorted([mine["home_score"], mine["away_score"]]) == [0, 1]
    # with the manager's match done the round can move on; the CPU plays the other match
    view = alice.post(f"/seasons/{season['id']}/advance").json()
    assert view["current_round"] == 2
    assert sum(r["played"] for r in view["standings"]) == 4


def test_auto_sim_and_finish_the_season(alice, default_team_ids):
    season = started(alice, default_team_ids)
    for round_ in (1, 2, 3):
        view = alice.get(f"/seasons/{season['id']}").json()
        assert view["current_round"] == round_
        res = alice.post(f"/seasons/matches/{view['my_match']['id']}/auto")
        assert res.status_code == 200, res.text
        assert next(m for m in res.json()["round_matches"] if m["yours"])["played_mode"] == "AUTO"
        res = alice.post(f"/seasons/{season['id']}/advance")
        assert res.status_code == 200, res.text
    view = res.json()
    assert view["status"] == "COMPLETED" and view["champion"] is not None
    assert view["champion"]["id"] == view["standings"][0]["team"]["id"]
    assert all(r["played"] == 3 for r in view["standings"])
    assert sum(r["wins"] for r in view["standings"]) == 6
    # season games can be watched by members, results included
    schedule = alice.get(f"/seasons/{season['id']}/schedule").json()
    cpu_game = next(g for r in schedule["rounds"] for m in r["matches"] if not m["has_manager"] for g in m["games"])
    assert alice.get(f"/games/{cpu_game['game_id']}/state").json()["status"] == "COMPLETED"
    assert alice.get(f"/games/{cpu_game['game_id']}/result").status_code == 200
    assert alice.post(f"/games/{cpu_game['game_id']}/ready").status_code == 404     # watch, don't act
    # player stats for my team add up over the season
    mine = next(t for t in view["teams"] if t["is_you"])
    detail = alice.get(f"/seasons/{season['id']}/teams/{mine['id']}").json()
    assert all(s["games"] == 3 for s in detail["player_stats"].values())
    assert detail["record"]["played"] == 3


def test_force_advance_auto_sims_an_unfinished_live_game(alice, default_team_ids):
    season = started(alice, default_team_ids)
    gid = alice.post(f"/seasons/matches/{season['my_match']['id']}/play").json()["game_id"]
    res = alice.post(f"/seasons/{season['id']}/advance", {"force": True})
    assert res.status_code == 200, res.text
    assert alice.get(f"/games/{gid}/state").json()["status"] == "COMPLETED"
    assert res.json()["current_round"] == 2


def test_best_of_three_fixtures(alice, default_team_ids):
    season = started(alice, default_team_ids, regular_series="BO3")
    match = season["my_match"]
    gid = alice.post(f"/seasons/matches/{match['id']}/play").json()["game_id"]
    state = finish_live_game(alice, gid)
    assert state["series"] is not None and state["series"]["format"] == "BO3"
    # let the CPU take the rest of the series
    res = alice.post(f"/seasons/matches/{match['id']}/auto")
    assert res.status_code == 200, res.text
    mine = next(m for m in res.json()["round_matches"] if m["id"] == match["id"])
    assert mine["status"] == "COMPLETED" and max(mine["home_score"], mine["away_score"]) == 2
    assert len(mine["games"]) in (2, 3) and mine["played_mode"] == "LIVE"
    series = alice.get(f"/series/{mine['series_id']}").json()
    assert len(series["games"]) == len(mine["games"])


def test_only_the_creator_can_advance(alice, bob, default_team_ids):
    season = started(alice, default_team_ids)
    assert bob.post(f"/seasons/{season['id']}/advance").status_code == 404     # not even a member


def test_cancel(alice, default_team_ids):
    season = started(alice, default_team_ids)
    assert alice.post(f"/seasons/{season['id']}/cancel").json()["status"] == "CANCELLED"
    assert alice.post(f"/seasons/{season['id']}/advance").status_code == 409


def test_one_simulation_per_season_at_a_time():
    from fastapi import HTTPException

    from app.services.season_match_service import simulating
    with simulating(12345):
        with pytest.raises(HTTPException) as err:
            with simulating(12345):
                pass
        assert err.value.status_code == 409
        with simulating(54321):       # other seasons aren't blocked
            pass
    with simulating(12345):           # released afterwards
        pass

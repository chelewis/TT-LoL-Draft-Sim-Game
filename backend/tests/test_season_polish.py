"""Seasons (phase 5): stat leaders and awards, and notifications (the inbox, its triggers and /ws/me)."""
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.services import season_service
from tests.test_season_draft import run_draft, with_bob
from tests.test_season_flow import create
from tests.test_season_flow import started as solo_started
from tests.test_season_multiplayer import head_to_head, started


def kinds(user):
    return [n["kind"] for n in user.get("/notifications").json()["items"]]


def play_out(alice, season_id):
    view = alice.get(f"/seasons/{season_id}").json()
    for _ in range(20):
        if view["status"] == "COMPLETED":
            return view
        res = alice.post(f"/seasons/{season_id}/advance", {"force": True})
        assert res.status_code == 200, res.text
        view = alice.get(f"/seasons/{season_id}").json()
    raise AssertionError("the season never finished")


# ------------------------------------------------------------------ stats
def test_stats_before_any_games(alice, default_team_ids):
    season = solo_started(alice, default_team_ids)
    stats = alice.get(f"/seasons/{season['id']}/stats").json()
    assert stats["games"] == 0 and stats["players"] == [] and not stats["final"]
    assert stats["awards"]["season_mvp"] is None


def test_leaders_and_awards_after_the_season(alice, default_team_ids):
    season = solo_started(alice, default_team_ids, playoff_size=2, final_series="BO3")
    view = play_out(alice, season["id"])
    stats = alice.get(f"/seasons/{season['id']}/stats").json()
    assert stats["final"] and stats["games"] >= 3 * 2 + 2
    assert len(stats["players"]) == 20                       # four teams of five
    assert all(p["team"]["id"] for p in stats["players"])
    rating = next(c for c in stats["leaders"] if c["key"] == "rating")
    assert len(rating["rows"]) == 5 and rating["rows"][0]["value"] >= rating["rows"][-1]["value"]
    awards = stats["awards"]
    assert awards["season_mvp"]["games"] >= stats["min_games"]
    assert awards["finals_mvp"]["team"]["id"] == view["champion"]["id"]
    assert [a["lane"] for a in awards["all_pro"]] == ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"]
    assert all(a["player"]["lane"] == a["lane"] for a in awards["all_pro"])
    assert "SEASON_OVER" in kinds(alice)


def test_stats_are_for_members_only(alice, bob, default_team_ids):
    season = solo_started(alice, default_team_ids)
    assert bob.get(f"/seasons/{season['id']}/stats").status_code == 404


# ----------------------------------------------------------- notifications
def test_join_and_first_round_notifications(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    assert kinds(alice) == ["SEASON_JOINED"]                 # Alice started it: no "your match is ready" for her
    inbox = bob.get("/notifications").json()
    assert inbox["unread"] == 1 and inbox["items"][0]["kind"] == "MATCH_READY"
    assert inbox["items"][0]["link"] == f"/seasons/{season['id']}" and "Round 1" in inbox["items"][0]["body"]
    # Alice advancing tells Bob his next match is ready, once
    for user in (alice, bob):
        mine = user.get(f"/seasons/{season['id']}").json()["my_match"]
        user.post(f"/seasons/matches/{mine['id']}/auto")
    alice.post(f"/seasons/{season['id']}/advance")
    assert kinds(bob).count("MATCH_READY") == 2 and kinds(alice) == ["SEASON_JOINED"]


def test_marking_notifications_read(alice, bob, default_team_ids):
    started(alice, bob, default_team_ids)
    first = bob.get("/notifications").json()["items"][0]
    assert bob.post("/notifications/read", {"ids": [first["id"]]}).json()["unread"] == 0
    assert alice.post("/notifications/read", {"ids": [first["id"]]}).json()["unread"] == 1   # not hers to mark
    inbox = alice.post("/notifications/read").json()
    assert inbox["unread"] == 0 and all(n["read"] for n in inbox["items"])


def test_opponent_ready_and_auto_sim_requests(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    view, match = head_to_head(alice, bob, season)
    alice.post(f"/seasons/matches/{match['id']}/auto")
    assert "AUTO_SIM_ASKED" in kinds(bob)
    alice.post(f"/seasons/matches/{match['id']}/auto", {"ready": False})
    alice.post(f"/seasons/matches/{match['id']}/auto")
    assert kinds(bob).count("AUTO_SIM_ASKED") == 1           # asked again: no second notification
    alice.post(f"/seasons/matches/{match['id']}/play")
    assert "OPPONENT_READY" in kinds(bob) and "OPPONENT_READY" not in kinds(alice)


def test_deadline_warning(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids, round_deadline_hours=12)
    with SessionLocal() as db:
        season_service.process_deadlines(db, utcnow() + timedelta(hours=9))
    assert "DEADLINE" not in kinds(bob)
    for _ in range(2):
        with SessionLocal() as db:
            season_service.process_deadlines(db, utcnow() + timedelta(hours=10, minutes=30))
    assert kinds(bob).count("DEADLINE") == 1 and kinds(alice).count("DEADLINE") == 1
    assert alice.get(f"/seasons/{season['id']}").json()["current_round"] == 1


def test_short_rounds_warn_later(alice, bob, default_team_ids):
    started(alice, bob, default_team_ids, round_deadline_hours=1)
    with SessionLocal() as db:
        season_service.process_deadlines(db, utcnow() + timedelta(minutes=30))
    assert "DEADLINE" not in kinds(bob)
    with SessionLocal() as db:
        season_service.process_deadlines(db, utcnow() + timedelta(minutes=50))
    assert "DEADLINE" in kinds(bob)


def test_on_the_clock(alice, bob):
    season = with_bob(alice, bob)
    view = alice.post(f"/seasons/{season['id']}/start").json()
    first = view["draft"]["on_the_clock"]["manager"]["id"]
    users = {alice.user["id"]: alice, bob.user["id"]: bob}
    assert "ON_THE_CLOCK" in kinds(users[first])
    assert "SEASON_STARTED" in kinds(bob) and "SEASON_STARTED" not in kinds(alice)
    run_draft(view, users)
    # two managers snake-drafting 10 picks: A, BB, AA, BB, AA, B -- one notification per turn of the snake
    assert kinds(alice).count("ON_THE_CLOCK") + kinds(bob).count("ON_THE_CLOCK") == 6


def test_removed_manager_is_told(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    bob_team = next(t for t in season["teams"] if t["manager"] and t["manager"]["id"] == bob.user["id"])
    alice.post(f"/seasons/{season['id']}/teams/{bob_team['id']}/release")
    assert "SEASON_REMOVED" in kinds(bob)


def test_notification_socket(client, alice, bob, default_team_ids):
    season = create(alice, human_slots=2)
    alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    with client.websocket_connect(f"/ws/me?token={alice.token}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]})
        assert ws.receive_json() == {"type": "NOTIFICATION"}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/me?token=nope") as ws:
            ws.receive_json()

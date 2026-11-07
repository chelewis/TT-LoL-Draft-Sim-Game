"""Seasons (phase 3): several managers in one season, invite codes, manager vs manager matches, managers leaving,
round deadlines and the season's WebSocket channel."""
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.services import season_service
from tests.conftest import play_draft
from tests.test_cpu_mode import free_champion, let_cpu_think, play_my_turns
from tests.test_season_flow import create


def two_managers(alice, bob, default_team_ids, **options):
    """Alice creates a 4-team season with two manager slots and enters a team; Bob joins with the code."""
    season = create(alice, human_slots=2, **options)
    assert alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]}).status_code == 201
    res = bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]})
    assert res.status_code == 201, res.text
    return res.json()


def started(alice, bob, default_team_ids, **options):
    season = two_managers(alice, bob, default_team_ids, **options)
    res = alice.post(f"/seasons/{season['id']}/start")
    assert res.status_code == 200, res.text
    return res.json()


def head_to_head(alice, bob, season):
    """Advance until Alice's match this round is against Bob, auto-simming their other matches on the way."""
    for _ in range(3):
        view = alice.get(f"/seasons/{season['id']}").json()
        match = view["my_match"]
        if match and not match["home"]["is_cpu"] and not match["away"]["is_cpu"]:
            return view, match
        for user in (alice, bob):
            mine = user.get(f"/seasons/{season['id']}").json()["my_match"]
            if mine and mine["status"] != "COMPLETED":
                assert user.post(f"/seasons/matches/{mine['id']}/auto").status_code == 200
        assert alice.post(f"/seasons/{season['id']}/advance").status_code == 200
    raise AssertionError("Alice and Bob never met")


def manager_of(view, match, side):
    return match[side]["manager"]["id"]


def test_join_with_the_invite_code(alice, bob, default_team_ids):
    season = create(alice, human_slots=2)
    preview = bob.get(f"/seasons/join/{season['code'].lower()}").json()
    assert preview["name"] == "Spring Split" and preview["can_join"] and not preview["is_member"]
    assert preview["open_slots"] == 2 and preview["created_by"]["username"] == "alice"
    assert bob.get(f"/seasons/{season['id']}").status_code == 404          # not a member yet
    alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    # the same team twice would be confusing in the table
    res = bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[0]})
    assert res.status_code == 409 and "already in this season" in res.json()["detail"]
    view = bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]}).json()
    assert view["managers"] == 2 and view["my_team_id"] is not None and not view["is_creator"]
    assert bob.get(f"/seasons/{season['id']}").status_code == 200
    assert [s["id"] for s in bob.get("/seasons").json()] == [season["id"]]
    assert bob.get(f"/seasons/join/{season['code']}").json()["can_join"] is False
    assert bob.get("/seasons/join/NOPE00").status_code == 404


def test_a_full_season_cannot_be_joined(alice, bob, default_team_ids):
    season = create(alice)                                           # one manager slot
    alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    assert bob.get(f"/seasons/join/{season['code']}").json()["can_join"] is False
    res = bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]})
    assert res.status_code == 409 and "slot" in res.json()["detail"]


def test_only_before_the_start(alice, bob, default_team_ids):
    season = create(alice, human_slots=3)
    alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    alice.post(f"/seasons/{season['id']}/start")
    res = bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]})
    assert res.status_code == 409


def test_managers_play_each_other_live(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    assert sum(not t["is_cpu"] for t in season["teams"]) == 2
    view, match = head_to_head(alice, bob, season)
    users = {alice.user["id"]: alice, bob.user["id"]: bob}
    blue, red = users[manager_of(view, match, "home")], users[manager_of(view, match, "away")]
    # the first manager to press Play waits at the ready check
    gid = blue.post(f"/seasons/matches/{match['id']}/play").json()["game_id"]
    state = blue.get(f"/games/{gid}/state").json()
    assert state["status"] == "READY_CHECK" and state["settings"]["mode"] == "MULTI"
    assert state["players"]["blue"]["ready"] and not state["players"]["red"]["ready"]
    # the other manager pressing Play joins the same game and starts the draft
    assert red.post(f"/seasons/matches/{match['id']}/play").json()["game_id"] == gid
    assert red.get(f"/games/{gid}/state").json()["status"] == "DRAFTING"
    play_draft(blue, red, gid, range(1, 500))
    assert blue.post(f"/games/{gid}/lineup/ready").status_code == 200
    assert red.post(f"/games/{gid}/lineup/ready").status_code == 200
    after = alice.get(f"/seasons/{season['id']}").json()["my_match"]
    assert after["status"] == "COMPLETED" and after["played_mode"] == "LIVE"


def test_auto_sim_between_managers_needs_both(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    _, match = head_to_head(alice, bob, season)
    view = alice.post(f"/seasons/matches/{match['id']}/auto").json()
    mine = view["my_match"]
    assert mine["status"] == "SCHEDULED"
    assert mine["auto_requested"] == {"home": mine["home"]["is_you"], "away": mine["away"]["is_you"]}
    # taking it back, then asking again
    assert alice.post(f"/seasons/matches/{match['id']}/auto", {"ready": False}).json()["my_match"]["auto_requested"] \
        == {"home": False, "away": False}
    alice.post(f"/seasons/matches/{match['id']}/auto")
    done = bob.post(f"/seasons/matches/{match['id']}/auto").json()["my_match"]
    assert done["status"] == "COMPLETED" and done["played_mode"] == "AUTO"


def test_hide_player_data_between_managers(alice, bob, default_team_ids):
    season = alice.post("/seasons", {"name": "Hidden", "rules": {"timers_enabled": False, "hide_player_data": True},
                                     "options": {"team_count": 4, "human_slots": 2}}).json()
    alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]})
    alice.post(f"/seasons/{season['id']}/start")
    _, match = head_to_head(alice, bob, season)
    gid = alice.post(f"/seasons/matches/{match['id']}/play").json()["game_id"]
    state = alice.get(f"/games/{gid}/state").json()
    assert state["settings"]["hide_player_data"] is True


def test_the_creator_can_leave_their_own_team(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    mine = alice.get(f"/seasons/{season['id']}").json()["my_team_id"]
    view = alice.post(f"/seasons/{season['id']}/teams/{mine}/release").json()
    # the creator still runs the season; the CPU runs the team
    assert view["my_team_id"] is None and view["can_advance"]
    assert next(t for t in view["teams"] if t["id"] == mine)["is_cpu"]
    assert alice.post(f"/seasons/{season['id']}/teams/{mine}/release").status_code == 409


def test_the_cpu_takes_over_a_live_game(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    _, match = head_to_head(alice, bob, season)
    gid = alice.post(f"/seasons/matches/{match['id']}/play").json()["game_id"]
    bob_team = bob.get(f"/seasons/{season['id']}").json()["my_team_id"]
    assert bob.post(f"/seasons/{season['id']}/teams/{bob_team}/release").status_code == 200
    assert bob.get(f"/seasons/{season['id']}").status_code == 404            # Bob has left the season
    view = alice.get(f"/seasons/{season['id']}").json()
    assert next(t for t in view["teams"] if t["id"] == bob_team)["is_cpu"]
    # the game Alice was waiting in carries on against the CPU
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "DRAFTING" and state["settings"]["mode"] == "CPU"
    play_my_turns(alice, gid, state["you"]["team"])
    assert alice.post(f"/games/{gid}/lineup/ready").status_code == 200
    assert alice.get(f"/seasons/{season['id']}").json()["my_match"]["status"] == "COMPLETED"


def test_the_cpu_takes_over_mid_draft(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    view, match = head_to_head(alice, bob, season)
    gid = alice.post(f"/seasons/matches/{match['id']}/play").json()["game_id"]
    bob.post(f"/seasons/matches/{match['id']}/play")
    users = {"BLUE": alice if match["home"]["is_you"] else bob}
    users["RED"] = bob if users["BLUE"] is alice else alice
    draft = alice.get(f"/games/{gid}/draft").json()
    first = users[draft["current_team"]]
    kind = "pick" if draft["action_type"] == "PICK" else "ban"
    assert first.post(f"/games/{gid}/draft/{kind}", {"champion_id": free_champion(draft)}).status_code == 200
    bob_team = bob.get(f"/seasons/{season['id']}").json()["my_team_id"]
    bob.post(f"/seasons/{season['id']}/teams/{bob_team}/release")
    me = "BLUE" if users["BLUE"] is alice else "RED"
    let_cpu_think(gid)
    play_my_turns(alice, gid, me)
    assert alice.post(f"/games/{gid}/lineup/ready").status_code == 200
    assert alice.get(f"/games/{gid}/state").json()["status"] == "COMPLETED"


def test_the_creator_can_remove_a_manager(alice, bob, default_team_ids):
    season = two_managers(alice, bob, default_team_ids)
    bob_team = bob.get(f"/seasons/{season['id']}").json()["my_team_id"]
    alice_team_id = alice.get(f"/seasons/{season['id']}").json()["my_team_id"]
    # another manager can't remove you
    assert bob.post(f"/seasons/{season['id']}/teams/{alice_team_id}/release").status_code == 403
    view = alice.post(f"/seasons/{season['id']}/teams/{bob_team}/release").json()
    assert view["managers"] == 1 and len(view["teams"]) == 1          # before the start the entry is withdrawn
    assert bob.get(f"/seasons/{season['id']}").status_code == 404


def test_round_deadline_closes_the_round(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids, round_deadline_hours=12)
    assert season["round_deadline_at"] is not None
    with SessionLocal() as db:
        assert season_service.process_deadlines(db, utcnow() + timedelta(hours=11)) == []
    with SessionLocal() as db:
        events = season_service.process_deadlines(db, utcnow() + timedelta(hours=13))
    assert any(e.get("type") == "SEASON_UPDATED" for e in events)
    view = alice.get(f"/seasons/{season['id']}").json()
    assert view["current_round"] == 2 and view["round_deadline_at"] is not None
    schedule = alice.get(f"/seasons/{season['id']}/schedule").json()
    assert all(m["status"] == "COMPLETED" for m in schedule["rounds"][0]["matches"])


def test_a_deadline_waits_a_little_for_a_draft_in_progress(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids, round_deadline_hours=1)
    match = alice.get(f"/seasons/{season['id']}").json()["my_match"]
    alice.post(f"/seasons/matches/{match['id']}/play")                  # a live game (vs the CPU or Bob)
    bob_match = bob.get(f"/seasons/{season['id']}").json()["my_match"]
    bob.post(f"/seasons/matches/{bob_match['id']}/play")
    with SessionLocal() as db:
        season_service.process_deadlines(db, utcnow() + timedelta(hours=1, minutes=5))
    assert alice.get(f"/seasons/{season['id']}").json()["current_round"] == 1
    with SessionLocal() as db:
        season_service.process_deadlines(db, utcnow() + timedelta(hours=2))
    assert alice.get(f"/seasons/{season['id']}").json()["current_round"] == 2


def test_no_deadline_by_default(alice, bob, default_team_ids):
    season = started(alice, bob, default_team_ids)
    assert season["round_deadline_at"] is None
    with SessionLocal() as db:
        assert season_service.process_deadlines(db, utcnow() + timedelta(days=30)) == []


def test_season_socket(client, alice, bob, default_team_ids):
    season = create(alice, human_slots=2)
    alice.post(f"/seasons/{season['id']}/teams", {"team_id": default_team_ids[0]})
    with client.websocket_connect(f"/ws/seasons/{season['id']}?token={alice.token}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        bob.post(f"/seasons/join/{season['code']}", {"team_id": default_team_ids[1]})
        event = ws.receive_json()
        assert event == {"type": "SEASON_UPDATED", "season_id": season["id"]}
    from tests.conftest import Api
    carol = Api(client, "carol")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/seasons/{season['id']}?token={carol.token}") as ws:
            ws.receive_json()

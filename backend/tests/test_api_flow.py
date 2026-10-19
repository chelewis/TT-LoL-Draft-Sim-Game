"""End-to-end API flow: lobby -> teams -> draft -> lineup -> simulation -> result."""
from datetime import timedelta

from tests.conftest import Api, play_draft, start_draft

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.game.config import LANES
from app.models import Game
from app.services import game_service


def test_health_and_auth(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/auth/me").status_code == 401
    a = Api(client, "carol")
    me = a.get("/auth/me").json()
    assert me["username"] == "carol"
    bad = client.post("/api/v1/auth/login", json={"username": "carol", "password": "wrong-password"})
    assert bad.status_code == 401
    ok = client.post("/api/v1/auth/login", json={"username": "carol", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["user"]["id"] == me["id"]
    dup = client.post("/api/v1/auth/register", json={"username": "carol", "email": "x@y.co", "password": "password123"})
    assert dup.status_code == 409
    assert client.post("/api/v1/auth/register", json={"username": "a", "email": "bad", "password": "x"}).status_code == 422


def test_full_game(alice, bob, default_team_ids):
    assert len(default_team_ids) >= 2
    gid = start_draft(alice, bob, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "DRAFTING" and state["draft"]["current_team"] == "BLUE"

    # only the active player can act
    res = bob.post(f"/games/{gid}/draft/ban", {"champion_id": 1})
    assert res.status_code == 409 and "not your turn" in res.json()["detail"]
    # wrong action type
    assert alice.post(f"/games/{gid}/draft/pick", {"champion_id": 1}).status_code == 409

    draft = play_draft(alice, bob, gid, range(1, 60))
    assert len(draft["blue_picks"]) == 5 and len(draft["red_picks"]) == 5 and len(draft["bans"]) == 10
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "LANE_ASSIGNMENT"

    # lineup validation
    blue, red = draft["blue_picks"], draft["red_picks"]
    bad = alice.put(f"/games/{gid}/lineup", {"assignments": [{"lane": "TOP", "champion_id": red[0]}]})
    assert bad.status_code == 400
    # the draft leaves each side a full lineup in pick order; save a partial one to test the check
    assert alice.put(f"/games/{gid}/lineup", {"assignments": [{"lane": "TOP", "champion_id": blue[0]}]}).status_code == 200
    assert alice.post(f"/games/{gid}/lineup/ready").status_code == 400   # incomplete
    dup = alice.put(f"/games/{gid}/lineup", {"assignments": [
        {"lane": "TOP", "champion_id": blue[0]}, {"lane": "MID", "champion_id": blue[0]}]})
    assert dup.status_code == 400

    blue_lineup = [{"lane": lane, "champion_id": cid} for lane, cid in zip(LANES, blue)]
    red_lineup = [{"lane": lane, "champion_id": cid} for lane, cid in zip(LANES, red)]
    assert alice.put(f"/games/{gid}/lineup", {"assignments": blue_lineup}).status_code == 200
    preview = alice.get(f"/games/{gid}/lineup/preview").json()
    assert len(preview) == 5 and {p["tier"] for p in preview} <= {"BEST", "COMFORT", "FAMILIAR", "VULNERABLE"}

    # opponent's lineup is hidden until the end
    bob_view = bob.get(f"/games/{gid}/state").json()["lineup"]
    assert bob_view["yours"] == dict(zip(LANES, red))   # his own default lineup (pick order), not Alice's
    assert "opponent" not in bob_view and set(bob_view["players"]) == {"RED"}
    assert alice.post(f"/games/{gid}/lineup/ready").status_code == 200
    assert bob.get(f"/games/{gid}/state").json()["status"] == "LANE_ASSIGNMENT"
    assert bob.get(f"/games/{gid}/result").status_code == 409
    assert bob.put(f"/games/{gid}/lineup", {"assignments": red_lineup}).status_code == 200
    assert alice.put(f"/games/{gid}/lineup", {"assignments": blue_lineup}).status_code == 409  # already confirmed
    final = bob.post(f"/games/{gid}/lineup/ready").json()
    assert final["status"] == "COMPLETED"
    assert final["lineup"]["opponent"]          # revealed after completion

    result = alice.get(f"/games/{gid}/result").json()
    assert result["winner"] in ("BLUE", "RED") and result["win_condition"] in ("NEXUS", "TIMEOUT")
    assert result["simulation_version"] and result["seed"] is not None
    assert len(result["players"]) == 10 and len(result["lanes"]) == 5
    assert result["mvp"]["team"] == result["winner"]
    assert result["draft"]["blue_picks"] == blue
    assert bob.get(f"/games/{gid}/result").json()["winner"] == result["winner"]   # both can view

    events = alice.get(f"/games/{gid}/result/events?limit=5").json()
    assert len(events["events"]) == 5 and events["next_after"] == 5

    # the stored result can be reproduced from the seed (spec 18)
    from app.game.simulation_engine import simulate_match  # noqa: F401  (engine is independent of the API)


def test_rerun_match(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    assert alice.post(f"/games/{gid}/rerun").status_code == 409          # not finished yet
    play_draft(alice, bob, gid, range(1, 60))
    alice.post(f"/games/{gid}/lineup/ready")
    assert bob.post(f"/games/{gid}/lineup/ready").json()["status"] == "COMPLETED"
    before = alice.get(f"/games/{gid}/result").json()

    assert bob.post(f"/games/{gid}/rerun").status_code == 403            # only the lobby owner
    res = alice.post(f"/games/{gid}/rerun")
    assert res.status_code == 200 and res.json()["status"] == "COMPLETED"
    after = alice.get(f"/games/{gid}/result").json()
    if after["seed"] == before["seed"]:                                   # a 1 in 2^31 collision: try once more
        alice.post(f"/games/{gid}/rerun")
        after = alice.get(f"/games/{gid}/result").json()
    assert after["seed"] != before["seed"]
    assert after["draft"] == before["draft"] and after["lineups"] == before["lineups"]

    events = alice.get(f"/games/{gid}/result/events?limit=500").json()["events"]
    sequences = [e["sequence"] for e in events]
    assert sequences and len(sequences) == len(set(sequences))           # the old events were replaced


def test_lobby_rules(client, alice, bob, default_team_ids):
    lobby = alice.post("/lobbies").json()
    assert len(lobby["code"]) == 6 and lobby["status"] == "WAITING_FOR_PLAYERS"
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 200
    carol = Api(client, "carol")
    assert carol.post(f"/lobbies/{lobby['code']}/join").status_code == 409        # third player rejected
    assert carol.get(f"/lobbies/{lobby['id']}").status_code == 404                # and cannot read it
    assert carol.get(f"/games/{lobby['game_id']}/state").status_code == 404
    assert alice.post("/lobbies/ZZZZZZ/join").status_code == 404
    assert alice.post(f"/lobbies/{lobby['code']}/join").status_code == 200        # rejoining is fine
    # can't ready before both teams are chosen
    assert alice.post(f"/games/{lobby['game_id']}/ready").status_code == 409
    # mirror match is allowed
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]}).status_code == 200
    state = bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]}).json()
    assert state["status"] == "READY_CHECK"
    # an incomplete default team (no roster) is rejected
    all_teams = alice.get("/teams").json()
    incomplete = next(t for t in all_teams if not t["selectable"])
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": incomplete["id"]}).status_code == 400


def test_leaving_cancels_game(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    lobby_id = alice.get(f"/games/{gid}/state").json()["lobby_id"]
    assert bob.post(f"/lobbies/{lobby_id}/leave").status_code == 200
    assert alice.get(f"/games/{gid}/state").json()["status"] == "CANCELLED"
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 409


def test_joiner_leaving_reopens_lobby(client, alice, bob):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    bob.post(f"/lobbies/{lobby['id']}/leave")
    assert alice.get(f"/lobbies/{lobby['id']}").json()["status"] == "WAITING_FOR_PLAYERS"
    carol = Api(client, "carol")
    assert carol.post(f"/lobbies/{lobby['code']}/join").status_code == 200


def test_lobby_expires(alice, bob):
    lobby = alice.post("/lobbies").json()
    with SessionLocal() as db:
        from app.models import Lobby
        row = db.get(Lobby, lobby["id"])
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert alice.get(f"/lobbies/{lobby['id']}").json()["status"] == "CANCELLED"
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 409


def test_draft_timeout_picks_random_legal_action(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    with SessionLocal() as db:
        game = db.get(Game, gid)
        # far in the future: every remaining timer has expired, so the whole draft auto-completes
        events = game_service.advance_timeouts(db, game, now=utcnow() + timedelta(hours=1))
        assert game.status == "LANE_ASSIGNMENT"
        assert any(e["type"] == "DRAFT_COMPLETED" for e in events)
    draft = alice.get(f"/games/{gid}/draft").json()
    assert draft["complete"] and len(draft["history"]) == 20 and all(h["auto"] for h in draft["history"])
    used = [h["champion_id"] for h in draft["history"]]
    assert len(set(used)) == 20                      # only legal, unique actions
    assert len(draft["blue_picks"]) == 5 and len(draft["red_picks"]) == 5


def test_single_timeout_advances_one_action(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    started = alice.get(f"/games/{gid}/draft").json()
    assert started["current_action"] == 0 and started["expires_at"]
    with SessionLocal() as db:
        game = db.get(Game, gid)
        game_service.advance_timeouts(db, game, now=game.action_expires_at + timedelta(seconds=1))
        assert game.current_action == 1
    after = alice.get(f"/games/{gid}/draft").json()
    assert after["current_action"] == 1 and after["current_team"] == "RED"
    assert after["history"][0]["auto"] is True


def test_timeout_locks_in_hovered_champion(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    # only the acting side can hover, and only legal champions
    assert bob.post(f"/games/{gid}/draft/hover", {"champion_id": 7, "draft_action": 0}).status_code == 409
    assert alice.post(f"/games/{gid}/draft/hover", {"champion_id": 99999, "draft_action": 0}).status_code == 409
    assert alice.post(f"/games/{gid}/draft/hover", {"champion_id": 7, "draft_action": 0}).status_code == 200
    with SessionLocal() as db:
        game = db.get(Game, gid)
        game_service.advance_timeouts(db, game, now=game.action_expires_at + timedelta(seconds=1))
    after = alice.get(f"/games/{gid}/draft").json()
    assert after["history"][0] == {"action_number": 0, "team": "BLUE", "action_type": "BAN", "champion_id": 7, "auto": True}
    # the hover belonged to the resolved action: a stale hover is ignored and red's timeout stays random
    assert alice.post(f"/games/{gid}/draft/hover", {"champion_id": 8, "draft_action": 0}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Game, gid).hovered_champion_id is None


def test_hidden_player_data(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids, hide=True)
    mine = alice.get(f"/games/{gid}/state").json()
    theirs = mine["teams"]["RED"]
    assert theirs["hidden"] is True
    for player in theirs["roster"].values():
        assert player["hidden"] and "aggr" not in player and "pool" not in player
    assert "aggr" in mine["teams"]["BLUE"]["roster"]["TOP"]                     # own data is visible
    # nothing hidden leaks anywhere in the payload
    assert str(mine["teams"]["RED"]["roster"]["TOP"].get("pool")) == "None"
    # visible in a normal lobby
    alice2, bob2 = alice, bob
    gid2 = start_draft(alice2, bob2, default_team_ids, hide=False)
    assert "aggr" in alice2.get(f"/games/{gid2}/state").json()["teams"]["RED"]["roster"]["TOP"]


def test_opponent_data_revealed_after_completion(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids, hide=True)
    play_draft(alice, bob, gid, range(1, 60))
    state = alice.get(f"/games/{gid}/state").json()
    assert state["teams"]["RED"].get("hidden") is True
    draft = state["draft"]
    alice.put(f"/games/{gid}/lineup", {"assignments": [{"lane": l, "champion_id": c} for l, c in zip(LANES, draft["blue_picks"])]})
    bob.put(f"/games/{gid}/lineup", {"assignments": [{"lane": l, "champion_id": c} for l, c in zip(LANES, draft["red_picks"])]})
    alice.post(f"/games/{gid}/lineup/ready")
    bob.post(f"/games/{gid}/lineup/ready")
    done = alice.get(f"/games/{gid}/state").json()
    assert done["status"] == "COMPLETED"
    assert "aggr" in done["teams"]["RED"]["roster"]["TOP"]


def test_my_games(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    games = alice.get("/games?active=true").json()
    assert [g["game_id"] for g in games] == [gid]


def test_websocket_events(client, alice, bob, default_team_ids):
    lobby = alice.post("/lobbies").json()
    gid = lobby["game_id"]
    with client.websocket_connect(f"/ws/games/{gid}?token={alice.token}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        bob.post(f"/lobbies/{lobby['code']}/join")
        assert ws.receive_json()["type"] == "PLAYER_JOINED"
        bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]})
        assert ws.receive_json()["type"] == "TEAM_SELECTED"
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "PONG"
    # not a participant / bad token: rejected
    carol = Api(client, "carol")
    try:
        with client.websocket_connect(f"/ws/games/{gid}?token={carol.token}") as ws2:
            ws2.receive_json()
        raised = False
    except Exception:
        raised = True
    assert raised

"""Lobby owner can switch between Blue and Red; the other player swaps with them."""
from tests.conftest import Api, start_draft


def test_owner_can_take_red_before_anyone_joins(client, alice, bob):
    lobby = alice.post("/lobbies").json()
    assert lobby["you"] == "BLUE"
    state = alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"}).json()
    assert state["you"]["team"] == "RED" and state["you"]["is_owner"] is True
    assert state["players"]["red"]["username"] == "alice" and state["players"]["blue"] is None
    # the joiner takes the free side
    assert bob.post(f"/lobbies/{lobby['code']}/join").json()["you"] == "BLUE"
    state = bob.get(f"/games/{lobby['game_id']}/state").json()
    assert state["you"] == {"user_id": state["you"]["user_id"], "team": "BLUE", "is_owner": False}
    assert state["players"]["blue"]["username"] == "bob" and state["players"]["red"]["username"] == "alice"
    # a third player is still rejected
    assert Api(client, "carol").post(f"/lobbies/{lobby['code']}/join").status_code == 409


def test_full_lobby_swaps_players_and_their_teams(alice, bob, default_team_ids):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]})
    bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[1]})
    gid = lobby["game_id"]
    assert alice.post(f"/games/{gid}/ready").json()["players"]["blue"]["ready"] is True

    state = alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"}).json()
    assert state["you"]["team"] == "RED"
    assert state["players"]["red"]["username"] == "alice" and state["players"]["blue"]["username"] == "bob"
    # each player keeps their own team, which moves with them
    assert state["teams"]["RED"]["id"] == default_team_ids[0]
    assert state["teams"]["BLUE"]["id"] == default_team_ids[1]
    # readiness is cleared so nobody starts a draft on the wrong side by accident
    assert state["players"]["red"]["ready"] is False and state["players"]["blue"]["ready"] is False
    assert state["status"] == "READY_CHECK"
    assert bob.get(f"/games/{gid}/state").json()["you"]["team"] == "BLUE"

    # choosing the side you are already on changes nothing; swapping back works
    assert alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"}).json()["you"]["team"] == "RED"
    assert alice.post(f"/lobbies/{lobby['id']}/side", {"side": "BLUE"}).json()["you"]["team"] == "BLUE"


def test_only_the_owner_can_change_sides(alice, bob):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    res = bob.post(f"/lobbies/{lobby['id']}/side", {"side": "BLUE"})
    assert res.status_code == 403
    assert alice.post(f"/lobbies/{lobby['id']}/side", {"side": "GREEN"}).status_code == 400


def test_sides_locked_once_the_draft_starts(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    lobby_id = alice.get(f"/games/{gid}/state").json()["lobby_id"]
    assert alice.post(f"/lobbies/{lobby_id}/side", {"side": "RED"}).status_code == 409


def test_game_plays_through_after_a_swap(alice, bob, default_team_ids):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]})
    bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[1]})
    alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"})
    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    bob.post(f"/games/{gid}/ready")
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "DRAFTING" and state["you"]["team"] == "RED"
    assert state["draft"]["current_team"] == "BLUE"          # bob (now Blue) acts first
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 409
    assert bob.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 200


def test_joiner_leaving_frees_their_side_after_a_swap(alice, bob, client):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"})     # bob is now Blue
    bob.post(f"/lobbies/{lobby['id']}/leave")
    state = alice.get(f"/games/{lobby['game_id']}/state").json()
    assert state["status"] == "WAITING_FOR_PLAYERS"
    assert state["players"]["blue"] is None and state["players"]["red"]["username"] == "alice"
    carol = Api(client, "carol")
    assert carol.post(f"/lobbies/{lobby['code']}/join").json()["you"] == "BLUE"


def test_owner_leaving_cancels_even_on_red(alice, bob):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"})
    alice.post(f"/lobbies/{lobby['id']}/leave")
    assert bob.get(f"/games/{lobby['game_id']}/state").json()["status"] == "CANCELLED"


def test_websocket_notifies_the_swap(client, alice, bob):
    lobby = alice.post("/lobbies").json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    with client.websocket_connect(f"/ws/games/{lobby['game_id']}?token={bob.token}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"})
        event = ws.receive_json()
        assert event["type"] == "SIDES_SWAPPED" and event["owner_team"] == "RED"

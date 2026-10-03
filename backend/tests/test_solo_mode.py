"""Single player: one user holds both seats and decides everything for both sides."""
from datetime import timedelta

from tests.conftest import Api

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.game.config import LANES
from app.models import Game
from app.services import game_service


def solo(alice, **settings):
    res = alice.post("/lobbies", {"mode": "SOLO", "settings": settings})
    assert res.status_code == 201, res.text
    return res.json()


def choose(alice, lobby, blue, red):
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": blue, "side": "BLUE"}).status_code == 200
    return alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": red, "side": "RED"})


def draft_all(alice, gid, ids=range(1, 80)):
    """The one user plays every step, acting for whichever side is up."""
    ids = iter(ids)
    while True:
        d = alice.get(f"/games/{gid}/draft").json()
        if d["complete"]:
            return d
        kind = "pick" if d["action_type"] == "PICK" else "ban"
        res = alice.post(f"/games/{gid}/draft/{kind}", {"champion_id": next(ids)})
        assert res.status_code == 200, res.text


def test_solo_lobby_starts_in_team_selection_with_one_user_on_both_sides(alice):
    lobby = solo(alice)
    assert lobby["settings"]["mode"] == "SOLO" and lobby["status"] == "TEAM_SELECTION"
    state = alice.get(f"/games/{lobby['game_id']}/state").json()
    assert state["settings"]["mode"] == "SOLO"
    assert state["players"]["blue"]["id"] == state["players"]["red"]["id"] == state["you"]["user_id"]


def test_hide_player_data_is_ignored_in_solo(alice):
    lobby = solo(alice, hide_player_data=True)
    assert lobby["settings"]["hide_player_data"] is False


def test_full_solo_game_from_team_choice_to_result(alice, default_team_ids):
    lobby = solo(alice)
    gid = lobby["game_id"]
    # a mirror match is fine: the same default team on both sides
    state = choose(alice, lobby, default_team_ids[0], default_team_ids[0]).json()
    assert state["status"] == "READY_CHECK"
    assert state["teams"]["BLUE"]["id"] == state["teams"]["RED"]["id"] == default_team_ids[0]

    started = alice.post(f"/games/{gid}/ready").json()
    assert started["status"] == "DRAFTING" and started["draft"]["current_team"] == "BLUE"

    # the usual validation still applies
    assert alice.post(f"/games/{gid}/draft/pick", {"champion_id": 1}).status_code == 409        # a ban is due
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 200
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 409        # already banned
    assert alice.get(f"/games/{gid}/draft").json()["current_team"] == "RED"                    # turn passed to Red

    draft = draft_all(alice, gid, range(2, 80))
    assert len(draft["blue_picks"]) == 5 and len(draft["red_picks"]) == 5 and len(draft["bans"]) == 10
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "LANE_ASSIGNMENT"

    # lineups need a side
    lineup = lambda picks: [{"lane": l, "champion_id": c} for l, c in zip(LANES, picks)]  # noqa: E731
    assert alice.put(f"/games/{gid}/lineup", {"assignments": lineup(draft["blue_picks"])}).status_code == 400
    assert alice.post(f"/games/{gid}/lineup/ready").status_code == 400
    # a side can only use its own picks
    wrong = alice.put(f"/games/{gid}/lineup", {"side": "BLUE", "assignments": lineup(draft["red_picks"])})
    assert wrong.status_code == 400

    assert alice.put(f"/games/{gid}/lineup", {"side": "BLUE", "assignments": lineup(draft["blue_picks"])}).status_code == 200
    assert alice.put(f"/games/{gid}/lineup", {"side": "RED", "assignments": lineup(draft["red_picks"])}).status_code == 200
    state = alice.get(f"/games/{gid}/state").json()
    assert set(state["lineup"]["blue"]) == set(LANES) and set(state["lineup"]["red"]) == set(LANES)
    assert len(alice.get(f"/games/{gid}/lineup/preview?side=RED").json()) == 5
    assert alice.get(f"/games/{gid}/lineup/preview").status_code == 400

    # the match runs once both sides are confirmed
    mid = alice.post(f"/games/{gid}/lineup/ready?side=BLUE").json()
    assert mid["status"] == "LANE_ASSIGNMENT" and mid["players"]["blue"]["lineup_ready"] is True
    assert alice.put(f"/games/{gid}/lineup", {"side": "BLUE", "assignments": lineup(draft["blue_picks"])}).status_code == 409
    final = alice.post(f"/games/{gid}/lineup/ready?side=RED").json()
    assert final["status"] == "COMPLETED"

    result = alice.get(f"/games/{gid}/result").json()
    assert result["winner"] in ("BLUE", "RED") and len(result["players"]) == 10
    assert result["draft"]["blue_picks"] == draft["blue_picks"]


def test_different_teams_for_each_side(alice, default_team_ids):
    lobby = solo(alice)
    state = choose(alice, lobby, default_team_ids[0], default_team_ids[1]).json()
    assert state["teams"]["BLUE"]["id"] == default_team_ids[0] and state["teams"]["RED"]["id"] == default_team_ids[1]


def test_team_choice_needs_a_side_and_a_valid_team(alice, default_team_ids):
    lobby = solo(alice)
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]}).status_code == 400
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0], "side": "GREEN"}).status_code == 400
    incomplete = next(t for t in alice.get("/teams").json() if not t["selectable"])
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": incomplete["id"], "side": "BLUE"}).status_code == 400


def test_cannot_start_until_both_teams_are_chosen(alice, default_team_ids):
    lobby = solo(alice)
    assert alice.post(f"/games/{lobby['game_id']}/ready").status_code == 409
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0], "side": "BLUE"})
    assert alice.post(f"/games/{lobby['game_id']}/ready").status_code == 409


def test_nobody_else_can_join_read_or_act(client, alice, default_team_ids):
    lobby = solo(alice)
    bob = Api(client, "bob")
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 409
    assert bob.get(f"/games/{lobby['game_id']}/state").status_code == 404
    assert bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0], "side": "RED"}).status_code == 404
    assert alice.post(f"/lobbies/{lobby['code']}/join").status_code == 200       # the owner rejoining is harmless


def test_sides_cannot_be_swapped_in_solo(alice):
    lobby = solo(alice)
    assert alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"}).status_code == 409


def test_leaving_cancels_the_solo_game(alice):
    lobby = solo(alice)
    alice.post(f"/lobbies/{lobby['id']}/leave")
    assert alice.get(f"/games/{lobby['game_id']}/state").json()["status"] == "CANCELLED"


def test_draft_options_work_in_solo(alice, default_team_ids):
    lobby = solo(alice, bans_enabled=False, timers_enabled=False)
    choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    draft = alice.get(f"/games/{gid}/draft").json()
    assert len(draft["actions"]) == 10 and draft["expires_at"] is None
    done = draft_all(alice, gid)
    assert done["bans"] == []


def test_solo_timer_still_auto_plays_expired_actions(alice, default_team_ids):
    lobby = solo(alice, timers_enabled=True, pick_seconds=5, ban_seconds=5)
    choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    with SessionLocal() as db:
        game = db.get(Game, gid)
        game_service.advance_timeouts(db, game, now=utcnow() + timedelta(hours=1))
        assert game.status == "LANE_ASSIGNMENT"


def test_solo_games_appear_in_my_games_once(alice):
    lobby = solo(alice)
    games = alice.get("/games").json()
    assert [g["game_id"] for g in games] == [lobby["game_id"]] and games[0]["settings"]["mode"] == "SOLO"


def test_multiplayer_is_unchanged(alice, bob, default_team_ids):
    lobby = alice.post("/lobbies").json()
    assert lobby["settings"]["mode"] == "MULTI" and lobby["status"] == "WAITING_FOR_PLAYERS"
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 200
    # a multiplayer player cannot name a side to act for the other seat
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0], "side": "RED"})
    state = alice.get(f"/games/{lobby['game_id']}/state").json()
    assert state["teams"]["BLUE"]["id"] == default_team_ids[0] and state["teams"]["RED"] is None

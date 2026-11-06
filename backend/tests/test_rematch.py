"""Rematch: once both sides click Rematch, a new lobby opens with the same settings, players, teams and sides."""
from app.core.database import SessionLocal
from app.models import Game
from tests.test_cpu_mode import play_my_turns, started as cpu_started
from tests.test_series import advance, champion_ids, create, play_game


def finished(alice, bob, team_ids, **settings):
    """A multiplayer best of one played to the end. Returns the final state."""
    _, gid = create(alice, bob, team_ids, **settings)
    return play_game({alice.user["id"]: alice, bob.user["id"]: bob}, gid, champion_ids(alice))


def test_both_players_must_click_rematch(alice, bob, default_team_ids):
    res = alice.post("/lobbies", {"settings": {"bans_enabled": False, "pick_seconds": 45, "hide_player_data": True}})
    lobby = res.json()
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 200
    gid = lobby["game_id"]
    assert alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"}).status_code == 200    # owner plays Red
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0]})
    bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[1]})
    assert alice.post(f"/games/{gid}/rematch").status_code == 409            # not finished yet
    alice.post(f"/games/{gid}/ready")
    bob.post(f"/games/{gid}/ready")
    state = play_game({alice.user["id"]: alice, bob.user["id"]: bob}, gid, champion_ids(alice))
    assert state["status"] == "COMPLETED"
    assert state["rematch"] == {"available": True, "ready": {"blue": False, "red": False}, "game_id": None}

    # alice (Red) clicks, changes her mind, clicks again: nothing starts until bob clicks too
    assert alice.post(f"/games/{gid}/rematch").json()["rematch"]["ready"] == {"blue": False, "red": True}
    assert alice.post(f"/games/{gid}/rematch", {"ready": False}).json()["rematch"]["ready"]["red"] is False
    assert alice.post(f"/games/{gid}/rematch").json()["rematch"]["game_id"] is None
    after = bob.post(f"/games/{gid}/rematch").json()["rematch"]
    new_id = after["game_id"]
    assert new_id and after["ready"] == {"blue": True, "red": True}
    assert alice.get(f"/games/{gid}/state").json()["rematch"]["game_id"] == new_id
    assert bob.post(f"/games/{gid}/rematch").status_code == 409              # already started

    new = alice.get(f"/games/{new_id}/state").json()
    assert new["status"] == "READY_CHECK" and new["lobby_code"] != state["lobby_code"]
    assert new["players"]["red"]["id"] == alice.user["id"] and new["players"]["blue"]["id"] == bob.user["id"]
    assert new["players"]["red"]["team_id"] == default_team_ids[0]
    assert new["players"]["blue"]["team_id"] == default_team_ids[1]
    assert not new["players"]["red"]["ready"] and not new["players"]["blue"]["ready"]
    assert new["you"]["is_owner"] is True and new["rematch"] is None
    assert new["settings"] == state["settings"]
    assert new["settings"]["bans_enabled"] is False and new["settings"]["pick_seconds"] == 45

    alice.post(f"/games/{new_id}/ready")
    assert bob.post(f"/games/{new_id}/ready").json()["status"] == "DRAFTING"


def test_rematch_after_a_series(alice, bob, default_team_ids):
    lobby, gid = create(alice, bob, default_team_ids, series_format="BO3")
    players = {alice.user["id"]: alice, bob.user["id"]: bob}
    ids = champion_ids(alice)
    state = play_game(players, gid, ids)
    assert state["rematch"]["available"] is False
    assert alice.post(f"/games/{gid}/rematch").status_code == 409            # the series isn't over
    # the loser always swaps, so later games are played on the other sides
    while not state["series"]["complete"]:
        gid = advance(players, state, "RED" if state["series"]["loser_side"] == "BLUE" else "BLUE")
        state = play_game(players, gid, ids)
    assert state["rematch"]["available"] is True
    alice.post(f"/games/{gid}/rematch")
    new_id = bob.post(f"/games/{gid}/rematch").json()["rematch"]["game_id"]
    new = alice.get(f"/games/{new_id}/state").json()
    # a fresh series, with the players and teams on the sides chosen in the first lobby
    assert new["series"]["id"] != lobby["series"]["id"] and new["series"]["game_number"] == 1
    assert new["series"]["format"] == "BO3"
    assert new["players"]["blue"]["id"] == alice.user["id"] and new["players"]["blue"]["team_id"] == default_team_ids[0]
    assert new["players"]["red"]["id"] == bob.user["id"] and new["players"]["red"]["team_id"] == default_team_ids[1]


def test_solo_play_again_needs_one_click(alice, default_team_ids):
    lobby = alice.post("/lobbies", {"mode": "SOLO"}).json()
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0], "side": "BLUE"})
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[1], "side": "RED"})
    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    play_game({alice.user["id"]: alice}, gid, champion_ids(alice))
    new_id = alice.post(f"/games/{gid}/rematch").json()["rematch"]["game_id"]
    new = alice.get(f"/games/{new_id}/state").json()
    assert new["status"] == "READY_CHECK" and new["settings"]["mode"] == "SOLO"
    assert new["teams"]["BLUE"]["id"] == default_team_ids[0] and new["teams"]["RED"]["id"] == default_team_ids[1]


def test_cpu_play_again_needs_one_click(alice, default_team_ids):
    lobby, _ = cpu_started(alice, default_team_ids)
    gid = lobby["game_id"]
    play_my_turns(alice, gid, "BLUE")
    assert alice.post(f"/games/{gid}/lineup/ready").json()["status"] == "COMPLETED"
    new_id = alice.post(f"/games/{gid}/rematch").json()["rematch"]["game_id"]
    new = alice.get(f"/games/{new_id}/state").json()
    assert new["status"] == "READY_CHECK" and new["settings"]["mode"] == "CPU"
    assert new["players"]["red"]["bot"] is True and new["players"]["red"]["team_id"] == default_team_ids[1]


def test_a_team_that_is_gone_must_be_chosen_again(alice, bob, default_team_ids):
    state = finished(alice, bob, default_team_ids)
    gid = state["game_id"]
    with SessionLocal() as db:          # what deleting the team does to the finished game (ON DELETE SET NULL)
        db.get(Game, gid).red_team_id = None
        db.commit()
    alice.post(f"/games/{gid}/rematch")
    new_id = bob.post(f"/games/{gid}/rematch").json()["rematch"]["game_id"]
    new = alice.get(f"/games/{new_id}/state").json()
    assert new["status"] == "TEAM_SELECTION"
    assert new["players"]["blue"]["team_id"] == default_team_ids[0] and new["players"]["red"]["team_id"] is None

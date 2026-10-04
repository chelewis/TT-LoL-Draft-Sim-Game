"""After the draft each side starts in pick order; champions or positions are then swapped."""
from app.game.config import LANES
from tests.test_solo_mode import choose, draft_all, solo


def drafted_game(alice, default_team_ids):
    lobby = solo(alice)
    gid = lobby["game_id"]
    choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    alice.post(f"/games/{gid}/ready")
    return gid, draft_all(alice, gid, range(1, 80))


def roster_ids(state, side):
    return {lane: p["id"] for lane, p in state["teams"][side]["roster"].items()}


def test_draft_leaves_each_side_a_lineup_in_pick_order(alice, default_team_ids):
    gid, draft = drafted_game(alice, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "LANE_ASSIGNMENT"
    assert state["lineup"]["blue"] == dict(zip(LANES, draft["blue_picks"]))
    assert state["lineup"]["red"] == dict(zip(LANES, draft["red_picks"]))
    assert state["lineup"]["players"]["BLUE"] == roster_ids(state, "BLUE")
    # already complete, so it can be confirmed without changes
    assert alice.post(f"/games/{gid}/lineup/ready?side=BLUE").status_code == 200


def test_position_swap_moves_players_with_their_champions(alice, default_team_ids):
    gid, draft = drafted_game(alice, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    players = roster_ids(state, "BLUE")
    champs = dict(zip(LANES, draft["blue_picks"]))
    # top and mid trade places, each keeping their champion
    players["TOP"], players["MID"] = players["MID"], players["TOP"]
    champs["TOP"], champs["MID"] = champs["MID"], champs["TOP"]
    body = {"side": "BLUE", "assignments": [{"lane": l, "champion_id": champs[l], "player_id": players[l]} for l in LANES]}
    assert alice.put(f"/games/{gid}/lineup", body).status_code == 200

    state = alice.get(f"/games/{gid}/state").json()
    assert state["lineup"]["players"]["BLUE"] == players
    assert state["lineup"]["blue"] == champs
    preview = {p["lane"]: p["player_id"] for p in alice.get(f"/games/{gid}/lineup/preview?side=BLUE").json()}
    assert preview == players

    assert alice.post(f"/games/{gid}/lineup/ready?side=BLUE").status_code == 200
    final = alice.post(f"/games/{gid}/lineup/ready?side=RED").json()
    assert final["status"] == "COMPLETED"
    result = alice.get(f"/games/{gid}/result").json()
    played = {p["lane"]: p["player_id"] for p in result["players"] if p["team"] == "BLUE"}
    assert played == players


def test_champion_swap_keeps_players_in_their_lanes(alice, default_team_ids):
    gid, draft = drafted_game(alice, default_team_ids)
    champs = dict(zip(LANES, draft["red_picks"]))
    champs["BOT"], champs["SUPPORT"] = champs["SUPPORT"], champs["BOT"]
    body = {"side": "RED", "assignments": [{"lane": l, "champion_id": champs[l]} for l in LANES]}
    assert alice.put(f"/games/{gid}/lineup", body).status_code == 200
    state = alice.get(f"/games/{gid}/state").json()
    assert state["lineup"]["red"] == champs
    assert state["lineup"]["players"]["RED"] == roster_ids(state, "RED")


def test_position_swaps_must_use_each_roster_player_once(alice, default_team_ids):
    gid, draft = drafted_game(alice, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    players = roster_ids(state, "BLUE")
    champs = dict(zip(LANES, draft["blue_picks"]))

    def put(player_for):
        return alice.put(f"/games/{gid}/lineup", {"side": "BLUE", "assignments": [
            {"lane": l, "champion_id": champs[l], **({"player_id": player_for[l]} if l in player_for else {})} for l in LANES]})

    assert put({**players, "MID": players["TOP"]}).status_code == 400          # same player twice
    assert put({**players, "MID": 999_999}).status_code == 400                 # not on the roster
    assert put({"TOP": players["MID"], "MID": players["TOP"]}).status_code == 400  # some lanes missing a player
    assert put(players).status_code == 200

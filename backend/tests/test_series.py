"""Best-of series: games played one after another with the same teams, loser picks side, optional fearless draft."""
from tests.conftest import Api


def other(side):
    return "RED" if side == "BLUE" else "BLUE"


def create(owner, guest, team_ids, **settings):
    """A multiplayer lobby with both teams chosen and both players ready. Returns (lobby, game_id)."""
    res = owner.post("/lobbies", {"settings": settings})
    assert res.status_code == 201, res.text
    lobby = res.json()
    assert guest.post(f"/lobbies/{lobby['code']}/join").status_code == 200
    owner.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_ids[0]})
    guest.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_ids[1]})
    owner.post(f"/games/{lobby['game_id']}/ready")
    guest.post(f"/games/{lobby['game_id']}/ready")
    return lobby, lobby["game_id"]


def champion_ids(api):
    return sorted(c["id"] for c in api.get("/champions").json())


def sides(players, state):
    """side -> the Api of whoever plays it in this game (sides can change between games)."""
    return {"BLUE": players[state["players"]["blue"]["id"]], "RED": players[state["players"]["red"]["id"]]}


def play_game(players, gid, ids):
    """Draft with the first free champions (skipping fearless locks), then confirm both lineups.
    `players` maps user id -> Api."""
    api = next(iter(players.values()))
    state = api.get(f"/games/{gid}/state").json()
    solo = state["settings"]["mode"] == "SOLO"
    by_side = sides(players, state)
    while True:
        d = api.get(f"/games/{gid}/draft").json()
        if d["complete"]:
            break
        taken = set(d["fearless_locked"]) | set(d["blue_picks"]) | set(d["red_picks"]) | {b["champion_id"] for b in d["bans"]}
        cid = next(c for c in ids if c not in taken)
        kind = "pick" if d["action_type"] == "PICK" else "ban"
        res = by_side[d["current_team"]].post(f"/games/{gid}/draft/{kind}", {"champion_id": cid})
        assert res.status_code == 200, res.text
    for side in ("BLUE", "RED"):
        res = by_side[side].post(f"/games/{gid}/lineup/ready" + (f"?side={side}" if solo else ""))
        assert res.status_code == 200, res.text
    return api.get(f"/games/{gid}/state").json()


def advance(players, state, loser_takes):
    """Both players ready up after a completed game; the loser takes `loser_takes`. Returns the next game id."""
    gid, loser = state["game_id"], state["series"]["loser_side"]
    by_side = sides(players, state)
    assert by_side[other(loser)].post(f"/games/{gid}/series/ready").status_code == 200
    res = by_side[loser].post(f"/games/{gid}/series/ready", {"side": loser_takes})
    assert res.status_code == 200, res.text
    return res.json()["series"]["next_game_id"]


def test_best_of_one_has_no_series(alice, bob, default_team_ids):
    lobby, gid = create(alice, bob, default_team_ids, fearless=True)
    assert lobby["series"] is None and lobby["settings"]["series_format"] == "BO1"
    assert lobby["settings"]["fearless"] is False          # fearless means nothing in a single game
    assert alice.get(f"/games/{gid}/state").json()["series"] is None


def test_best_of_three_flow(alice, bob, default_team_ids):
    players = {alice.user["id"]: alice, bob.user["id"]: bob}
    ids = champion_ids(alice)
    lobby, gid = create(alice, bob, default_team_ids, series_format="BO3")
    series_id = lobby["series"]["id"]
    assert lobby["series"] == {"id": series_id, "format": "BO3", "fearless": False, "game_number": 1}

    state = play_game(players, gid, ids)
    s = state["series"]
    assert state["status"] == "COMPLETED" and s["game_number"] == 1 and sum(s["score"].values()) == 1
    assert not s["complete"] and s["next_game_id"] is None
    loser = s["loser_side"]
    winner_api, loser_api = sides(players, state)[other(loser)], sides(players, state)[loser]

    assert alice.post(f"/games/{gid}/rerun").status_code == 409          # no re-runs inside a series
    # the next game waits for both players
    after = winner_api.post(f"/games/{gid}/series/ready").json()["series"]
    assert after["next_game_id"] is None and after["next_ready"][other(loser).lower()] is True
    assert loser_api.post(f"/games/{gid}/series/ready").status_code == 400          # the loser must choose a side
    # the loser takes the other side, so everyone swaps
    res = loser_api.post(f"/games/{gid}/series/ready", {"side": other(loser)})
    assert res.status_code == 200, res.text
    gid2 = res.json()["series"]["next_game_id"]
    assert gid2 and loser_api.post(f"/games/{gid}/series/ready", {"side": loser}).status_code == 409

    g2 = alice.get(f"/games/{gid2}/state").json()
    assert g2["status"] == "DRAFTING" and g2["series"]["game_number"] == 2
    assert g2["players"]["blue"]["id"] == state["players"]["red"]["id"]
    assert g2["players"]["red"]["id"] == state["players"]["blue"]["id"]
    assert g2["teams"]["BLUE"]["id"] == state["teams"]["RED"]["id"]          # snapshots follow their team
    assert g2["series"]["score"] == {"BLUE": s["score"]["RED"], "RED": s["score"]["BLUE"]}
    assert g2["draft"]["fearless_locked"] == []                              # not a fearless series
    # match history marks every game of the series
    mine = {g["game_id"]: g for g in alice.get("/games").json()}
    assert mine[gid]["series"]["game_number"] == 1 and mine[gid2]["series"]["game_number"] == 2

    # play until someone has two wins
    current = gid2
    for _ in range(2):
        state = play_game(players, current, ids)
        if state["series"]["complete"]:
            break
        current = advance(players, state, state["series"]["loser_side"])     # the loser keeps their side
    s = state["series"]
    assert s["complete"] and max(s["score"].values()) == 2 and s["series_winner"] in ("BLUE", "RED")
    assert alice.post(f"/games/{current}/series/ready", {"side": "BLUE"}).status_code == 409

    result = bob.get(f"/series/{series_id}").json()
    assert result["format"] == "BO3" and result["complete"] and result["score"][result["winner"]] == 2
    numbers = [g["game_number"] for g in result["games"]]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) in (2, 3)
    for g in result["games"]:
        assert g["status"] == "COMPLETED" and g["winner"] in ("BLUE", "RED")
        assert len(g["draft"]["blue_picks"]) == 5 and g["mvp"]
    assert sum(1 for g in result["games"] if g["winner"] == result["winner"]) == 2


def test_fearless_locks_earlier_picks(alice, bob, default_team_ids):
    players = {alice.user["id"]: alice, bob.user["id"]: bob}
    _, gid = create(alice, bob, default_team_ids, series_format="BO5", fearless=True)
    state = play_game(players, gid, champion_ids(alice))
    picks1 = set(state["draft"]["blue_picks"]) | set(state["draft"]["red_picks"])
    bans1 = {b["champion_id"] for b in state["draft"]["bans"]}
    gid2 = advance(players, state, state["series"]["loser_side"])

    d = alice.get(f"/games/{gid2}/draft").json()
    assert set(d["fearless_locked"]) == picks1 and len(picks1) == 10
    blue = sides(players, alice.get(f"/games/{gid2}/state").json())["BLUE"]
    res = blue.post(f"/games/{gid2}/draft/ban", {"champion_id": min(picks1)})
    assert res.status_code == 409 and "Fearless" in res.json()["detail"]
    # bans reset each game: a champion banned in game 1 is free again
    assert blue.post(f"/games/{gid2}/draft/ban", {"champion_id": min(bans1)}).status_code == 200


def test_series_result_is_private(client, alice, bob, default_team_ids):
    lobby, _ = create(alice, bob, default_team_ids, series_format="BO3")
    carol = Api(client, "carol")
    assert carol.get(f"/series/{lobby['series']['id']}").status_code == 404
    assert alice.get("/series/99999").status_code == 404


def test_solo_series_one_ready_starts_next_game(alice, default_team_ids):
    lobby = alice.post("/lobbies", {"mode": "SOLO", "settings": {"series_format": "BO3", "fearless": True}}).json()
    gid = lobby["game_id"]
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[0], "side": "BLUE"})
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": default_team_ids[1], "side": "RED"})
    assert alice.post(f"/games/{gid}/ready").status_code == 200
    state = play_game({alice.user["id"]: alice}, gid, champion_ids(alice))
    assert alice.post(f"/games/{gid}/series/ready").status_code == 400     # choose the losing team's side
    loser = state["series"]["loser_side"]
    gid2 = alice.post(f"/games/{gid}/series/ready", {"side": other(loser)}).json()["series"]["next_game_id"]
    g2 = alice.get(f"/games/{gid2}/state").json()
    assert g2["status"] == "DRAFTING" and g2["series"]["fearless"]
    assert g2["teams"][other(loser)]["id"] == state["teams"][loser]["id"]   # the losing team switched sides

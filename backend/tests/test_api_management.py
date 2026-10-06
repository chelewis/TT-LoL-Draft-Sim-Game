"""Team / player / coach management rules (spec 5.6)."""
from tests.conftest import Api, play_draft, start_draft

from app.game.config import LANES

STATS = {"aggr": 6, "aware": 6, "pos": 6, "dmg": 6, "cs": 6}   # total 30, within the soft ceiling
POOL = [1, 2, 3, 4, 5]


def make_player(api, role="TOP", name="P", pool=None, **stats):
    body = {"name": name, "role": role, "age": 21, "region": "NA", **{**STATS, **stats}, "pool": pool or POOL}
    return api.post("/players", body)


def make_roster(api, prefix="R", **stats):
    ids = {}
    for i, lane in enumerate(LANES):
        res = make_player(api, lane, f"{prefix}{lane}", pool=[i * 5 + k + 1 for k in range(5)], **stats)
        assert res.status_code == 201, res.text
        ids[lane] = res.json()["id"]
    return ids


def make_coach(api, draft=5, synergy=5):
    res = api.post("/coaches", {"name": "Coach", "draft": draft, "synergy": synergy})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def team_body(roster, coach_id, name="My Team"):
    return {"name": name, "style1": "early", "style2": "teamfight", "focus1": "TOP", "focus2": "MID",
            "coach_id": coach_id, "roster": roster}


def test_catalogue_and_default_content(alice):
    champs = alice.get("/champions").json()
    assert len(champs) >= 155 and champs[0]["strength"] in ("Offence", "Defence", "Control")
    teams = alice.get("/teams").json()
    defaults = [t for t in teams if t["is_default"]]
    assert len(defaults) == 10 and sum(t["selectable"] for t in defaults) == 2
    assert all(not t["over_budget"] for t in defaults)   # system players are exempt even above 32
    assert any(p["stat_total"] > 32 for p in alice.get("/players").json() if p["is_default"])


def test_default_content_is_read_only(alice):
    team = alice.get("/teams?selectable=true").json()[0]
    assert alice.put(f"/teams/{team['id']}", team_body({}, None)).status_code == 403
    assert alice.delete(f"/teams/{team['id']}").status_code == 403
    player = alice.get("/players").json()[0]
    assert alice.delete(f"/players/{player['id']}").status_code == 403


def test_create_selectable_team(alice):
    roster = make_roster(alice)
    coach = make_coach(alice)
    res = alice.post("/teams", team_body(roster, coach))
    assert res.status_code == 201, res.text
    team = res.json()
    assert team["selectable"] and team["issues"] == [] and team["over_budget"] is False
    assert team["roster"]["TOP"]["name"] == "RTOP" and team["coach"]["id"] == coach
    # incomplete teams can be saved but are not selectable
    partial = alice.post("/teams", team_body({"TOP": roster["TOP"]}, None, name="Half")).json()
    assert not partial["selectable"] and len(partial["issues"]) >= 2
    assert alice.post("/teams", team_body(roster, coach)).status_code == 409   # duplicate name


def test_player_validation(alice):
    assert make_player(alice, "TOP", aggr=11).status_code == 400            # stat range
    assert make_player(alice, "TOP", aggr=0).status_code == 400
    assert make_player(alice, "ADC").status_code == 400                     # unknown role
    assert make_player(alice, "TOP", pool=[1, 2, 3]).status_code == 400     # pool size
    assert make_player(alice, "TOP", pool=[1, 1, 2, 3, 4]).status_code == 400   # duplicate
    assert make_player(alice, "TOP", pool=[1, 2, 3, 4, 9999]).status_code == 400  # unknown champion
    assert make_player(alice, "TOP").status_code == 201


def test_soft_stat_ceiling_flags_team_but_allows_it(alice):
    roster = make_roster(alice, prefix="S", aggr=9, aware=9, pos=9, dmg=9, cs=9)   # total 45 > 32
    assert alice.get("/players").json()  # saved fine
    coach = make_coach(alice)
    team = alice.post("/teams", team_body(roster, coach, name="Overpowered")).json()
    assert team["selectable"] is True
    assert team["over_budget"] is True
    assert len(team["over_budget_players"]) == 5
    assert team["over_budget_players"][0]["over_by"] == 13
    assert team["roster"]["TOP"]["over_budget_by"] == 13
    assert team["roster"]["TOP"]["stat_budget"] == 32          # hand-made players always get the standard ceiling


def test_coach_budget_is_enforced(alice):
    assert alice.post("/coaches", {"name": "C", "draft": 10, "synergy": 10}).status_code == 400
    assert alice.post("/coaches", {"name": "C", "draft": 0, "synergy": 5}).status_code == 400
    assert alice.post("/coaches", {"name": "C", "draft": 6, "synergy": 6}).status_code == 201


def test_roster_rules(alice):
    roster = make_roster(alice)
    coach = make_coach(alice)
    wrong_role = dict(roster, TOP=roster["MID"])
    assert alice.post("/teams", team_body(wrong_role, coach)).status_code == 400
    same_player_twice = dict(roster)
    bad = team_body(roster, coach)
    bad["style2"] = "early"
    assert alice.post("/teams", bad).status_code == 400                   # identical styles
    bad = team_body(roster, coach)
    bad["focus2"] = "TOP"
    assert alice.post("/teams", bad).status_code == 400                   # identical focus
    bad = team_body(roster, coach)
    bad["style1"] = "nonsense"
    assert alice.post("/teams", bad).status_code == 400
    del same_player_twice


def test_ownership_and_privacy(client, alice):
    roster = make_roster(alice)
    coach = make_coach(alice)
    team = alice.post("/teams", team_body(roster, coach)).json()
    bob = Api(client, "bob")
    assert bob.get(f"/teams/{team['id']}").status_code == 404
    assert bob.put(f"/teams/{team['id']}", team_body(roster, coach)).status_code == 404
    assert bob.delete(f"/players/{roster['TOP']}").status_code == 404
    assert all(t["is_default"] for t in bob.get("/teams").json())
    assert all(p["is_default"] for p in bob.get("/players").json())
    # bob cannot use alice's players or coach in his own team
    assert bob.post("/teams", team_body(roster, coach)).status_code == 404


def test_edit_and_delete(alice):
    roster = make_roster(alice)
    coach = make_coach(alice)
    team = alice.post("/teams", team_body(roster, coach)).json()
    edited = team_body(roster, coach, name="Renamed")
    edited["style1"], edited["style2"] = "scaling", "skirmish"
    res = alice.put(f"/teams/{team['id']}", edited).json()
    assert res["name"] == "Renamed" and res["style1"] == "scaling"

    # deleting a rostered player makes the team unselectable until refilled
    assert alice.delete(f"/players/{roster['JUNGLE']}").status_code == 204
    after = alice.get(f"/teams/{team['id']}").json()
    assert after["selectable"] is False and after["roster"]["JUNGLE"] is None
    # deleting a coach unsets it
    assert alice.delete(f"/coaches/{coach}").status_code == 204
    assert alice.get(f"/teams/{team['id']}").json()["coach"] is None
    assert alice.delete(f"/teams/{team['id']}").status_code == 204
    assert alice.get(f"/teams/{team['id']}").status_code == 404


def test_update_player_pool_and_role_lock(alice):
    roster = make_roster(alice)
    coach = make_coach(alice)
    alice.post("/teams", team_body(roster, coach))
    p = alice.get(f"/players/{roster['TOP']}").json()
    body = {k: p[k] for k in ("name", "role", "age", "region", "aggr", "aware", "pos", "dmg", "cs")}
    body["pool"] = [40, 41, 42, 43, 44]
    res = alice.put(f"/players/{p['id']}", body)
    assert res.status_code == 200 and res.json()["pool"] == [40, 41, 42, 43, 44]
    body["role"] = "MID"
    assert alice.put(f"/players/{p['id']}", body).status_code == 409   # on a roster: cannot change role


def test_duplicate_default_team(alice):
    default = alice.get("/teams?selectable=true").json()[0]
    copy = alice.post(f"/teams/{default['id']}/duplicate").json()
    assert copy["is_default"] is False and copy["selectable"] is True
    assert copy["name"].endswith("(copy)")
    assert copy["roster"]["TOP"]["id"] != default["roster"]["TOP"]["id"]
    assert copy["roster"]["TOP"]["over_budget_by"] >= 0
    again = alice.post(f"/teams/{default['id']}/duplicate").json()
    assert again["name"] != copy["name"]


def test_custom_team_plays_a_full_game_and_shows_flag_to_opponent(alice, client):
    bob = Api(client, "bob")
    roster = make_roster(alice, prefix="X", aggr=9, aware=9, pos=9, dmg=9, cs=9)
    coach = make_coach(alice)
    custom = alice.post("/teams", team_body(roster, coach, name="Flagged")).json()
    default = bob.get("/teams?selectable=true").json()[0]

    lobby = alice.post("/lobbies", {"settings": {"hide_player_data": True}}).json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": custom["id"]})
    state = bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": default["id"]}).json()
    # the opponent sees the warning flag even though the player data is hidden
    seen = state["teams"]["BLUE"]
    assert seen["over_budget"] is True and seen["hidden"] is True
    assert "total" not in seen["over_budget_players"][0] and seen["over_budget_players"][0]["over_by"] == 13
    assert "aggr" not in seen["roster"]["TOP"]

    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    bob.post(f"/games/{gid}/ready")
    # edits after the game started do not affect it (snapshot)
    alice.put(f"/teams/{custom['id']}", team_body(roster, coach, name="Edited later"))
    draft = play_draft(alice, bob, gid, range(1, 80))
    state = alice.get(f"/games/{gid}/state").json()
    assert state["teams"]["BLUE"]["name"] == "Flagged"
    for user, picks in ((alice, draft["blue_picks"]), (bob, draft["red_picks"])):
        user.put(f"/games/{gid}/lineup", {"assignments": [{"lane": l, "champion_id": c} for l, c in zip(LANES, picks)]})
        user.post(f"/games/{gid}/lineup/ready")
    final = alice.get(f"/games/{gid}/state").json()
    assert final["status"] == "COMPLETED"
    assert final["teams"]["BLUE"]["over_budget"] is True
    assert "aggr" in final["teams"]["BLUE"]["roster"]["TOP"]     # revealed after the game
    # silence unused-helper warning
    assert start_draft

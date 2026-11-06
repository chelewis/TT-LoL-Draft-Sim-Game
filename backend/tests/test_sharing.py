"""Public sharing: publish players / coaches / teams, search other users' public ones, copy them."""
from app.core.database import SessionLocal
from app.game.config import LANES
from app.models import Player
from tests.test_import_seal import BODY, edit, riot  # noqa: F401  (riot is a fixture)

STATS = ("aggr", "aware", "pos", "dmg", "cs")


def imported(api, fake, *, role=None, rank="GOLD", mine=None, name="My guy"):
    """Import the fake Faker account as a player (optionally for a lane, at a rank, with given match numbers)."""
    fake.ranks = {"SOLO": rank, "FLEX": rank}
    if mine is not None:
        fake.mine = mine
    preview = api.post("/riot/preview", {**BODY, **({"role": role} if role else {})})
    assert preview.status_code == 200, preview.text
    preview = preview.json()
    res = api.post("/players", {**preview["player"], "name": name, "riot_ref": preview["riot_ref"]})
    assert res.status_code == 201, res.text
    return res.json()


def publish(api, kind, obj_id, public=True):
    return api.put(f"/{kind}/{obj_id}/public", {"public": public})


def hand_made(api, role="TOP"):
    champs = [c["id"] for c in api.get("/champions").json()][:5]
    res = api.post("/players", {"name": "Handy", "role": role, "aggr": 5, "aware": 5, "pos": 5, "dmg": 5, "cs": 5,
                                "pool": champs})
    assert res.status_code == 201, res.text
    return res.json()


def coach(api, name="Coachy", draft=6, synergy=6):
    res = api.post("/coaches", {"name": name, "draft": draft, "synergy": synergy})
    assert res.status_code == 201, res.text
    return res.json()


def genuine_team(api, fake, name="Shared Squad", rank="GOLD"):
    roster = {lane: imported(api, fake, role=lane, rank=rank)["id"] for lane in LANES}
    res = api.post("/teams", {"name": name, "style1": "early", "style2": "teamfight",
                              "coach_id": coach(api)["id"], "roster": roster})
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------------ publish
def test_unedited_import_is_published_under_its_riot_name(alice, riot):
    p = imported(alice, riot, name="Renamed")
    assert p["is_public"] is False and p["share_issues"] == []
    res = publish(alice, "players", p["id"])
    assert res.status_code == 200, res.text
    assert res.json()["is_public"] and res.json()["name"] == "Faker"
    # renaming a public player is ignored: it keeps its Riot name
    again = edit(alice, res.json(), name="Something else")
    assert again["name"] == "Faker" and again["is_public"]
    # and it can be made private again
    assert publish(alice, "players", p["id"], False).json()["is_public"] is False


def test_hand_made_edited_and_unverified_players_cannot_be_public(alice, riot):
    plain = hand_made(alice)
    assert plain["share_issues"] and publish(alice, "players", plain["id"]).status_code == 400

    original = imported(alice, riot)
    edited = edit(alice, original, aggr=original["aggr"] - 1 if original["aggr"] > 1 else 2)
    assert edited["riot"]["import_check"]["status"] == "edited"
    assert publish(alice, "players", edited["id"]).status_code == 400

    p = imported(alice, riot)
    with SessionLocal() as db:
        db.get(Player, p["id"]).riot_seal = None
        db.commit()
    assert publish(alice, "players", p["id"]).status_code == 400


def test_default_content_cannot_be_published(alice, default_team_ids):
    assert publish(alice, "teams", default_team_ids[0]).status_code == 403


def test_editing_a_public_player_into_edited_unpublishes_it_and_its_team(alice, riot):
    team = genuine_team(alice, riot)
    assert publish(alice, "teams", team["id"]).status_code == 200
    top = team["roster"]["TOP"]
    assert publish(alice, "players", top["id"]).status_code == 200
    player = alice.get(f"/players/{top['id']}").json()
    changed = edit(alice, player, cs=player["cs"] - 1 if player["cs"] > 1 else 2)
    assert changed["is_public"] is False
    assert alice.get(f"/teams/{team['id']}").json()["is_public"] is False


def test_deleting_a_player_unpublishes_the_team(alice, riot):
    team = genuine_team(alice, riot)
    assert publish(alice, "teams", team["id"]).status_code == 200
    assert alice.delete(f"/players/{team['roster']['MID']['id']}").status_code == 204
    assert alice.get(f"/teams/{team['id']}").json()["is_public"] is False


def test_team_needs_a_full_genuine_roster(alice, riot):
    roster = {lane: imported(alice, riot, role=lane)["id"] for lane in LANES}
    roster["TOP"] = hand_made(alice, "TOP")["id"]
    team = alice.post("/teams", {"name": "Mixed", "style1": "early", "style2": "scaling",
                                 "coach_id": coach(alice)["id"], "roster": roster}).json()
    assert team["share_issues"] and "Handy" in team["share_issues"][0]
    assert publish(alice, "teams", team["id"]).status_code == 400
    incomplete = alice.post("/teams", {"name": "Half", "roster": {"MID": roster["MID"]}}).json()
    assert publish(alice, "teams", incomplete["id"]).status_code == 400


# ------------------------------------------------------------------- search
def test_player_search_filters(alice, bob, riot):
    strong = imported(alice, riot, role="MID", rank="DIAMOND")
    weak = imported(alice, riot, role="TOP", rank="SILVER", mine=dict(kills=1, deaths=9, assists=2, cs=110,
                                                                       jungle_cs=4, vision=8, damage=8000,
                                                                       dragons=0, barons=0))
    private = imported(alice, riot, role="BOT")
    for p in (strong, weak):
        assert publish(alice, "players", p["id"]).status_code == 200
    strong, weak = alice.get(f"/players/{strong['id']}").json(), alice.get(f"/players/{weak['id']}").json()

    def ids(**params):
        res = bob.get("/public/players", params=params)
        assert res.status_code == 200, res.text
        return {p["id"] for p in res.json()["items"]}

    assert ids() == {strong["id"], weak["id"]}             # private ones never show
    assert private["id"] not in ids()
    assert alice.get("/public/players").json()["items"] == []   # your own public players aren't listed
    for lane in LANES:   # primary or secondary role
        assert ids(role=lane) == {p["id"] for p in (strong, weak) if lane in (p["role"], p["secondary_role"])}
    assert ids(rank_min="GOLD") == {strong["id"]}
    assert ids(rank_max="GOLD") == {weak["id"]}
    assert ids(total_min=strong["stat_total"]) >= {strong["id"]}
    assert ids(total_max=weak["stat_total"]) == {weak["id"]} or strong["stat_total"] <= weak["stat_total"]
    assert ids(aggr_min=strong["aggr"], aggr_max=strong["aggr"]) >= {strong["id"]}
    champ = strong["pool"][0]
    assert strong["id"] in ids(champions=[champ])
    assert ids(champions=[champ, 99999]) == set()          # every champion must be in the pool
    assert ids(q="fak") == {strong["id"], weak["id"]} and ids(q="zzz") == set()
    tag = next((t["key"] for t in strong["tags"]), None)
    if tag:
        assert strong["id"] in ids(tags=[tag])
    assert ids(tags=["no-such-tag"]) == set()

    page = bob.get("/public/players", params={"limit": 1, "sort": "rank"}).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["items"][0]["id"] == strong["id"]
    assert page["items"][0]["owner"] == "alice"


def test_coach_search(alice, bob):
    a, b = coach(alice, "Strategist", 8, 4), coach(alice, "Motivator", 3, 9)
    for c in (a, b):
        assert publish(alice, "coaches", c["id"]).status_code == 200
    items = bob.get("/public/coaches", params={"draft_min": 7}).json()["items"]
    assert [c["id"] for c in items] == [a["id"]]
    items = bob.get("/public/coaches", params={"synergy_min": 5, "q": "moti"}).json()["items"]
    assert [c["id"] for c in items] == [b["id"]]


def test_team_search(alice, bob, riot):
    team = genuine_team(alice, riot, rank="DIAMOND")
    assert publish(alice, "teams", team["id"]).status_code == 200

    def found(**params):
        res = bob.get("/public/teams", params=params)
        assert res.status_code == 200, res.text
        return [t["id"] for t in res.json()["items"]]

    assert found() == [team["id"]]
    item = bob.get("/public/teams").json()["items"][0]
    assert item["owner"] == "alice" and item["average_rank"] == 6   # Diamond
    total = item["stat_total"]
    assert found(total_min=total, total_max=total) == [team["id"]] and found(total_max=total - 1) == []
    assert found(rank_min="DIAMOND") == [team["id"]] and found(rank_min="MASTER") == []
    assert found(style="teamfight") == [team["id"]] and found(style="scaling") == []
    assert found(champion=team["roster"]["MID"]["pool"][0]) == [team["id"]]
    assert found(coach_draft_min=7) == []


# --------------------------------------------------------------------- copy
def test_copying_a_public_player_keeps_it_genuine(alice, bob, riot):
    p = imported(alice, riot)
    publish(alice, "players", p["id"])
    res = bob.post(f"/public/players/{p['id']}/copy")
    assert res.status_code == 201, res.text
    copy = res.json()
    assert copy["id"] != p["id"] and copy["is_public"] is False and copy["is_default"] is False
    assert copy["riot"]["import_check"]["status"] == "unedited" and copy["name"] == "Faker"
    assert copy["id"] in {x["id"] for x in bob.get("/players").json()}
    assert bob.post(f"/public/players/{copy['id']}/copy").status_code == 404   # bob's copy is private
    assert alice.post(f"/public/players/{p['id']}/copy").status_code == 400    # already yours


def test_copying_a_team_copies_its_players_and_coach(alice, bob, riot):
    team = genuine_team(alice, riot)
    publish(alice, "teams", team["id"])
    res = bob.post(f"/public/teams/{team['id']}/copy")
    assert res.status_code == 201, res.text
    copy = res.json()
    assert copy["name"] == "Shared Squad" and copy["selectable"] and copy["coach"]["is_default"] is False
    assert all(p["riot"]["import_check"]["status"] == "unedited" for p in copy["roster"].values())
    assert {p["id"] for p in copy["roster"].values()}.isdisjoint({p["id"] for p in team["roster"].values()})
    # private teams can't be copied
    publish(alice, "teams", team["id"], False)
    assert bob.post(f"/public/teams/{team['id']}/copy").status_code == 404


def test_duplicate_keeps_riot_data(alice, riot):
    team = genuine_team(alice, riot)
    dup = alice.post(f"/teams/{team['id']}/duplicate").json()
    assert all(p["riot"] and p["riot"]["import_check"]["status"] == "unedited" for p in dup["roster"].values())


def test_copy_respects_limits(alice, bob, monkeypatch):
    from app.services import team_management_service
    c = coach(alice)
    publish(alice, "coaches", c["id"])
    monkeypatch.setitem(team_management_service.CFG, "max_coaches_per_user", 0)
    assert bob.post(f"/public/coaches/{c['id']}/copy").status_code == 409

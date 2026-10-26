"""Admins create, edit and delete the default (system) teams, players and coaches."""
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.data.seed_db import seed_database
from app.game.config import LANES
from app.models import Coach, Player, Team
from tests.conftest import Api
from tests.test_api_management import STATS, make_coach, make_roster, team_body


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_usernames", ["Root"])
    return Api(client, "root")


def player_body(role="TOP", name="Default P", pool=(1, 2, 3, 4, 5), **extra):
    return {"name": name, "role": role, "secondary_role": None, "age": 22, "region": "EU",
            **STATS, "pool": list(pool), **extra}


def default_roster(admin, prefix="D"):
    ids = {}
    for i, lane in enumerate(LANES):
        res = admin.post("/admin/defaults/players", player_body(lane, f"{prefix}{lane}", [i * 5 + k + 1 for k in range(5)]))
        assert res.status_code == 201, res.text
        ids[lane] = res.json()["id"]
    return ids


def default_coach(admin, name="Default Coach"):
    res = admin.post("/admin/defaults/coaches", {"name": name, "draft": 6, "synergy": 6})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_only_admins_can_change_defaults(admin, alice):
    team = alice.get("/teams?selectable=true").json()[0]
    player = next(p for p in alice.get("/players").json() if p["is_default"])
    coach = next(c for c in alice.get("/coaches").json() if c["is_default"])
    calls = [
        ("post", "/admin/defaults/teams", team_body({}, None)),
        ("put", f"/admin/defaults/teams/{team['id']}", team_body({}, None)),
        ("delete", f"/admin/defaults/teams/{team['id']}", None),
        ("post", "/admin/defaults/players", player_body()),
        ("put", f"/admin/defaults/players/{player['id']}", player_body()),
        ("delete", f"/admin/defaults/players/{player['id']}", None),
        ("post", "/admin/defaults/coaches", {"name": "C", "draft": 5, "synergy": 5}),
        ("put", f"/admin/defaults/coaches/{coach['id']}", {"name": "C", "draft": 5, "synergy": 5}),
        ("delete", f"/admin/defaults/coaches/{coach['id']}", None),
    ]
    for method, path, body in calls:
        kw = {} if method == "delete" else {"json": body}
        assert getattr(alice, method)(path, **kw).status_code == 403, path
        assert getattr(admin.client, method)("/api/v1" + path, **kw).status_code == 401, path
    # the user routes stay read-only for default content, admins included
    assert admin.delete(f"/teams/{team['id']}").status_code == 403
    assert admin.put(f"/coaches/{coach['id']}", {"name": "C", "draft": 5, "synergy": 5}).status_code == 403


def test_admin_crud_on_default_content(admin, alice):
    roster = default_roster(admin)
    coach = default_coach(admin)
    res = admin.post("/admin/defaults/teams", team_body(roster, coach, name="New Default"))
    assert res.status_code == 201, res.text
    team = res.json()
    assert team["is_default"] and team["selectable"] and team["coach"]["is_default"]
    assert all(team["roster"][lane]["is_default"] for lane in LANES)

    # everyone sees it as default, read-only content
    seen = next(t for t in alice.get("/teams").json() if t["id"] == team["id"])
    assert seen["is_default"] and alice.delete(f"/teams/{team['id']}").status_code == 403

    # edit all three
    edited = admin.put(f"/admin/defaults/teams/{team['id']}", team_body(roster, coach, name="Renamed")).json()
    assert edited["name"] == "Renamed"
    p = admin.put(f"/admin/defaults/players/{roster['TOP']}", player_body("TOP", "Better", aggr=9)).json()
    assert p["name"] == "Better" and p["aggr"] == 9 and p["is_default"]
    c = admin.put(f"/admin/defaults/coaches/{coach}", {"name": "Renamed Coach", "draft": 7, "synergy": 5}).json()
    assert c["name"] == "Renamed Coach" and c["draft"] == 7
    assert admin.put(f"/admin/defaults/coaches/{coach}", {"name": "X", "draft": 10, "synergy": 10}).status_code == 400

    # duplicate default team names are refused
    assert admin.post("/admin/defaults/teams", team_body({}, None, name="Renamed")).status_code == 409

    # delete
    assert admin.delete(f"/admin/defaults/teams/{team['id']}").status_code == 204
    assert all(t["id"] != team["id"] for t in alice.get("/teams").json())
    assert admin.delete(f"/admin/defaults/coaches/{coach}").status_code == 204
    assert admin.delete(f"/admin/defaults/players/{roster['TOP']}").status_code == 204
    assert alice.get(f"/players/{roster['TOP']}").status_code == 404


def test_admin_routes_only_touch_default_rows(admin, alice):
    user_roster = make_roster(alice)
    user_coach = make_coach(alice)
    user_team = alice.post("/teams", team_body(user_roster, user_coach)).json()
    assert admin.put(f"/admin/defaults/players/{user_roster['TOP']}", player_body()).status_code == 404
    assert admin.delete(f"/admin/defaults/coaches/{user_coach}").status_code == 404
    assert admin.delete(f"/admin/defaults/teams/{user_team['id']}").status_code == 404
    # a default team may only use default players and coaches
    assert admin.post("/admin/defaults/teams", team_body({"TOP": user_roster["TOP"]}, None, "X")).status_code == 404
    assert admin.post("/admin/defaults/teams", team_body({}, user_coach, "Y")).status_code == 404


def test_default_players_cannot_link_riot(admin):
    res = admin.post("/admin/defaults/players", player_body(riot_ref="anything"))
    assert res.status_code == 400 and "Riot" in res.json()["detail"]


def test_no_per_user_limit_on_defaults(admin, monkeypatch):
    from app.game.config import MANAGEMENT_CONFIG
    monkeypatch.setitem(MANAGEMENT_CONFIG, "max_coaches_per_user", 1)
    for i in range(3):
        default_coach(admin, f"Coach {i}")


def test_deleting_defaults_clears_them_from_user_teams(admin, alice):
    roster = default_roster(admin)
    coach = default_coach(admin)
    team = alice.post("/teams", team_body(roster, coach)).json()
    assert team["selectable"]

    assert admin.delete(f"/admin/defaults/players/{roster['MID']}").status_code == 204
    after = alice.get(f"/teams/{team['id']}").json()
    assert after["roster"]["MID"] is None and not after["selectable"]

    assert admin.delete(f"/admin/defaults/coaches/{coach}").status_code == 204
    assert alice.get(f"/teams/{team['id']}").json()["coach"] is None


def test_role_change_blocked_while_rostered_on_a_user_team(admin, alice):
    roster = default_roster(admin)
    alice.post("/teams", team_body(roster, None))
    res = admin.put(f"/admin/defaults/players/{roster['TOP']}", player_body("MID", "DTOP"))
    assert res.status_code == 409


def test_seeding_does_not_duplicate_after_default_teams_are_deleted(admin, alice):
    for t in alice.get("/teams").json():
        if t["is_default"]:
            assert admin.delete(f"/admin/defaults/teams/{t['id']}").status_code == 204

    def counts(db):
        return [db.scalar(select(func.count()).select_from(m).where(m.owner_user_id.is_(None)))
                for m in (Team, Player, Coach)]

    with SessionLocal() as db:
        before = counts(db)
        assert before[0] == 0
        seed_database(db)
        assert counts(db) == before

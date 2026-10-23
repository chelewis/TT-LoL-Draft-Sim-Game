"""Admin users page: list every user with activity counts, and reset passwords (signing the user out)."""
import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import User
from tests.conftest import Api, play_draft, start_draft


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_usernames", ["root"])
    return Api(client, "root")


def user_id(api):
    return api.user["id"]


def reset(admin, target, password="brand-new-pass"):
    return admin.post(f"/admin/users/{user_id(target)}/password", {"password": password})


def login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_only_admins_can_list_and_reset(admin, alice):
    assert alice.get("/admin/users").status_code == 403
    assert reset(alice, admin).status_code == 403
    assert admin.client.get("/api/v1/admin/users").status_code == 401
    assert admin.client.post(f"/api/v1/admin/users/{user_id(alice)}/password",
                             json={"password": "brand-new-pass"}).status_code == 401


def test_list_shows_every_user_with_counts(admin, alice, bob, default_team_ids):
    assert alice.post(f"/teams/{default_team_ids[0]}/duplicate").status_code in (200, 201)   # 1 team, 5 players
    gid = start_draft(alice, bob, default_team_ids)
    play_draft(alice, bob, gid, range(1, 200))
    assert alice.post(f"/games/{gid}/lineup/ready").status_code == 200
    assert bob.post(f"/games/{gid}/lineup/ready").json()["status"] == "COMPLETED"

    rows = {r["username"]: r for r in admin.get("/admin/users").json()}
    assert set(rows) == {"root", "alice", "bob"}
    assert rows["root"]["is_admin"] is True and rows["alice"]["is_admin"] is False
    assert rows["alice"] | {"created_at": None} == {
        "id": user_id(alice), "username": "alice", "email": "alice@example.com", "is_admin": False,
        "created_at": None, "password_changed_at": None, "teams": 1, "players": 5, "games": 1}
    assert rows["alice"]["created_at"].endswith("Z")
    assert (rows["bob"]["teams"], rows["bob"]["players"], rows["bob"]["games"]) == (0, 0, 1)
    assert rows["root"]["games"] == 0
    assert "password" not in str(rows).replace("password_changed_at", "")   # no hashes leak


def test_reset_changes_the_password_and_signs_the_user_out(admin, alice):
    assert reset(admin, alice).status_code == 204
    assert login(admin.client, "alice", "password123").status_code == 401
    fresh = login(admin.client, "alice", "brand-new-pass")
    assert fresh.status_code == 200

    # the token alice had before the reset no longer works; one issued after it does
    assert alice.get("/auth/me").status_code == 401
    headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert admin.client.get("/api/v1/auth/me", headers=headers).status_code == 200
    row = next(r for r in admin.get("/admin/users").json() if r["username"] == "alice")
    assert row["password_changed_at"] is not None


def test_reset_closes_off_the_game_socket(admin, alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    with alice.client.websocket_connect(f"/ws/games/{gid}?token={alice.token}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
    assert reset(admin, alice).status_code == 204
    with pytest.raises(WebSocketDisconnect):
        with alice.client.websocket_connect(f"/ws/games/{gid}?token={alice.token}") as ws:
            ws.receive_json()


def test_tokens_without_issued_at_still_work_until_a_reset(admin, alice):
    import jwt
    from datetime import datetime, timedelta, timezone
    old = jwt.encode({"sub": str(user_id(alice)), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                     settings.secret_key, algorithm="HS256")
    headers = {"Authorization": f"Bearer {old}"}
    assert admin.client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert reset(admin, alice).status_code == 204
    assert admin.client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_reset_validates_the_password_and_the_user(admin, alice):
    assert reset(admin, alice, "short").status_code == 422
    assert admin.post("/admin/users/999999/password", {"password": "brand-new-pass"}).status_code == 404
    with SessionLocal() as db:
        assert db.get(User, user_id(alice)).password_changed_at is None   # nothing changed

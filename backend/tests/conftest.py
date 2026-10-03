import os

# Must be set before the application modules are imported: in-memory database, no background task.
os.environ["LDM_DATABASE_URL"] = "sqlite://"
os.environ["LDM_RUN_TIMEOUT_TASK"] = "false"
os.environ["LDM_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
os.environ["LDM_AUTH_RATE_LIMIT"] = "100000"
os.environ["LDM_RIOT_API_KEY"] = ""     # never let a developer's real .env key leak into tests

import random

import pytest

from app.data.loader import load_seed_data, seed_team_setup
from app.game.config import LANES


@pytest.fixture(scope="session")
def seed():
    return load_seed_data()


@pytest.fixture(scope="session")
def champions(seed):
    return {c.id: c for c in seed.champions}


def random_lineup(seed, rng, exclude=()):
    ids = [c.id for c in seed.champions if c.id not in exclude]
    return dict(zip(LANES, rng.sample(ids, 5)))


@pytest.fixture
def make_teams(seed):
    def _make(rng_seed=1):
        rng = random.Random(rng_seed)
        blue_lineup = random_lineup(seed, rng)
        red_lineup = random_lineup(seed, rng, exclude=blue_lineup.values())
        return seed_team_setup(seed, 1, blue_lineup), seed_team_setup(seed, 2, red_lineup)
    return _make


# ------------------------------------------------------------- API fixtures
@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.core import rate_limit
    from app.core.database import Base, engine
    from app.main import app

    Base.metadata.drop_all(engine)
    rate_limit.reset()
    with TestClient(app) as test_client:  # runs the lifespan: create tables + seed default content
        yield test_client


class Api:
    """Small helper around TestClient for readable API tests."""

    def __init__(self, client, username):
        self.client = client
        res = client.post("/api/v1/auth/register", json={
            "username": username, "email": f"{username}@example.com", "password": "password123"})
        assert res.status_code == 201, res.text
        self.token = res.json()["access_token"]
        self.user = res.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def get(self, path, **kw):
        return self.client.get("/api/v1" + path, headers=self.headers, **kw)

    def post(self, path, json=None, **kw):
        return self.client.post("/api/v1" + path, json=json, headers=self.headers, **kw)

    def put(self, path, json=None, **kw):
        return self.client.put("/api/v1" + path, json=json, headers=self.headers, **kw)

    def delete(self, path, **kw):
        return self.client.delete("/api/v1" + path, headers=self.headers, **kw)


@pytest.fixture
def alice(client):
    return Api(client, "alice")


@pytest.fixture
def bob(client):
    return Api(client, "bob")


@pytest.fixture
def default_team_ids(alice):
    teams = alice.get("/teams?selectable=true").json()
    return [t["id"] for t in teams]


def start_draft(alice, bob, team_ids, hide=False):
    """Create a lobby, join it, pick the two default teams and ready up. Returns game_id."""
    lobby = alice.post("/lobbies", {"settings": {"hide_player_data": hide}}).json()
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 200
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_ids[0]}).status_code == 200
    assert bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_ids[1]}).status_code == 200
    gid = lobby["game_id"]
    assert alice.post(f"/games/{gid}/ready").status_code == 200
    assert bob.post(f"/games/{gid}/ready").status_code == 200
    return gid


def play_draft(alice, bob, gid, champion_ids):
    """Drive the draft to completion with sequential champion ids."""
    ids = iter(champion_ids)
    users = {"BLUE": alice, "RED": bob}
    while True:
        draft = alice.get(f"/games/{gid}/draft").json()
        if draft["complete"]:
            return draft
        user = users[draft["current_team"]]
        kind = "pick" if draft["action_type"] == "PICK" else "ban"
        res = user.post(f"/games/{gid}/draft/{kind}", {"champion_id": next(ids)})
        assert res.status_code == 200, res.text

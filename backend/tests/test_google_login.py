"""Sign in with Google: ID tokens are verified for real (RS256 signature, audience, issuer, expiry), with a
test key standing in for Google's published keys."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import google
from app.core.config import settings

CLIENT_ID = "test-client.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def google_enabled(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(google, "_signing_key", lambda token: KEY.public_key())


def token(key=KEY, **overrides):
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1001", "email": "Jane.Doe@gmail.com",
              "email_verified": True, "name": "Jane Doe", "iat": now, "exp": now + 3600, **overrides}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")


def sign_in(client, credential):
    return client.post("/api/v1/auth/google", json={"credential": credential})


def test_first_sign_in_creates_an_account_and_later_ones_log_into_it(client):
    first = sign_in(client, token())
    assert first.status_code == 200, first.text
    user = first.json()["user"]
    assert user["username"] == "Jane_Doe" and user["email"] == "jane.doe@gmail.com"
    again = sign_in(client, token(email="renamed@gmail.com"))      # matched on Google's id, not the email
    assert again.json()["user"]["id"] == user["id"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {again.json()['access_token']}"})
    assert me.json()["username"] == "Jane_Doe"


def test_google_accounts_cannot_log_in_with_a_password(client):
    sign_in(client, token())
    for password in ("", "password123"):
        res = client.post("/api/v1/auth/login", json={"username": "Jane_Doe", "password": password})
        assert res.status_code == 401


def test_existing_password_account_with_the_same_email_is_not_taken_over(client):
    client.post("/api/v1/auth/register", json={"username": "squatter", "email": "jane.doe@gmail.com",
                                               "password": "password123"})
    res = sign_in(client, token())
    assert res.status_code == 409 and "already exists" in res.json()["detail"]


def test_username_clash_gets_a_number(client):
    client.post("/api/v1/auth/register", json={"username": "Jane_Doe", "email": "other@example.com",
                                               "password": "password123"})
    assert sign_in(client, token()).json()["user"]["username"] == "Jane_Doe2"


@pytest.mark.parametrize("bad", [
    token(aud="someone-elses-client.apps.googleusercontent.com"),   # issued for another app
    token(iss="https://evil.example.com"),                             # not from Google
    token(exp=int(time.time()) - 3600),                                # expired
    token(email_verified=False),                                       # unverified email
    token(email=None),                                                 # no email at all
    token(key=OTHER_KEY),                                              # not signed by Google's key
    "not-a-jwt-at-all-xxxxxxxxxxxxxxxx",
])
def test_bad_tokens_are_rejected(client, bad):
    assert sign_in(client, bad).status_code == 401


def test_providers_and_disabled_server(client, monkeypatch):
    assert client.get("/api/v1/auth/providers").json() == {"google_client_id": CLIENT_ID}
    monkeypatch.setattr(settings, "google_client_id", "")
    assert client.get("/api/v1/auth/providers").json() == {"google_client_id": None}
    assert sign_in(client, token()).status_code == 404

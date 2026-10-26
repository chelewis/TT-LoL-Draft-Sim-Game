"""Verify "Sign in with Google" ID tokens (OpenID Connect).

The browser gets a signed ID token (a JWT) from Google Identity Services and posts it to us. We check it
ourselves against Google's published signing keys: RS256 signature, issued by Google, for *our* client ID,
not expired, and with an email Google has verified. Nothing else in the token is trusted.
"""
from __future__ import annotations

from functools import lru_cache

import jwt

from .config import settings

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleTokenError(ValueError):
    pass


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    # caches Google's keys in memory and refetches when a token names a key it hasn't seen (key rotation)
    return jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=6 * 3600)


def _signing_key(token: str):
    return _jwks_client().get_signing_key_from_jwt(token).key


def verify_id_token(token: str) -> dict:
    """Return the verified claims (sub, email, name, ...) or raise GoogleTokenError."""
    if not settings.google_client_id:
        raise GoogleTokenError("Google sign-in is not configured.")
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise GoogleTokenError("That Google sign-in could not be verified.") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("That sign-in did not come from Google.")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise GoogleTokenError("Your Google account's email address is not verified.")
    return claims

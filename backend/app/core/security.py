from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    # sub-second issued-at, so a login straight after a password reset is still told apart from one before it
    return jwt.encode({"sub": str(user_id), "iat": now.timestamp(), "exp": expires},
                      settings.secret_key, algorithm=ALGORITHM)


def decode_access_claims(token: str) -> tuple[int, float | None] | None:
    """Return (user id, issued-at in Unix seconds) for a valid token, or None. Tokens made before
    issued-at was recorded have None for it."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        issued = payload.get("iat")
        return int(payload["sub"]), float(issued) if issued is not None else None
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def decode_access_token(token: str) -> int | None:
    """Return the user id in a valid token, or None."""
    claims = decode_access_claims(token)
    return claims[0] if claims else None

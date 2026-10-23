from __future__ import annotations

from datetime import timezone

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models import User

from .config import settings
from .database import get_db
from .errors import forbidden, unauthorized
from .security import decode_access_claims

bearer = HTTPBearer(auto_error=False)


def user_from_token(db: Session, token: str) -> User | None:
    """The user a token belongs to, or None when it is invalid, expired, or older than the user's last
    password reset (a reset signs the user out everywhere)."""
    claims = decode_access_claims(token)
    if claims is None:
        return None
    user_id, issued = claims
    user = db.get(User, user_id)
    if user is None:
        return None
    if user.password_changed_at is not None:
        changed = user.password_changed_at.replace(tzinfo=timezone.utc).timestamp()
        if issued is None or issued < changed:
            return None
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise unauthorized()
    user = user_from_token(db, credentials.credentials)
    if user is None:
        raise unauthorized("Invalid or expired token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not settings.is_admin(user.username):
        raise forbidden("Admin access is required.")
    return user

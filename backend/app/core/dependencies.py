from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models import User

from .config import settings
from .database import get_db
from .errors import forbidden, unauthorized
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise unauthorized()
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise unauthorized("Invalid or expired token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not settings.is_admin(user.username):
        raise forbidden("Admin access is required.")
    return user

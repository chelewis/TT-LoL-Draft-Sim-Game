from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.errors import conflict, not_found, unauthorized
from app.core.google import GoogleTokenError, verify_id_token
from app.core.rate_limit import auth_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import GoogleLoginRequest, LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email, is_admin=settings.is_admin(user.username))


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[Depends(auth_rate_limit)])
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    taken = db.scalar(select(User).where(or_(User.username == body.username, User.email == body.email)))
    if taken:
        raise conflict("That username or email is already registered.")
    user = User(username=body.username, email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    log.info("user_registered user_id=%s", user.id)
    return TokenOut(access_token=create_access_token(user.id), user=_out(user))


@router.post("/login", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    ident = body.username.strip()
    user = db.scalar(select(User).where(or_(User.username == ident, User.email == ident.lower())))
    if user is None or not verify_password(body.password, user.password_hash):
        raise unauthorized("Incorrect username or password.")
    return TokenOut(access_token=create_access_token(user.id), user=_out(user))


@router.post("/logout", status_code=204)
def logout(_: User = Depends(get_current_user)):
    # Tokens are stateless; the client discards its token. Endpoint exists for API symmetry.
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _out(user)


# ------------------------------------------------------------ Sign in with Google
@router.get("/providers")
def providers():
    """Which extra sign-in options the login page should offer. The Google client ID is public by design."""
    return {"google_client_id": settings.google_client_id or None}


def _username_from(claims: dict, db: Session) -> str:
    """A free username from the Google name or email, e.g. "Jane Doe" -> "Jane_Doe", "Jane_Doe2"."""
    raw = claims.get("name") or claims["email"].split("@")[0]
    base = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")[:28] or "player"
    base = base if len(base) >= 3 else f"{base}_gg"
    name, n = base, 1
    while db.scalar(select(User.id).where(User.username == name)) is not None:
        n += 1
        name = f"{base}{n}"
    return name


@router.post("/google", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def google_login(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Log in (or sign up) with a Google ID token.

    Accounts are matched on Google's stable account id (`sub`), never on email alone. If a password account
    already uses the same email, we refuse instead of merging: this app does not verify emails at
    registration, so that account may not belong to the person signing in with Google.
    """
    if not settings.google_enabled:
        raise not_found("Google sign-in is not enabled on this server.")
    try:
        claims = verify_id_token(body.credential)
    except GoogleTokenError as exc:
        raise unauthorized(str(exc)) from exc
    user = db.scalar(select(User).where(User.google_sub == claims["sub"]))
    if user is None:
        email = claims["email"].strip().lower()
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise conflict("An account with this email already exists. Log in with your username and password.")
        user = User(username=_username_from(claims, db), email=email, password_hash="", google_sub=claims["sub"])
        db.add(user)
        db.commit()
        log.info("user_registered user_id=%s via=google", user.id)
    return TokenOut(access_token=create_access_token(user.id), user=_out(user))


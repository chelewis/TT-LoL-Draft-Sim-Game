from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.errors import conflict, unauthorized
from app.core.rate_limit import auth_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email)


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

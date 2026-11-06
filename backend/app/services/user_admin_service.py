"""Admin view of site users and password resets: a stopgap until self-service password recovery exists."""
from __future__ import annotations

from sqlalchemy import func, select, union
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.core.config import settings
from app.core.errors import not_found
from app.core.security import hash_password
from app.models import Game, Player, Team, User


def _counts_by_owner(db: Session, model) -> dict[int, int]:
    rows = db.execute(select(model.owner_user_id, func.count()).where(model.owner_user_id.is_not(None),
                                                                    model.season_id.is_(None))
                      .group_by(model.owner_user_id))
    return {uid: n for uid, n in rows}


def _completed_games_by_user(db: Session) -> dict[int, int]:
    """Finished games each user played in; a single player game (both seats) counts once."""
    done = Game.status == "COMPLETED"
    seats = union(select(Game.id.label("game_id"), Game.blue_player_id.label("user_id")).where(done),
                  select(Game.id.label("game_id"), Game.red_player_id.label("user_id")).where(done)).subquery()
    rows = db.execute(select(seats.c.user_id, func.count()).where(seats.c.user_id.is_not(None))
                      .group_by(seats.c.user_id))
    return {uid: n for uid, n in rows}


def list_users(db: Session) -> list[dict]:
    teams, players, games = _counts_by_owner(db, Team), _counts_by_owner(db, Player), _completed_games_by_user(db)
    return [{
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "is_admin": settings.is_admin(u.username),
        "created_at": iso(u.created_at),
        "password_changed_at": iso(u.password_changed_at),
        "teams": teams.get(u.id, 0),
        "players": players.get(u.id, 0),
        "games": games.get(u.id, 0),
    } for u in db.scalars(select(User).order_by(func.lower(User.username)))]


def reset_password(db: Session, user_id: int, password: str) -> User:
    """Set a new password. Every token issued before now stops working, so the user is signed out everywhere."""
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User not found.")
    user.password_hash = hash_password(password)
    user.password_changed_at = utcnow()
    db.commit()
    return user

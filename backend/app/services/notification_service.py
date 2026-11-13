"""User notifications: an inbox per user, pushed live on the user's WebSocket channel.

Services call `notify` inside their transaction; the notification is only delivered (a NOTIFICATION nudge on
/ws/me, so the client refetches its inbox) once that transaction commits, and dropped with it on a rollback.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, event, func, select, update
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.models import Notification, User
from app.websocket.manager import manager

INBOX_SIZE = 30
KEEP_READ = timedelta(days=30)         # read notifications older than this are cleared away
_USERS, _KEYS = "notify_users", "notify_keys"


def notify(db: Session, user_id: int | None, kind: str, title: str, body: str = "", link: str = "",
           season_id: int | None = None, key: str | None = None) -> None:
    """Queue a notification for `user_id` (no one: the CPU). With a `key`, a second notification with the same key
    for the same user is never sent."""
    if user_id is None:
        return
    if key:
        queued = db.info.setdefault(_KEYS, set())
        if (user_id, key) in queued or db.scalar(select(Notification.id).where(
                Notification.user_id == user_id, Notification.key == key)) is not None:
            return
        queued.add((user_id, key))
    db.add(Notification(user_id=user_id, kind=kind, title=title[:120], body=body[:300], link=link,
                        season_id=season_id, key=key))
    db.info.setdefault(_USERS, set()).add(user_id)


@event.listens_for(Session, "after_commit")
def _deliver(session: Session) -> None:
    session.info.pop(_KEYS, None)
    users = session.info.pop(_USERS, None)
    if users:
        manager.notify_users(users)


@event.listens_for(Session, "after_soft_rollback")
def _forget(session: Session, previous_transaction) -> None:
    session.info.pop(_KEYS, None)
    session.info.pop(_USERS, None)


def _view(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "season_id": n.season_id,
            "created_at": iso(n.created_at), "read": n.read_at is not None}


def inbox(db: Session, user: User) -> dict:
    items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(INBOX_SIZE)).all()
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                                  Notification.read_at.is_(None))) or 0
    return {"unread": unread, "items": [_view(n) for n in items]}


def mark_read(db: Session, user: User, ids: list[int] | None = None) -> dict:
    """Mark some notifications (or, with no ids, all of them) read, and clear away old read ones."""
    now = utcnow()
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=now))
    db.execute(delete(Notification).where(Notification.user_id == user.id, Notification.read_at.is_not(None),
                                          Notification.created_at < now - KEEP_READ))
    db.commit()
    return inbox(db, user)

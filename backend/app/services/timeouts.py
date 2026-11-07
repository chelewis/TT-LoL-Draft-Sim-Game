"""Background processing of draft timers, lobby expiry and season round deadlines.

The draft endpoints also apply expired timers lazily on every request, so the game never depends on this
loop for correctness; the loop just makes timeouts happen on time and notifies connected clients.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow
from app.models import Game
from app.services import game_service as svc
from app.services import season_service
from app.websocket.manager import manager

log = logging.getLogger(__name__)


def process_due_games(session_factory: sessionmaker) -> list[dict]:
    """Apply every expired draft timer and cancel expired lobbies. Returns events to broadcast."""
    events: list[dict] = []
    now = utcnow()
    with session_factory() as db:  # type: Session
        drafting = db.scalars(select(Game).where(Game.status == "DRAFTING", Game.action_expires_at <= now)).all()
        for game in drafting:
            events += svc.advance_timeouts(db, game, now)
        waiting = db.scalars(select(Game).where(Game.status.in_(svc.PRE_DRAFT))).all()
        for game in waiting:
            events += svc.expire_if_needed(db, game)
        events += season_service.process_deadlines(db, now)
    return events


async def timeout_loop(session_factory: sessionmaker, interval: float) -> None:
    while True:
        try:
            events = await asyncio.to_thread(process_due_games, session_factory)
            await manager.publish(events)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("timeout processing failed")
        await asyncio.sleep(interval)

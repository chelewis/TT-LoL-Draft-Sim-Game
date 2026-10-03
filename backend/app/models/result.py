from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base, JSONType


class MatchResultRow(Base):
    """One result per completed game. `data` holds the full structured result
    (teams, lanes, per-player stats) so clients get it in one read."""
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), unique=True)
    winner: Mapped[str] = mapped_column(String(4))
    win_condition: Mapped[str] = mapped_column(String(8))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    mvp_player_id: Mapped[int] = mapped_column(Integer)
    ace_player_id: Mapped[int] = mapped_column(Integer)
    blue_gold: Mapped[float] = mapped_column(Float)
    red_gold: Mapped[float] = mapped_column(Float)
    seed: Mapped[int] = mapped_column(Integer)
    simulation_version: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MatchEventRow(Base):
    __tablename__ = "match_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(12))
    minute: Mapped[float] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSONType)

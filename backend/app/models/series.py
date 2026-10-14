from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base


class Series(Base):
    """A best-of-N series: one Game row per game played. The score is derived from the games' results,
    so nothing here changes once the series is created."""
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    format: Mapped[str] = mapped_column(String(4))            # "BO3" | "BO5"
    wins_needed: Mapped[int] = mapped_column(Integer)
    # hard fearless: a champion picked in an earlier game cannot be picked or banned again in the series
    fearless: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

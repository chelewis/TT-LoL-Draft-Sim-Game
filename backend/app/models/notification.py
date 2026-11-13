"""A user's notifications: things that need them (your match is ready, you're on the clock, a deadline is near).

`key` stops the same notification being sent twice (e.g. one deadline warning per round); NULL keys never clash.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(300), default="")
    link: Mapped[str] = mapped_column(String(200), default="")         # where it takes you in the app
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    key: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)

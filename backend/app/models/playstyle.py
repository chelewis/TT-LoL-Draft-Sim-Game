from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base, JSONType


class PlaystyleTag(Base):
    """A playstyle tag admins manage: how a Riot account earns it (`source` + `rule`) and what it does in the
    simulation (`effects`: [{hook, value}], hooks from game.config.PLAYSTYLE_HOOKS)."""
    __tablename__ = "playstyle_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")
    polarity: Mapped[str] = mapped_column(String(8))          # positive / negative
    source: Mapped[str] = mapped_column(String(10))           # challenge / match
    rule: Mapped[dict] = mapped_column(JSONType, default=dict)
    effects: Mapped[list] = mapped_column(JSONType, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

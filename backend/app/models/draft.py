from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DraftActionRow(Base):
    __tablename__ = "draft_actions"
    __table_args__ = (UniqueConstraint("game_id", "action_number"), UniqueConstraint("game_id", "champion_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    action_number: Mapped[int] = mapped_column(Integer)
    team: Mapped[str] = mapped_column(String(4))
    action_type: Mapped[str] = mapped_column(String(4))
    champion_id: Mapped[int] = mapped_column(ForeignKey("champions.id"))
    auto: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

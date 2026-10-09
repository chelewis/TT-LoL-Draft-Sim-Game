from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base


class ChampionMatchup(Base):
    """One cell of a champion x champion win rate matrix, stored once per pair with champion_a_id < champion_b_id.

    kind "ally": the pair's win rate when on the same team (the same either way round).
    kind "enemy": champion A's win rate against champion B (B against A is 100 minus it).
    """
    __tablename__ = "champion_matchups"
    __table_args__ = (UniqueConstraint("kind", "champion_a_id", "champion_b_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)
    champion_a_id: Mapped[int] = mapped_column(ForeignKey("champions.id"), index=True)
    champion_b_id: Mapped[int] = mapped_column(ForeignKey("champions.id"), index=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)     # percent; NULL = no data
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)                    # for "enemy": champion A's wins
    edited: Mapped[bool] = mapped_column(Boolean, default=False)             # changed by an admin since seeding
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base
from app.game.models import Champion as EngineChampion


class Champion(Base):
    __tablename__ = "champions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    champ_class: Mapped[str] = mapped_column(String(32))
    style: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer)
    damage_type: Mapped[str] = mapped_column(String(2))
    damage: Mapped[int] = mapped_column(Integer)
    sturdiness: Mapped[int] = mapped_column(Integer)
    crowd_control: Mapped[int] = mapped_column(Integer)
    mobility: Mapped[int] = mapped_column(Integer)
    utility: Mapped[int] = mapped_column(Integer)
    win_rate: Mapped[float] = mapped_column(Float, default=50.0)
    pick_rate: Mapped[float] = mapped_column(Float, default=0.0)
    scaling: Mapped[int] = mapped_column(Integer, default=2)
    attack_range: Mapped[int] = mapped_column(Integer, default=2)
    waveclear: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def to_engine(self) -> EngineChampion:
        return EngineChampion(self.id, self.name, self.champ_class, self.style, self.difficulty,
                              self.damage_type, self.damage, self.sturdiness, self.crowd_control,
                              self.mobility, self.utility, self.win_rate, self.pick_rate, self.scaling,
                              self.attack_range, self.waveclear)

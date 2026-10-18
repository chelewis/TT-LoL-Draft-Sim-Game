from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base, JSONType


class SimulationSettings(Base):
    """Admin changes to the simulation config: a single row of overrides merged over SIMULATION_CONFIG.
    No row (or an empty dict) means every setting is at its default."""
    __tablename__ = "simulation_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    overrides: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.core.database import Base


class Coach(Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    draft: Mapped[int] = mapped_column(Integer)
    synergy: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PlayerPoolEntry(Base):
    __tablename__ = "player_champion_pools"
    __table_args__ = (UniqueConstraint("player_id", "position"), UniqueConstraint("player_id", "champion_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)  # 1 = best
    champion_id: Mapped[int] = mapped_column(ForeignKey("champions.id"))


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(10))
    secondary_role: Mapped[str | None] = mapped_column(String(10))   # optional second lane they can be rostered in
    age: Mapped[int] = mapped_column(Integer, default=20)
    region: Mapped[str] = mapped_column(String(16), default="")
    aggr: Mapped[int] = mapped_column(Integer)
    aware: Mapped[int] = mapped_column(Integer)
    pos: Mapped[int] = mapped_column(Integer)
    dmg: Mapped[int] = mapped_column(Integer)
    cs: Mapped[int] = mapped_column(Integer)
    # set when the player was built from a real Riot account (unverified: anyone can import any Riot ID)
    riot_puuid: Mapped[str | None] = mapped_column(String(96), index=True)
    riot_game_name: Mapped[str | None] = mapped_column(String(32))
    riot_tag_line: Mapped[str | None] = mapped_column(String(16))
    riot_region: Mapped[str | None] = mapped_column(String(8))
    riot_data_source: Mapped[str | None] = mapped_column(String(8))   # SOLO / FLEX / NORMAL: which queue the stats came from
    riot_games_used: Mapped[int | None] = mapped_column(Integer)
    # rank at import time, used to scale the imported stats; all null when the account was unranked
    riot_rank_queue: Mapped[str | None] = mapped_column(String(8))    # SOLO / FLEX: which queue the rank is from
    riot_rank_tier: Mapped[str | None] = mapped_column(String(12))
    riot_rank_division: Mapped[str | None] = mapped_column(String(4))
    riot_rank_lp: Mapped[int | None] = mapped_column(Integer)
    riot_rank_wins: Mapped[int | None] = mapped_column(Integer)
    riot_rank_losses: Mapped[int | None] = mapped_column(Integer)
    riot_imported_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    pool_entries: Mapped[list[PlayerPoolEntry]] = relationship(
        order_by=PlayerPoolEntry.position, cascade="all, delete-orphan", lazy="selectin")

    @property
    def pool(self) -> list[int]:
        return [e.champion_id for e in self.pool_entries]

    @property
    def stat_total(self) -> int:
        return self.aggr + self.aware + self.pos + self.dmg + self.cs

    def plays(self, lane: str) -> bool:
        """Whether this lane is the player's primary or secondary role."""
        return lane in (self.role, self.secondary_role)


class TeamRosterSlot(Base):
    __tablename__ = "team_rosters"
    __table_args__ = (UniqueConstraint("team_id", "lane"), UniqueConstraint("team_id", "player_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    lane: Mapped[str] = mapped_column(String(10))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    logo: Mapped[str] = mapped_column(String(8), default="")
    region: Mapped[str] = mapped_column(String(16), default="")
    fanbase: Mapped[str] = mapped_column(String(16), default="")
    style1: Mapped[str | None] = mapped_column(String(12))
    style2: Mapped[str | None] = mapped_column(String(12))
    focus1: Mapped[str | None] = mapped_column(String(10))
    focus2: Mapped[str | None] = mapped_column(String(10))
    coach_id: Mapped[int | None] = mapped_column(ForeignKey("coaches.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    slots: Mapped[list[TeamRosterSlot]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    coach: Mapped[Coach | None] = relationship(lazy="selectin")

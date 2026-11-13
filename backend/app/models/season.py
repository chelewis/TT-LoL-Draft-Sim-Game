"""Seasons: leagues and tournaments where each user manages one team across many matches.

A season owns frozen copies of every team that plays in it (Team, Player and Coach rows with `season_id` set),
so edits outside the season never change it. CPU teams are generated into the season the same way.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base, JSONType

SEASON_STATUSES = ("SETUP", "PLAYER_DRAFT", "REGULAR", "PLAYOFFS", "COMPLETED", "CANCELLED")
MATCH_STATUSES = ("SCHEDULED", "LIVE", "COMPLETED")


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    code: Mapped[str] = mapped_column(String(6), unique=True, index=True)    # invite code
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="SETUP", index=True)
    roster_mode: Mapped[str] = mapped_column(String(8), default="BYO")        # BYO | DRAFT
    format: Mapped[str] = mapped_column(String(12), default="ROUND_ROBIN")    # ROUND_ROBIN | SWISS
    # {"rules": lobby options (rulesets, draft options), plus the season options (team_count, series lengths...)}
    settings: Mapped[dict] = mapped_column(JSONType)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    round_deadline_at: Mapped[datetime | None] = mapped_column(DateTime)
    pick_deadline_at: Mapped[datetime | None] = mapped_column(DateTime)       # Player Draft: the pick clock
    winner_team_id: Mapped[int | None] = mapped_column(Integer)               # the champion's SeasonTeam id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class SeasonTeam(Base):
    """A team entered in a season: a season-owned Team copy, managed by a user or (manager None) the CPU."""
    __tablename__ = "season_teams"
    __table_args__ = (UniqueConstraint("season_id", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    eliminated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    draft_position: Mapped[int | None] = mapped_column(Integer)               # Player Draft: 1 picks first
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SeasonMatch(Base):
    """A fixture: two season teams playing a best-of series. Each game played is a Game row with
    `season_match_id` set (live games through the normal draft, or auto-played by the CPU for both sides)."""
    __tablename__ = "season_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(8), default="REGULAR")          # REGULAR | SWISS | PLAYOFF
    round: Mapped[int] = mapped_column(Integer)
    slot: Mapped[int] = mapped_column(Integer, default=0)                     # order within the round / bracket
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("season_teams.id"))   # Blue in game 1
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("season_teams.id"))
    format: Mapped[str] = mapped_column(String(3), default="BO1")
    status: Mapped[str] = mapped_column(String(10), default="SCHEDULED", index=True)
    played_mode: Mapped[str | None] = mapped_column(String(4))                # LIVE | AUTO (how it was decided)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"))
    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("season_teams.id"))
    # human vs human: each manager asks to auto-sim; it runs once both have (Phase 3)
    home_auto_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    away_auto_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class SeasonDraftPick(Base):
    """Player Draft: one pick, in order. The player joins the team's roster in `lane`."""
    __tablename__ = "season_draft_picks"
    __table_args__ = (UniqueConstraint("season_id", "pick_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    pick_number: Mapped[int] = mapped_column(Integer)                         # 1, 2, 3...
    season_team_id: Mapped[int] = mapped_column(ForeignKey("season_teams.id", ondelete="CASCADE"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"))
    lane: Mapped[str] = mapped_column(String(10))
    auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())   # clock ran out / CPU
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SeasonTransaction(Base):
    """Free agency: a signing (SIGN) and the player it replaced (RELEASE), logged per team."""
    __tablename__ = "season_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    season_team_id: Mapped[int] = mapped_column(ForeignKey("season_teams.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(8))                              # SIGN | RELEASE
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"))
    player_name: Mapped[str] = mapped_column(String(40))                      # kept for the log
    lane: Mapped[str] = mapped_column(String(10))
    stage: Mapped[str] = mapped_column(String(8))
    round: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

from __future__ import annotations

from datetime import datetime

from sqlalchemy import false as sa_false
from sqlalchemy import true as sa_true
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.database import Base, JSONType

STATUSES = ("WAITING_FOR_PLAYERS", "TEAM_SELECTION", "READY_CHECK", "DRAFTING", "LANE_ASSIGNMENT",
            "READY_TO_SIMULATE", "SIMULATING", "COMPLETED", "CANCELLED")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (UniqueConstraint("series_id", "game_number"),)   # never two "game 2"s in one series

    id: Mapped[int] = mapped_column(primary_key=True)
    lobby_id: Mapped[int] = mapped_column(ForeignKey("lobbies.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="WAITING_FOR_PLAYERS", index=True)
    blue_player_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    red_player_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    blue_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    red_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    hide_player_data: Mapped[bool] = mapped_column(Boolean, default=False)
    # single player: one user holds both seats and makes every pick, ban and lineup decision for both sides
    is_solo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    # vs CPU: the user holds one seat; the other seat (player id None) is played by the CPU (game/draft_ai.py)
    vs_cpu: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    bans_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_true())
    timers_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_true())
    pick_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    ban_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    # best-of series: game_number counts from 1; sides_swapped says Blue/Red are flipped relative to game 1
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), index=True)
    game_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sides_swapped: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    blue_next_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    red_next_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    next_loser_side: Mapped[str | None] = mapped_column(String(4))   # side the loser chose for the next game
    blue_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    red_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    blue_lineup_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    red_lineup_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_phase: Mapped[str | None] = mapped_column(String(16))
    current_action: Mapped[int] = mapped_column(Integer, default=0)
    action_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    action_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    # champion the acting side has hovered for the current action; locked in instead of a random one on timeout
    hovered_champion_id: Mapped[int | None] = mapped_column(Integer)
    seed: Mapped[int | None] = mapped_column(Integer)
    simulation_version: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GameTeamSnapshot(Base):
    """Frozen copy of a team (roster, players, pools, coach) taken when the game leaves team selection."""
    __tablename__ = "game_team_snapshots"
    __table_args__ = (UniqueConstraint("game_id", "team"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    team: Mapped[str] = mapped_column(String(4))
    snapshot: Mapped[dict] = mapped_column(JSONType)


class TeamLineup(Base):
    __tablename__ = "team_lineups"
    __table_args__ = (UniqueConstraint("game_id", "team", "lane"), UniqueConstraint("game_id", "team", "champion_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    team: Mapped[str] = mapped_column(String(4))
    lane: Mapped[str] = mapped_column(String(10))
    champion_id: Mapped[int] = mapped_column(ForeignKey("champions.id"))
    player_id: Mapped[int] = mapped_column(Integer)


class ChatMessage(Base):
    """All-chat between the two players of a game."""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team: Mapped[str] = mapped_column(String(4))
    body: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

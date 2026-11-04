from __future__ import annotations

from pydantic import BaseModel, Field


class LobbySettings(BaseModel):
    hide_player_data: bool = False
    bans_enabled: bool = True          # False skips every ban phase (picks only)
    timers_enabled: bool = True        # False means no time limit on picks and bans
    pick_seconds: int = Field(default=30, ge=5, le=600)
    ban_seconds: int = Field(default=30, ge=5, le=600)
    series_format: str = Field(default="BO1", pattern="^BO[135]$")   # best of 1, 3 or 5
    fearless: bool = False             # fearless draft across a series; ignored for best of 1


class LobbyCreate(BaseModel):
    settings: LobbySettings = Field(default_factory=LobbySettings)
    mode: str = Field(default="MULTI", pattern="^(MULTI|SOLO|CPU)$")  # SOLO: you control both sides; CPU: vs the CPU


class SideSelect(BaseModel):
    side: str  # "BLUE" | "RED"


class TeamSelect(BaseModel):
    team_id: int
    side: str | None = None        # BLUE or RED; required in single player


class ReadyIn(BaseModel):
    ready: bool = True


class SeriesReadyIn(BaseModel):
    ready: bool = True
    side: str | None = None        # the side the previous game's loser takes next game (required from the loser)


class DraftActionIn(BaseModel):
    champion_id: int


class DraftHoverIn(BaseModel):
    champion_id: int | None
    draft_action: int   # the action the hover is for; a stale hover for an earlier action is ignored


class LaneAssignment(BaseModel):
    lane: str
    champion_id: int
    player_id: int | None = None   # who plays the lane; defaults to the roster player for that lane


class LineupIn(BaseModel):
    assignments: list[LaneAssignment]
    side: str | None = None        # required in single player


class ChatIn(BaseModel):
    text: str = Field(max_length=1000)   # trimmed and checked against the real limit by the service

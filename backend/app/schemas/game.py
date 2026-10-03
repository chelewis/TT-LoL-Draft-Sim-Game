from __future__ import annotations

from pydantic import BaseModel, Field


class LobbySettings(BaseModel):
    hide_player_data: bool = False
    bans_enabled: bool = True          # False skips every ban phase (picks only)
    timers_enabled: bool = True        # False means no time limit on picks and bans
    pick_seconds: int = Field(default=30, ge=5, le=600)
    ban_seconds: int = Field(default=30, ge=5, le=600)


class LobbyCreate(BaseModel):
    settings: LobbySettings = Field(default_factory=LobbySettings)
    mode: str = Field(default="MULTI", pattern="^(MULTI|SOLO)$")     # SOLO: you control both sides


class SideSelect(BaseModel):
    side: str  # "BLUE" | "RED"


class TeamSelect(BaseModel):
    team_id: int
    side: str | None = None        # BLUE or RED; required in single player


class ReadyIn(BaseModel):
    ready: bool = True


class DraftActionIn(BaseModel):
    champion_id: int


class LaneAssignment(BaseModel):
    lane: str
    champion_id: int


class LineupIn(BaseModel):
    assignments: list[LaneAssignment]
    side: str | None = None        # required in single player

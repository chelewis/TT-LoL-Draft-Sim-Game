from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Lane = Literal["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"]


class PlayerIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    role: str
    secondary_role: str | None = None
    age: int = Field(default=20, ge=16, le=99)
    region: str = Field(default="", max_length=16)
    aggr: int
    aware: int
    pos: int
    dmg: int
    cs: int
    pool: list[int]
    riot_ref: str | None = None   # opaque token from /riot/preview linking this player to a Riot account
    # playstyle tag keys to keep (each earned by the linked Riot account); None keeps the current ones, or the
    # suggested ones when `riot_ref` is a new import
    tags: list[str] | None = Field(default=None, max_length=10)


class TeamInsightsIn(BaseModel):
    """The team editor's current (possibly unsaved) choices."""
    style1: str | None = None
    style2: str | None = None
    focus1: str | None = None
    focus2: str | None = None
    coach_id: int | None = None
    roster: dict[str, int | None] = Field(default_factory=dict)  # lane -> player id


class ChampionFitIn(BaseModel):
    """Unsaved player stats and pool from the editor; only the stats the lane formula uses."""
    aggr: int = Field(ge=1, le=10)
    aware: int = Field(ge=1, le=10)
    pos: int = Field(ge=1, le=10)
    dmg: int = Field(ge=1, le=10)
    pool: list[int] = Field(default_factory=list, max_length=5)
    limit: int | None = Field(default=10, ge=1)   # None: every enabled champion
    role: Lane | None = None             # the player's lanes; with neither, no off-role penalty is applied
    secondary_role: Lane | None = None


class CoachIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    draft: int
    synergy: int


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    logo: str = Field(default="", max_length=8)
    region: str = Field(default="", max_length=16)
    fanbase: str = Field(default="", max_length=16)
    style1: str | None = None
    style2: str | None = None
    focus1: str | None = None
    focus2: str | None = None
    coach_id: int | None = None
    roster: dict[str, int | None] = Field(default_factory=dict)  # lane -> player id


class RiotPreviewIn(BaseModel):
    riot_id: str = Field(min_length=3, max_length=40)   # "GameName#TAG"
    region: str = Field(default="NA1", max_length=6)
    role: str | None = None                              # optional lane override

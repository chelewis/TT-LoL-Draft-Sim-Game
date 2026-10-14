from __future__ import annotations

from pydantic import BaseModel, Field


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

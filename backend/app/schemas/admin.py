from __future__ import annotations

from pydantic import BaseModel, Field


class MatchupChange(BaseModel):
    a: int                                                      # row champion id
    b: int                                                      # column champion id
    win_rate: float | None = Field(default=None, ge=0, le=100)  # percent; null clears the cell


class MatchupChangesIn(BaseModel):
    changes: list[MatchupChange] = Field(min_length=1, max_length=20000)


class SimulationSettingsIn(BaseModel):
    values: dict[str, bool | float] = Field(min_length=1, max_length=200)  # dotted config path -> new value


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)   # same rule as sign-up


class PlaystyleEffectIn(BaseModel):
    hook: str = Field(max_length=32)
    value: float


class PlaystyleTagIn(BaseModel):
    key: str = Field(min_length=2, max_length=32)
    label: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=400)
    polarity: str
    source: str
    rule: dict
    effects: list[PlaystyleEffectIn] = Field(max_length=4)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)

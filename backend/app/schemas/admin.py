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

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.game import LobbySettings

SERIES = "^BO[135]$"
PLAYOFF_SIZES = (0, 2, 4, 8)
SWISS_SIZES = (8, 16)            # a Swiss stage needs a power of two teams: 8 (2 wins / 2 losses) or 16 (3 / 3)


class SeasonOptions(BaseModel):
    """How the competition runs. The match rules (rulesets, draft options) are the lobby options in `rules`."""
    team_count: int = Field(default=8, ge=4, le=16)
    human_slots: int = Field(default=1, ge=1, le=16)       # teams users can manage; the CPU runs the rest
    rr_double: bool = False                                # round robin: everyone plays everyone twice
    regular_series: str = Field(default="BO1", pattern=SERIES)     # round robin and Swiss matches
    cpu_strength: str = Field(default="EVEN", pattern="^(WEAKER|EVEN|STRONGER)$")
    # single-elimination playoffs after the round robin: the top N of the table (0: no playoffs, the table decides).
    # A Swiss stage always ends in a bracket of the teams that qualify (half the field).
    playoff_size: int = Field(default=0)
    playoff_series: str = Field(default="BO3", pattern=SERIES)
    final_series: str = Field(default="BO5", pattern=SERIES)
    # a round closes by itself this many hours after it opens: the CPU plays what managers haven't (0: no deadline)
    round_deadline_hours: int = Field(default=0, ge=0, le=336)

    @model_validator(mode="after")
    def _slots_fit(self) -> "SeasonOptions":
        if self.human_slots > self.team_count:
            raise ValueError("There can't be more manager slots than teams.")
        if self.playoff_size not in PLAYOFF_SIZES:
            raise ValueError("Playoffs can have 2, 4 or 8 teams (or none).")
        if self.playoff_size > self.team_count:
            raise ValueError("The playoffs can't have more teams than the league.")
        return self


class SeasonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    roster_mode: str = Field(default="BYO", pattern="^(BYO|DRAFT)$")    # bring your own team | player draft
    format: str = Field(default="ROUND_ROBIN", pattern="^(ROUND_ROBIN|SWISS)$")
    rules: LobbySettings = Field(default_factory=LobbySettings)
    options: SeasonOptions = Field(default_factory=SeasonOptions)

    @model_validator(mode="after")
    def _swiss_size(self) -> "SeasonCreate":
        if self.format == "SWISS" and self.options.team_count not in SWISS_SIZES:
            raise ValueError("A Swiss stage needs 8 or 16 teams.")
        return self


class SeasonTeamIn(BaseModel):
    team_id: int        # one of your teams (or a default team): a frozen copy of it enters the season


class AdvanceIn(BaseModel):
    force: bool = False  # auto-sim matches managers haven't played yet


class SeasonJoinIn(BaseModel):
    team_id: int        # the team you bring (see SeasonTeamIn)


class AutoSimIn(BaseModel):
    ready: bool = True  # between two managers: ask for (or take back) letting the CPU play the match

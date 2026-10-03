"""Pick/ban draft state machine (spec 7-9). Pure Python, no framework imports."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable


class DraftError(ValueError):
    """Raised when a draft action is illegal. Message is safe to show to users."""


@dataclass(frozen=True)
class DraftAction:
    index: int
    team: str         # "BLUE" | "RED"
    action_type: str  # "PICK" | "BAN"


def parse_actions(actions: Iterable[str]) -> list[DraftAction]:
    parsed = []
    for i, raw in enumerate(actions):
        team, _, kind = raw.partition("_")
        if team not in ("BLUE", "RED") or kind not in ("PICK", "BAN"):
            raise ValueError(f"Invalid draft action {raw!r}")
        parsed.append(DraftAction(i, team, kind))
    return parsed


@dataclass
class DraftState:
    """Mutable draft progress. `available` is derived from the champion pool minus used ids."""
    sequence: list[DraftAction]
    champion_ids: frozenset[int]
    bans: list[tuple[str, int]] = field(default_factory=list)       # (team, champion_id)
    picks: dict[str, list[int]] = field(default_factory=lambda: {"BLUE": [], "RED": []})
    history: list[tuple[int, str, str, int, bool]] = field(default_factory=list)
    # history entries: (action_index, team, action_type, champion_id, auto)

    @property
    def cursor(self) -> int:
        return len(self.history)

    @property
    def complete(self) -> bool:
        return self.cursor >= len(self.sequence)

    @property
    def current(self) -> DraftAction | None:
        return None if self.complete else self.sequence[self.cursor]

    @property
    def used(self) -> set[int]:
        used = {cid for _, cid in self.bans}
        for ids in self.picks.values():
            used.update(ids)
        return used

    def available(self) -> list[int]:
        used = self.used
        return sorted(cid for cid in self.champion_ids if cid not in used)

    def validate(self, team: str, action_type: str, champion_id: int) -> DraftAction:
        action = self.current
        if action is None:
            raise DraftError("The draft is already complete.")
        if action.team != team:
            raise DraftError("It is not your turn.")
        if action.action_type != action_type:
            raise DraftError(f"The current action is a {action.action_type.lower()}, not a {action_type.lower()}.")
        if champion_id not in self.champion_ids:
            raise DraftError("Unknown or disabled champion.")
        if champion_id in self.used:
            raise DraftError("That champion has already been picked or banned.")
        return action

    def apply(self, team: str, action_type: str, champion_id: int, auto: bool = False) -> DraftAction:
        action = self.validate(team, action_type, champion_id)
        if action_type == "BAN":
            self.bans.append((team, champion_id))
        else:
            self.picks[team].append(champion_id)
        self.history.append((action.index, team, action_type, champion_id, auto))
        return action

    def auto_action(self, rng: random.Random) -> tuple[DraftAction, int]:
        """Apply a random legal action for the team whose turn it is (timeout behaviour)."""
        action = self.current
        if action is None:
            raise DraftError("The draft is already complete.")
        pool = self.available()
        if not pool:
            raise DraftError("No champions are available.")
        champion_id = rng.choice(pool)
        self.apply(action.team, action.action_type, champion_id, auto=True)
        return action, champion_id

    @property
    def banned_ids(self) -> list[int]:
        return [cid for _, cid in self.bans]


def new_draft(actions: Iterable[str], champion_ids: Iterable[int]) -> DraftState:
    return DraftState(sequence=parse_actions(actions), champion_ids=frozenset(champion_ids))


def rebuild_draft(actions: Iterable[str], champion_ids: Iterable[int],
                  history: Iterable[tuple[str, str, int, bool]]) -> DraftState:
    """Rebuild a draft from persisted (team, action_type, champion_id, auto) rows in order."""
    state = new_draft(actions, champion_ids)
    for team, action_type, champion_id, auto in history:
        state.apply(team, action_type, champion_id, auto=auto)
    return state

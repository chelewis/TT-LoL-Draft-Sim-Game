"""Towers, inhibitors and nexus for one team (spec 9.11).

Per team: for each of TOP, MID, BOT a chain tower1 -> tower2 -> tower3 -> inhibitor;
two nexus towers (attackable once any inhibitor is down); the nexus (attackable once both
nexus towers are down).  3 lanes x 3 + 2 nexus towers = 11 towers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STRUCTURE_LANES = ("TOP", "MID", "BOT")


@dataclass
class TeamStructures:
    towers_per_lane: int = 3
    nexus_towers: int = 2
    towers_down: dict[str, int] = field(default_factory=lambda: {l: 0 for l in STRUCTURE_LANES})
    inhib_down: dict[str, bool] = field(default_factory=lambda: {l: False for l in STRUCTURE_LANES})
    nexus_towers_down: int = 0
    nexus_destroyed: bool = False

    # ---- queries ----
    def next_lane_structure(self, lane: str) -> str | None:
        if self.towers_down[lane] < self.towers_per_lane:
            return "tower"
        if not self.inhib_down[lane]:
            return "inhibitor"
        return None

    def lanes_with_tower(self) -> list[str]:
        return [l for l in STRUCTURE_LANES if self.next_lane_structure(l) == "tower"]

    def lanes_with_structure(self) -> list[str]:
        return [l for l in STRUCTURE_LANES if self.next_lane_structure(l) is not None]

    @property
    def inhibitors_down(self) -> int:
        return sum(1 for v in self.inhib_down.values() if v)

    @property
    def nexus_towers_unlocked(self) -> bool:
        return self.inhibitors_down > 0 and self.nexus_towers_down < self.nexus_towers

    @property
    def nexus_unlocked(self) -> bool:
        return self.inhibitors_down > 0 and self.nexus_towers_down >= self.nexus_towers and not self.nexus_destroyed

    @property
    def lane_towers_down(self) -> int:
        return sum(self.towers_down.values())

    @property
    def total_towers_down(self) -> int:
        return self.lane_towers_down + self.nexus_towers_down

    @property
    def total_towers(self) -> int:
        return self.towers_per_lane * len(STRUCTURE_LANES) + self.nexus_towers

    # ---- mutations (each returns the structure kind destroyed) ----
    def destroy_lane_structure(self, lane: str) -> str:
        kind = self.next_lane_structure(lane)
        if kind == "tower":
            self.towers_down[lane] += 1
        elif kind == "inhibitor":
            self.inhib_down[lane] = True
        else:
            raise ValueError(f"No structure left in lane {lane}")
        return kind

    def destroy_nexus_tower(self) -> str:
        if not self.nexus_towers_unlocked:
            raise ValueError("Nexus towers are not attackable yet")
        self.nexus_towers_down += 1
        return "nexus_tower"

    def destroy_nexus(self) -> str:
        if not self.nexus_unlocked:
            raise ValueError("The nexus is not attackable yet")
        self.nexus_destroyed = True
        return "nexus"

    def score(self, weights: dict[str, int]) -> int:
        """Weighted count of destroyed structures (used by the timeout tiebreaker)."""
        return (self.lane_towers_down * weights["tower"]
                + self.inhibitors_down * weights["inhibitor"]
                + self.nexus_towers_down * weights["nexus_tower"])

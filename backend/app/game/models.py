"""Plain data types used by the game engine. No framework or database imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Matchup wheel: key beats value.
FAVOURABLE = {"Offence": "Defence", "Defence": "Control", "Control": "Offence"}
ATTRIBUTE_ORDER = ("Offence", "Defence", "Control")


@dataclass(frozen=True)
class Champion:
    id: int
    name: str
    champ_class: str
    style: int
    difficulty: int
    damage_type: str  # "P", "M" or "PM"
    damage: int
    sturdiness: int
    cc: int
    mobility: int
    utility: int
    win_rate: float = 50.0
    pick_rate: float = 0.0
    scaling: int = 2  # 1 early game, 2 neutral, 3 late game
    attack_range: int = 2  # 1 melee, 2 short range, 3 long range
    waveclear: int = 2  # 1 weak, 2 average, 3 strong

    @property
    def offence(self) -> int:
        return self.damage + self.mobility

    @property
    def defence(self) -> int:
        return self.sturdiness + self.cc

    @property
    def control(self) -> int:
        return self.utility + self.cc

    def attribute(self, kind: str) -> int:
        return {"Offence": self.offence, "Defence": self.defence, "Control": self.control}[kind]

    @property
    def strength(self) -> str:
        """Highest of Offence / Defence / Control (ties: Offence > Defence > Control)."""
        best = max(ATTRIBUTE_ORDER, key=lambda k: (self.attribute(k), -ATTRIBUTE_ORDER.index(k)))
        return best

    @property
    def weakness(self) -> str:
        """The type that beats this champion's strength."""
        s = self.strength
        return next(k for k, v in FAVOURABLE.items() if v == s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "class": self.champ_class, "style": self.style,
            "difficulty": self.difficulty, "damage_type": self.damage_type,
            "damage": self.damage, "sturdiness": self.sturdiness, "crowd_control": self.cc,
            "mobility": self.mobility, "utility": self.utility,
            "win_rate": self.win_rate, "pick_rate": self.pick_rate, "scaling": self.scaling,
            "range": self.attack_range, "waveclear": self.waveclear,
            "offence": self.offence, "defence": self.defence, "control": self.control,
            "strength": self.strength, "weakness": self.weakness,
        }


@dataclass(frozen=True)
class PlayerSpec:
    id: int
    name: str
    role: str  # lane name
    age: int
    aggr: int
    aware: int
    pos: int
    dmg: int
    cs: int
    pool: tuple[int, ...]  # ordered champion ids, best first
    tag_effects: tuple[tuple[str, float], ...] = ()  # (hook, value) from the player's playstyle tags

    @property
    def stat_total(self) -> int:
        return self.aggr + self.aware + self.pos + self.dmg + self.cs


@dataclass(frozen=True)
class CoachSpec:
    id: int
    name: str
    draft: int
    synergy: int


@dataclass
class TeamSetup:
    """A fully drafted team ready to simulate.

    roster: lane -> PlayerSpec. lineup: lane -> champion id (assigned to that lane's player).
    styles: up to two of early/scaling/teamfight/skirmish. focus: up to two lane names.
    """
    id: int
    name: str
    styles: tuple[str, ...]
    focus: tuple[str, ...]
    coach: CoachSpec
    roster: dict[str, PlayerSpec]
    lineup: dict[str, int]


@dataclass(frozen=True)
class MatchupTable:
    """The champion x champion win rate matrices, one percent per pair keyed (a, b) with a < b.

    ally: the pair's win rate on the same team. enemy: champion a's win rate against champion b.
    A pair that is not in the dict has no data.
    """
    ally: dict[tuple[int, int], float] = field(default_factory=dict)
    enemy: dict[tuple[int, int], float] = field(default_factory=dict)

    def ally_rate(self, a: int, b: int) -> float | None:
        return self.ally.get((a, b) if a < b else (b, a))

    def enemy_rate(self, a: int, b: int) -> float | None:
        """Champion a's win rate against champion b."""
        if a < b:
            return self.enemy.get((a, b))
        rate = self.enemy.get((b, a))
        return None if rate is None else 100.0 - rate


@dataclass
class MatchEvent:
    sequence: int
    phase: str
    minute: float
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "phase": self.phase, "minute": round(self.minute, 2),
                "type": self.type, "payload": self.payload}


@dataclass
class MatchResult:
    simulation_version: str
    seed: int
    winner: str  # "BLUE" | "RED"
    win_condition: str  # "NEXUS" | "TIMEOUT"
    duration_seconds: int
    mvp: dict[str, Any]
    ace: dict[str, Any]
    teams: dict[str, dict[str, Any]]
    lanes: dict[str, dict[str, Any]]
    players: list[dict[str, Any]]
    events: list[MatchEvent]

    def to_dict(self, include_events: bool = True) -> dict[str, Any]:
        out = {
            "simulation_version": self.simulation_version,
            "seed": self.seed,
            "winner": self.winner,
            "win_condition": self.win_condition,
            "duration_seconds": self.duration_seconds,
            "mvp": self.mvp,
            "ace": self.ace,
            "teams": self.teams,
            "lanes": self.lanes,
            "players": self.players,
            "events_available": True,
        }
        if include_events:
            out["events"] = [e.to_dict() for e in self.events]
        return out

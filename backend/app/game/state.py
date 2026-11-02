"""Mutable per-match state shared by the simulation modules. One `Match` per simulation:
there is no module-level state, so two simulations in one process cannot interfere."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .comfort import comfort_modifier, comfort_tier
from .config import LANES
from .models import Champion, CoachSpec, MatchEvent, MatchupTable, PlayerSpec, TeamSetup
from .playstyle import adjust_comfort, effect_totals
from .range_waveclear import waveclear_priority
from .structures import TeamStructures

PHASE_SCALING_WEIGHT = {"lane": 0.0, "early": 0.0, "mid": 0.5, "late": 1.0, "overtime": 1.0}


@dataclass
class PlayerState:
    lane: str
    spec: PlayerSpec
    champion: Champion
    tier: str
    comfort: float
    team: str
    matchup_label: str | None = None
    matchup_multiplier: float = 1.0
    base_score: float = 0.0
    lane_score: float = 0.0
    # lane score without the lane phase's champion scaling, as a share of lane_score (fights use it)
    lane_unscaled_ratio: float = 1.0
    cs: float = 0.0
    cs_rate: float = 0.0  # CS per minute from here on
    gold: float = 0.0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    damage_dealt: int = 0
    damage_taken: int = 0
    tags: dict[str, float] = field(default_factory=dict)  # playstyle hook -> combined value

    def tag(self, hook: str) -> float:
        return self.tags.get(hook, 0.0)


@dataclass
class TeamState:
    side: str  # "BLUE" | "RED"
    setup: TeamSetup
    players: dict[str, PlayerState]
    structures: TeamStructures
    synergy_factor: float
    dragons: int = 0
    soul: bool = False
    elder_fights: int = 0
    barons: int = 0
    power_play: bool = False
    kills: int = 0
    fights_won: int = 0

    @property
    def gold(self) -> float:
        return sum(p.gold for p in self.players.values())

    @property
    def coach(self) -> CoachSpec:
        return self.setup.coach

    @property
    def name(self) -> str:
        return self.setup.name

    def ordered_players(self) -> list[PlayerState]:
        return [self.players[l] for l in LANES]

    def style_bonus(self, style: str, config: dict) -> float:
        """Bonus for one playstyle, scaled by the coach's Synergy."""
        ts = config["team_style"]
        if not ts["enabled"] or style not in self.setup.styles:
            return 0.0
        base = ts["primary_bonus"] if self.setup.styles.index(style) == 0 else ts["secondary_bonus"]
        return base * self.synergy_factor

    def damage_profile(self) -> dict[str, float]:
        return damage_profile(p.champion for p in self.players.values())

    def damage_balance_penalty(self, config: dict) -> float:
        return damage_balance_penalty(self.damage_profile(), config)


def damage_profile(champions: Iterable[Champion]) -> dict[str, float]:
    """Physical and magic damage points of a comp (PM champions count half to each)."""
    phys = magic = 0.0
    for c in champions:
        if c.damage_type == "P":
            phys += c.damage
        elif c.damage_type == "M":
            magic += c.damage
        else:
            phys += c.damage / 2
            magic += c.damage / 2
    return {"physical": round(phys, 1), "magic": round(magic, 1)}


def damage_balance_penalty(profile: dict[str, float], config: dict) -> float:
    """Fraction of fight damage lost to the enemy itemizing against a one-sided damage profile: 0 up to
    `threshold` share of the main type, rising linearly to `max_penalty` at 100%."""
    cfg = config["damage_balance"]
    if not cfg["enabled"]:
        return 0.0
    total = profile["physical"] + profile["magic"]
    if total <= 0:
        return 0.0
    share = max(profile.values()) / total
    threshold = cfg["threshold"]
    if share <= threshold or threshold >= 1.0:
        return 0.0
    return cfg["max_penalty"] * (share - threshold) / (1.0 - threshold)


class Match:
    def __init__(self, blue: TeamSetup, red: TeamSetup, champions: Mapping[int, Champion],
                 seed: int, config: dict, matchups: MatchupTable | None = None):
        self.config = config
        self.matchups = matchups or MatchupTable()
        self.seed = seed
        self.rng = random.Random(seed)
        self.events: list[MatchEvent] = []
        self.phase = "setup"
        self.minute = 0.0
        self.cs_minute = 0.0
        self.winner: str | None = None
        self.win_condition: str | None = None
        self.end_minute: float | None = None
        self.elementals_taken = 0
        # the minute each neutral objective is next alive
        self.next_dragon_at = float(self.config["objectives"]["dragon_first_spawn"])
        self.next_baron_at = float(self.config["objectives"]["baron_first_spawn"])
        self.teams: dict[str, TeamState] = {
            "BLUE": self._build_team("BLUE", blue, champions),
            "RED": self._build_team("RED", red, champions),
        }

    # ---- construction ----
    def _build_team(self, side: str, setup: TeamSetup, champions: Mapping[int, Champion]) -> TeamState:
        missing = [l for l in LANES if l not in setup.roster or l not in setup.lineup]
        if missing:
            raise ValueError(f"{side} team is missing lanes: {missing}")
        ids = [setup.lineup[l] for l in LANES]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{side} lineup contains a duplicate champion")
        st = self.config["structures"]
        players: dict[str, PlayerState] = {}
        for lane in LANES:
            spec = setup.roster[lane]
            try:
                champ = champions[setup.lineup[lane]]
            except KeyError as exc:
                raise ValueError(f"Unknown champion id {setup.lineup[lane]}") from exc
            tier = comfort_tier(spec, champ.id, self.config)
            tags = effect_totals(spec)
            comfort = adjust_comfort(comfort_modifier(tier, self.config), tier, tags)
            cs_rate = spec.cs * self.config["cs"]["role_factors"][lane] * (1.0 + tags.get("cs_rate", 0.0))
            players[lane] = PlayerState(lane, spec, champ, tier, comfort, side, cs_rate=cs_rate, tags=tags)
        synergy = 1.0 + (setup.coach.synergy - 5) * self.config["coach"]["synergy_scale"]
        return TeamState(side, setup, players,
                         TeamStructures(st["towers_per_lane"], st["nexus_towers"]), max(synergy, 0.0))

    # ---- helpers ----
    def other(self, team: TeamState) -> TeamState:
        return self.teams["RED" if team.side == "BLUE" else "BLUE"]

    @property
    def sides(self) -> tuple[TeamState, TeamState]:
        return self.teams["BLUE"], self.teams["RED"]

    def _event_gold(self) -> dict[str, list[int]]:
        """Each player's gold from everything except CS, per side in lane order. CS gold grows steadily with
        the clock, so a viewer can rebuild anyone's gold at any moment from this and the final result."""
        per_cs = self.config["economy"]["gold_per_cs"]
        return {side: [round(p.gold - p.cs * per_cs) for p in team.ordered_players()]
                for side, team in self.teams.items()}

    def emit(self, type_: str, **payload: Any) -> MatchEvent:
        payload["event_gold"] = self._event_gold()
        event = MatchEvent(len(self.events) + 1, self.phase, self.minute, type_, payload)
        self.events.append(event)
        return event

    def update_cs(self, minute: float) -> None:
        """Advance everyone's CS (and CS gold) to `minute`. Never moves backwards."""
        if minute <= self.cs_minute:
            return
        per_cs = self.config["economy"]["gold_per_cs"]
        for team in self.teams.values():
            for p in team.players.values():
                gained = p.cs_rate * (minute - self.cs_minute)
                p.cs += gained
                p.gold += gained * per_cs
        self.cs_minute = minute

    def lose_cs(self, p: PlayerState, minutes: float) -> float:
        """Take `minutes` of farm (and its gold) off a player, e.g. time spent dead. Returns the CS lost.
        Gold from everything else is untouched, so `event_gold` does not change."""
        lost = min(p.cs, p.cs_rate * minutes)
        p.cs -= lost
        p.gold -= lost * self.config["economy"]["gold_per_cs"]
        return lost

    # ---- derived strength ----
    def gold_factor(self, team: TeamState) -> float:
        """Objective-control multiplier from the current gold lead (gold = strength, spec 9.10)."""
        obj = self.config["objectives"]
        mine, theirs = team.gold, self.other(team).gold
        total = mine + theirs
        lead = 0.0 if total <= 0 else (mine - theirs) / total
        lead = max(-obj["gold_lead_cap"], min(obj["gold_lead_cap"], lead))
        return 1.0 + lead * obj["gold_control_scale"]

    def objective_control(self, team: TeamState, roll: bool = True, towers: bool = False) -> float:
        """(sum aware + sum pos) * roll, scaled by scaling-style, gold lead, waveclear (lane priority) and power
        play. Each player's share is scaled by their playstyle tags (`objective`, plus `tower` when contesting
        towers)."""
        base = sum((p.spec.aware + p.spec.pos) * (1.0 + p.tag("objective") + (p.tag("tower") if towers else 0.0))
                   for p in team.players.values())
        lo, hi = self.config["objectives"]["control_roll_range"]
        multiplier = self.rng.randint(lo, hi) if roll else (lo + hi) / 2
        value = base * multiplier
        value *= 1.0 + team.style_bonus("scaling", self.config) * PHASE_SCALING_WEIGHT.get(self.phase, 0.0)
        value *= self.gold_factor(team)
        value *= waveclear_priority({l: p.champion for l, p in team.players.items()}, self.config)
        if team.power_play:
            value += self.config["objectives"]["baron_power_play_bonus"]
        return value

    def control_ratio(self, team: TeamState, roll: bool = True, towers: bool = False) -> float:
        a = self.objective_control(team, roll, towers)
        b = self.objective_control(self.other(team), roll, towers)
        return a / (a + b) if a + b > 0 else 0.5

    def initiative_chance(self, team: TeamState) -> float:
        """Chance `team` starts the next fight, from its share of both teams' aggression."""
        f = self.config["fight"]
        mine = sum(p.spec.aggr * (1.0 + p.tag("initiative")) for p in team.players.values())
        theirs = sum(p.spec.aggr * (1.0 + p.tag("initiative")) for p in self.other(team).players.values())
        share = mine / (mine + theirs) if mine + theirs > 0 else 0.5
        lo, hi = f["initiative_bounds"]
        return max(lo, min(hi, 0.5 + f["initiative_scale"] * (share - 0.5)))

    def end(self, winner: str, condition: str) -> None:
        self.winner = winner
        self.win_condition = condition
        self.end_minute = self.minute

    @property
    def ended(self) -> bool:
        return self.winner is not None

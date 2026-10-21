"""Game configuration.

Every tuning constant used by the draft and simulation engines lives here
(spec section 11). Nothing in the engines hard-codes these numbers.
"""
from __future__ import annotations

import copy
from typing import Any

LANES = ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"]

# Short names used by Teams.csv focus columns -> lane names.
FOCUS_TO_LANE = {"top": "TOP", "jg": "JUNGLE", "mid": "MID", "bot": "BOT", "sup": "SUPPORT"}
# Player.Role values -> lane names.
ROLE_TO_LANE = FOCUS_TO_LANE

DRAFT_CONFIG: dict[str, Any] = {
    "draft_type": "STANDARD",
    "timer_seconds": 30,
    "actions": [
        "BLUE_BAN", "RED_BAN", "BLUE_BAN", "RED_BAN", "BLUE_BAN", "RED_BAN",
        "BLUE_PICK", "RED_PICK", "RED_PICK", "BLUE_PICK", "BLUE_PICK", "RED_PICK",
        "BLUE_BAN", "RED_BAN", "BLUE_BAN", "RED_BAN",
        "RED_PICK", "BLUE_PICK", "BLUE_PICK", "RED_PICK",
    ],
}

GAME_CONFIG: dict[str, Any] = {
    "lobby_expiration_minutes": 30,
    "lanes": LANES,
    "draft": DRAFT_CONFIG,
}

MANAGEMENT_CONFIG: dict[str, Any] = {
    "player_stat_budget": 32,        # soft ceiling for custom players
    # ceiling for players imported from a ranked Riot account, by tier; anyone else gets player_stat_budget
    "rank_stat_budgets": {
        "IRON": 28, "BRONZE": 28, "SILVER": 32, "GOLD": 32, "PLATINUM": 32, "EMERALD": 36, "DIAMOND": 36,
        "MASTER": 40, "GRANDMASTER": 40, "CHALLENGER": 48,
    },
    # minimum stat total an import from a ranked Riot account is raised to, by tier; anyone else has no floor
    "rank_stat_floors": {
        "IRON": 10, "BRONZE": 10, "SILVER": 28, "GOLD": 28, "PLATINUM": 28, "EMERALD": 28, "DIAMOND": 28,
        "MASTER": 36, "GRANDMASTER": 36, "CHALLENGER": 40,
    },
    "enforce_budget": False,         # True would turn the ceiling into a hard limit
    "system_players_exempt": True,
    "coach_stat_budget": 12,
    "stat_range": [1, 10],
    "champion_pool_size": 5,
    "allow_off_role_roster": False,
    "max_teams_per_user": 20,
    "max_players_per_user": 100,
    "max_coaches_per_user": 10,
}

SIMULATION_CONFIG: dict[str, Any] = {
    "version": "2.4.0",
    # Comfort modifiers (fractions, NOT whole-number multipliers).
    "comfort": {"best": 0.40, "comfort": 0.25, "familiar": 0.10, "vulnerable": -0.10},
    # Tier by position in the player's ordered 5-champion pool.
    "comfort_by_position": ["best", "comfort", "comfort", "familiar", "familiar"],
    "lane": {
        "roll_range": [1, 10],
        "scale": 5.0,          # converts raw rolls into the lane-score range
        "min_score": 100,      # floor on a base lane score
        "champion_synergy": {
            "aggr": {"damage": 30, "sturdiness": 30, "cc": 10, "mobility": 10, "utility": 20},
            "aware": {"damage": 10, "sturdiness": 30, "cc": 20, "mobility": 10, "utility": 30},
            "pos": {"damage": 30, "sturdiness": 20, "cc": 10, "mobility": 30, "utility": 10},
            "dmg": {"damage": 40, "sturdiness": 10, "cc": 10, "mobility": 40, "utility": 20},
            "divisor": 200,
        },
        # Lane multiplier from the player's stats behind the champion's strength (Offence/Defence/Control):
        # 1 + scale * (stat - mid) / half over the 1-10 stat range, so x0.75 at 1, x1.0 at 5.5, x1.25 at 10.
        "strength_fit": {
            "enabled": True,
            "scale": 0.25,
            "stat_range": [1, 10],
            "stats": {"Offence": ["dmg", "pos"], "Defence": ["aggr"], "Control": ["aware"]},
        },
        "matchup_multiplier": {"slight": 1.25, "strong": 1.5, "strong_threshold": 2},
        "assist": {"jungle": 0.45, "support_to_bot": 0.5, "other": 0.10},
        "focus_assist_boost": 0.25,
        # The assist fractions give each role a different total share (bot gets the most, jungle the least).
        # When on, each lane score is rescaled so equal players in every role end up with equal scores.
        "normalise_assists": True,
    },
    # Per-fight swing, in percent, centred on the comfort modifier (x scale). Each difficulty step above 1
    # widens the swing by `spread` points both ways, and pulls the centre down by `low_comfort_penalty` per
    # comfort point below `mastery`: hard champions have a higher ceiling but can fail, worst when unpractised.
    "skill_check": {"scale": 0.5, "spread": 30.0, "mastery": 25.0, "low_comfort_penalty": 0.5},
    "economy": {
        "gold_per_cs": 19.8,
        "kill": 300,
        "assist": 150,
        "tower": 250,
        "soul_bonus": 1000,
        "support_cs_factor": 0.15,
        "lane_minutes": 15,
        "bounty_gold_deficit": 2000,
        "bounty_gold": 250,
        "bounty_lane_score": 150,
    },
    "phases": [
        {"name": "early", "minutes": [3, 15], "max_dragons": 3, "max_barons": 0, "max_towers": 5,
         "skirmishes": [2, 8], "skirmish_size": [1, 4], "teamfights": [0, 0], "teamfight_size": [4, 5]},
        {"name": "mid", "minutes": [15, 25], "max_dragons": 2, "max_barons": 1, "max_towers": 6,
         "skirmishes": [2, 8], "skirmish_size": [2, 5], "teamfights": [0, 1], "teamfight_size": [4, 5]},
        {"name": "late", "minutes": [25, 35], "max_dragons": 2, "max_barons": 2, "max_towers": 4,
         "skirmishes": [1, 6], "skirmish_size": [3, 5], "teamfights": [1, 3], "teamfight_size": [4, 5]},
    ],
    "overtime": {"round_minutes": 5, "max_rounds": 3, "max_dragons": 1, "max_barons": 1, "max_towers": 2,
                 "skirmishes": [1, 3], "skirmish_size": [3, 5], "teamfights": [1, 2], "teamfight_size": [4, 5]},
    "objectives": {
        "dragon_soul_at": 4,
        "elemental_pool": 7,
        "dragon_lane_buff": 0.10,
        "soul_lane_multiplier": 1.5,
        "elder_bonus": 0.15,
        "elder_fights": 2,
        "baron_power_play_bonus": 50,
        "gold_control_scale": 1.0,
        "gold_lead_cap": 0.30,
        "control_roll_range": [1, 3],
    },
    "structures": {
        "towers_per_lane": 3,
        "nexus_towers": 2,
        "siege_min_kills": 1,
        "nexus_min_minute": 18,
        "siege_base_chance": 0.55,
        "siege_control_scale": 1.0,
        "baron_extra_hits": 3,
        "timeout_weights": {"tower": 1, "inhibitor": 2, "nexus_tower": 2},
    },
    "fight": {
        "damage_weight": 1.0,
        "sturdiness_weight": 1.0,  # equal to damage, so tanks are not outclassed by carries
        "control_scale": 0.5,      # weight of CC + mobility + utility above/below average
        "control_average": 5.25,   # the champion pool's average CC + mobility + utility
        "even_threshold": 0.02,
        "dominance_scale": 2.5,
        # Chance a side starts a fight (and so brings the bigger group to a skirmish):
        # 0.5 + scale * (its share of both teams' summed aggr - 0.5), clamped to initiative_bounds.
        "initiative_scale": 1.0,
        "initiative_bounds": [0.2, 0.8],
        # Fight performance from the player's dmg stat: 1 + scale * (dmg - mid) / half over the 1-10 range.
        "dmg_stat_scale": 0.10,
        # Damage dealt/taken figures in the result (reporting only: no rolls, no effect on the fight).
        # Dealt = the damage part of a fighter's power x scale; the enemy's damage is taken in proportion to
        # sturdiness, with fighters who died taking `damage_taken_death_bonus` more.
        "damage_report_scale": 0.4,    # puts a carry at roughly 20k over a 30-minute game
        "damage_taken_death_bonus": 0.5,
    },
    "winner_rule": "nexus",
    "team_style": {
        "enabled": True,
        "primary_bonus": 0.10,
        "secondary_bonus": 0.05,
        "scaling_lane_penalty": 0.05,
        "focus_lane_bonus": 0.08,
    },
    "coach": {"draft_matchup_scale": 0.05, "synergy_scale": 0.02},
    # Champion x champion win rate matrices (admin "Winrates" page). A delta is a win rate minus the baseline,
    # in points; each effect is x(1 + scale * delta), so 55% at scale 0.02 is x1.10.
    "win_rates": {
        "enabled": True,
        "baseline": 50.0,
        "max_points": 10.0,           # cap on any averaged delta
        "lane_counter_scale": 0.03,   # lane score, from the win rate against the lane opponent(s)
        "lane_duo_scale": 0.02,       # bot + support lane scores, from their same-team win rate
        "fight_synergy_scale": 0.02,  # fight power, from the fighters' average same-team win rate
        "fight_counter_scale": 0.02,  # fight power, from the fighters' average win rate against the enemy fighters
    },
    # A comp leaning on one damage type is easier to itemize against: its damage in fights is cut by up to
    # max_penalty, rising linearly from 0 at `threshold` share of the main type to max_penalty at 100%.
    "damage_balance": {
        "enabled": True,
        "threshold": 0.65,
        "max_penalty": 0.25,
        "phase_weights": {"early": 0.5, "mid": 1.0, "late": 1.0, "overtime": 1.0},
    },
    # Champion power curve by game phase, from each champion's scaling score (champion_scaling.csv:
    # 1 early game, 2 neutral, 3 late game). The multiplier applies to the champion's lane score in the lane
    # phase and to its fight performance in later phases.
    "champion_scaling": {
        "enabled": True,
        "curves": {
            "1": {"lane": 1.10, "early": 1.10, "mid": 1.00, "late": 0.92, "overtime": 0.88},
            "2": {"lane": 1.00, "early": 1.00, "mid": 1.00, "late": 1.00, "overtime": 1.00},
            "3": {"lane": 0.92, "early": 0.92, "mid": 1.00, "late": 1.10, "overtime": 1.14},
        },
    },
}

_SCALING_LABELS = {"1": "Early game champions", "3": "Late game champions"}
_PHASE_LABELS = {"lane": "Lane phase", "early": "Early game", "mid": "Mid game", "late": "Late game",
                 "overtime": "Overtime"}

# Settings admins may change on the Simulation Settings page, stored as overrides of SIMULATION_CONFIG.
# kind "bool" or "number"; numbers are checked against min/max.
EDITABLE_SETTINGS: list[dict[str, Any]] = [
    {"path": "win_rates.enabled", "group": "Champion win rates", "kind": "bool", "label": "Use win rate matrices",
     "help": "Same-team and against-team win rates affect lanes and fights."},
    {"path": "win_rates.baseline", "group": "Champion win rates", "kind": "number", "min": 40, "max": 60, "step": 0.5,
     "label": "Baseline win rate (%)", "help": "A win rate equal to this has no effect."},
    {"path": "win_rates.max_points", "group": "Champion win rates", "kind": "number", "min": 0, "max": 50, "step": 0.5,
     "label": "Cap (points)", "help": "Largest averaged win rate difference from the baseline that counts."},
    {"path": "win_rates.lane_counter_scale", "group": "Champion win rates", "kind": "number", "min": 0, "max": 0.2,
     "step": 0.005, "label": "Lane counter strength",
     "help": "Lane score change per point of win rate against the lane opponent (bot and support face both enemy "
             "bot laners)."},
    {"path": "win_rates.lane_duo_scale", "group": "Champion win rates", "kind": "number", "min": 0, "max": 0.2,
     "step": 0.005, "label": "Bot lane duo strength",
     "help": "Bot and support lane score change per point of their same-team win rate."},
    {"path": "win_rates.fight_synergy_scale", "group": "Champion win rates", "kind": "number", "min": 0, "max": 0.2,
     "step": 0.005, "label": "Fight synergy strength",
     "help": "Fight power change per point of the fighters' average same-team win rate."},
    {"path": "win_rates.fight_counter_scale", "group": "Champion win rates", "kind": "number", "min": 0, "max": 0.2,
     "step": 0.005, "label": "Fight counter strength",
     "help": "Fight power change per point of the fighters' average win rate against the enemy fighters."},
    {"path": "damage_balance.enabled", "group": "Damage balance", "kind": "bool", "label": "Penalize one-sided damage",
     "help": "A comp with mostly physical or mostly magic damage deals less damage in fights."},
    {"path": "damage_balance.threshold", "group": "Damage balance", "kind": "number", "min": 0.5, "max": 0.99,
     "step": 0.01, "label": "Free share of one type",
     "help": "Share of the team's damage one type can have before the penalty starts (0.65 = 65%)."},
    {"path": "damage_balance.max_penalty", "group": "Damage balance", "kind": "number", "min": 0, "max": 0.9,
     "step": 0.01, "label": "Penalty at 100% one type", "help": "Fraction of fight damage lost by a single-type comp."},
    {"path": "damage_balance.phase_weights.early", "group": "Damage balance", "kind": "number", "min": 0, "max": 2,
     "step": 0.05, "label": "Early game weight", "help": "How much of the penalty applies in early game fights."},
    {"path": "damage_balance.phase_weights.mid", "group": "Damage balance", "kind": "number", "min": 0, "max": 2,
     "step": 0.05, "label": "Mid game weight", "help": "How much of the penalty applies in mid game fights."},
    {"path": "damage_balance.phase_weights.late", "group": "Damage balance", "kind": "number", "min": 0, "max": 2,
     "step": 0.05, "label": "Late game weight", "help": "How much of the penalty applies in late game fights."},
    {"path": "damage_balance.phase_weights.overtime", "group": "Damage balance", "kind": "number", "min": 0, "max": 2,
     "step": 0.05, "label": "Overtime weight", "help": "How much of the penalty applies in overtime fights."},
    {"path": "champion_scaling.enabled", "group": "Champion scaling", "kind": "bool",
     "label": "Use champion scaling",
     "help": "Early game champions are stronger in lane and early fights, late game champions in late fights."},
    *[{"path": f"champion_scaling.curves.{score}.{phase}", "group": "Champion scaling", "kind": "number",
       "min": 0.5, "max": 1.5, "step": 0.01, "label": f"{who}: {_PHASE_LABELS[phase].lower()}",
       "help": f"Multiplier on lane score (lane phase) or fight performance (later phases). 1 = no effect. "
               f"Neutral (scaling 2) champions always use 1."}
      for score, who in _SCALING_LABELS.items() for phase in _PHASE_LABELS],
]
EDITABLE_BY_PATH = {s["path"]: s for s in EDITABLE_SETTINGS}


def config_value(config: dict, path: str) -> Any:
    value: Any = config
    for key in path.split("."):
        value = value[key]
    return value


def validate_overrides(values: dict[str, Any]) -> dict:
    """Check {dotted path: value} against EDITABLE_SETTINGS and return it as nested overrides for
    `simulation_config`. Raises ValueError naming the first bad entry."""
    nested: dict = {}
    for path, value in values.items():
        spec = EDITABLE_BY_PATH.get(path)
        if spec is None:
            raise ValueError(f"{path} is not an editable setting.")
        if spec["kind"] == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{spec['label']} must be true or false.")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{spec['label']} must be a number.")
            if not spec["min"] <= value <= spec["max"]:
                raise ValueError(f"{spec['label']} must be between {spec['min']} and {spec['max']}.")
            value = float(value)
        *parents, leaf = path.split(".")
        node = nested
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return nested


def flatten_overrides(overrides: dict, prefix: str = "") -> dict[str, Any]:
    """Nested overrides -> {dotted path: value}; the inverse of `validate_overrides`."""
    out: dict[str, Any] = {}
    for key, value in overrides.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten_overrides(value, f"{path}."))
        else:
            out[path] = value
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def simulation_config(overrides: dict | None = None) -> dict:
    """Return a fresh copy of the simulation config with optional overrides."""
    if not overrides:
        return copy.deepcopy(SIMULATION_CONFIG)
    return _deep_merge(SIMULATION_CONFIG, overrides)

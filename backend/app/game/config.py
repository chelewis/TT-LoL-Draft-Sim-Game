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
    "version": "2.1.0",
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
    },
    "skill_check": {"scale": 0.5},
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
        "sturdiness_weight": 0.5,
        "control_scale": 0.5,      # weight of CC + mobility + utility above/below average
        "control_average": 6.0,
        "even_threshold": 0.02,
        "dominance_scale": 2.5,
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
    "damage_profile_penalty": {"enabled": False, "threshold": 0.8, "bonus": 0.05},
}


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

"""Tunable constants for importing Riot accounts (regions, benchmarks, name aliases).

The benchmarks below are first-guess values for converting real match performance into the game's
1-10 player stats. Tune them after sampling real accounts; nothing else needs to change.
"""
from __future__ import annotations

# platform code (what the user picks) -> regional routing cluster for account-v1 / match-v5
PLATFORM_CLUSTER = {
    "NA1": "americas", "BR1": "americas", "LA1": "americas", "LA2": "americas",
    "EUW1": "europe", "EUN1": "europe", "TR1": "europe", "RU": "europe", "ME1": "europe",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea", "SG2": "sea", "TW2": "sea", "VN2": "sea", "PH2": "sea", "TH2": "sea",
}

TEAM_POSITION_TO_LANE = {"TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MID", "BOTTOM": "BOT", "UTILITY": "SUPPORT"}

# Where stats come from, in order of preference. The importer uses the FIRST tier that has at least
# MIN_GAMES usable games and never mixes queues. `params` are the match-v5 id filters; `queue_ids` are the
# queues a fetched match must belong to (the `type=normal` filter also returns modes without lane roles).
QUEUE_TIERS = [
    {"key": "SOLO", "label": "Ranked solo", "noun": "ranked solo games", "params": {"queue": 420}, "queue_ids": frozenset({420})},
    {"key": "FLEX", "label": "Ranked flex", "noun": "ranked flex games", "params": {"queue": 440}, "queue_ids": frozenset({440})},
    {"key": "NORMAL", "label": "Normal games", "noun": "normal games", "params": {"type": "normal"},
     "queue_ids": frozenset({400, 430, 490})},   # draft pick, blind pick, quickplay
]
MIN_GAME_SECONDS = 300          # shorter games are remakes and ignored

# Riot champion names are matched to ours after lower-casing and dropping punctuation/spaces (so
# "Cho'Gath" == "Cho Gath", "Nunu & Willump" == "Nunu & Willump"). Only real exceptions go here:
# normalised Riot display name or id -> normalised name in our data set.
CHAMPION_ALIASES = {
    "monkeyking": "wukong",
}

# (low, high): the value that maps to stat 1 and to stat 10. For "lower is better" metrics the
# mapper inverts the result. Keys are lanes.
BENCHMARKS: dict[str, dict[str, tuple[float, float]]] = {
    "kill_participation": {"TOP": (0.35, 0.65), "JUNGLE": (0.50, 0.75), "MID": (0.45, 0.70), "BOT": (0.50, 0.72), "SUPPORT": (0.50, 0.75)},
    "kills_per_min": {"TOP": (0.10, 0.30), "JUNGLE": (0.10, 0.28), "MID": (0.12, 0.35), "BOT": (0.12, 0.35), "SUPPORT": (0.02, 0.12)},
    "vision_per_min": {"TOP": (0.5, 1.2), "JUNGLE": (0.8, 1.6), "MID": (0.6, 1.3), "BOT": (0.6, 1.2), "SUPPORT": (1.8, 3.2)},
    "objectives_per_game": {"TOP": (0.0, 1.5), "JUNGLE": (0.5, 3.5), "MID": (0.0, 1.5), "BOT": (0.0, 1.5), "SUPPORT": (0.0, 1.5)},
    "deaths_per_min": {lane: (0.10, 0.35) for lane in ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT")},
    "kda": {lane: (1.5, 5.0) for lane in ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT")},
    "damage_per_min": {"TOP": (400, 800), "JUNGLE": (300, 600), "MID": (550, 950), "BOT": (550, 1000), "SUPPORT": (150, 400)},
    "damage_share": {"TOP": (0.15, 0.30), "JUNGLE": (0.10, 0.22), "MID": (0.18, 0.32), "BOT": (0.20, 0.35), "SUPPORT": (0.04, 0.12)},
    "cs_per_min": {"TOP": (5.0, 8.0), "JUNGLE": (3.8, 6.0), "MID": (5.5, 8.5), "BOT": (6.0, 9.0), "SUPPORT": (0.5, 1.8)},
}

# game stat -> metrics that make it up (all weighted equally); "-" prefix = lower is better
STAT_METRICS = {
    "aggr": ["kill_participation", "kills_per_min"],
    "aware": ["vision_per_min", "objectives_per_game"],
    "pos": ["-deaths_per_min", "kda"],
    "dmg": ["damage_per_min", "damage_share"],
    "cs": ["cs_per_min"],
}

# Human-readable names and meaning of each metric, shown in the import preview tooltips.
METRIC_INFO = {
    "kill_participation": {"label": "Kill participation", "unit": "percent", "how": "(kills + assists) / team kills"},
    "kills_per_min": {"label": "Kills per minute", "unit": "number", "how": "kills / game minutes"},
    "vision_per_min": {"label": "Vision score per minute", "unit": "number", "how": "vision score / game minutes"},
    "objectives_per_game": {"label": "Dragon + baron takedowns per game", "unit": "number", "how": "dragon takedowns + baron takedowns"},
    "deaths_per_min": {"label": "Deaths per minute", "unit": "number", "how": "deaths / game minutes (fewer is better)"},
    "kda": {"label": "KDA", "unit": "number", "how": "(kills + assists) / max(1, deaths)"},
    "damage_per_min": {"label": "Damage to champions per minute", "unit": "number", "how": "damage dealt to champions / game minutes"},
    "damage_share": {"label": "Share of team damage", "unit": "percent", "how": "own damage to champions / team damage to champions"},
    "cs_per_min": {"label": "CS per minute", "unit": "number", "how": "(lane minions + jungle monsters) / game minutes"},
}

# Calls per import: 1 account + 1 match list + N matches + 1 mastery. Keep N modest for the 100/2min key.
MATCH_COUNT = 20
MIN_GAMES = 10

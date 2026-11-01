"""Starter playstyle tags, added once when the playstyle_tags table is empty. Admins edit them from then on.

Challenge ids are Riot's lol-challenges-v1 ids. Positive tags use skill challenges at Diamond or above;
negative tags compare the player's averages over the imported games (riot/config.py METRIC_INFO).
"""
from __future__ import annotations


def _ch(*pairs: tuple[int, str]) -> list[dict]:
    return [{"id": cid, "name": name} for cid, name in pairs]


STARTER_TAGS: list[dict] = [
    # ------------------------------------------------------------- positive
    {"key": "playmaker", "label": "Playmaker", "polarity": "positive", "source": "challenge",
     "description": "Forces early fights and makes things happen around the map.",
     "rule": {"challenges": _ch((302101, "Level 1 Fiesta"), (201004, "Death Incarnate"),
                                (302102, "Farm Champs not Camps")), "min_level": "DIAMOND"},
     "effects": [{"hook": "initiative", "value": 0.04}]},
    {"key": "duelist", "label": "Duelist", "polarity": "positive", "source": "challenge",
     "description": "Wins one-on-ones and builds big leads over their lane opponent.",
     "rule": {"challenges": _ch((203301, "Solo Bolo"), (202101, "Flame Horizon")), "min_level": "DIAMOND"},
     "effects": [{"hook": "lane_score", "value": 0.03}]},
    {"key": "objective_hunter", "label": "Objective Hunter", "polarity": "positive", "source": "challenge",
     "description": "Always around for dragons and barons, and steals a few.",
     "rule": {"challenges": _ch((402206, "Lizard Hunting"), (402207, "Wurm Fishing"), (301101, "Always On Time"),
                                (402201, "Clutch Steal")), "min_level": "DIAMOND"},
     "effects": [{"hook": "objective", "value": 0.03}]},
    {"key": "vision_controller", "label": "Vision Controller", "polarity": "positive", "source": "challenge",
     "description": "Lights up the map and clears enemy vision.",
     "rule": {"challenges": _ch((204102, "All-Seeing"), (402403, "Goodbye to the Darkness!"),
                                (402401, "Darkness is Everywhere"), (202104, "The Brush Has Eyes")),
              "min_level": "DIAMOND"},
     "effects": [{"hook": "objective", "value": 0.02}]},
    {"key": "farmer", "label": "Farmer", "polarity": "positive", "source": "challenge",
     "description": "Efficient last-hitting and wave control.",
     "rule": {"challenges": _ch((201002, "Lethal Efficiency")), "min_level": "DIAMOND"},
     "effects": [{"hook": "cs_rate", "value": 0.04}]},
    {"key": "survivor", "label": "Survivor", "polarity": "positive", "source": "challenge",
     "description": "Dodges skillshots and walks out of fights alive.",
     "rule": {"challenges": _ch((601002, "Dancing Shoes"), (203203, "Go Where You Please"),
                                (203202, "Damage Sponge")), "min_level": "DIAMOND"},
     "effects": [{"hook": "survival", "value": 0.05}]},
    {"key": "teamfighter", "label": "Teamfighter", "polarity": "positive", "source": "challenge",
     "description": "Shines in five-versus-five fights.",
     "rule": {"challenges": _ch((402105, "Multikill Madness"), (302401, "Flawless Ace"),
                                (302402, "Making the Dream Work")), "min_level": "DIAMOND"},
     "effects": [{"hook": "fight_perf", "value": 0.03}]},
    {"key": "tower_breaker", "label": "Tower Breaker", "polarity": "positive", "source": "challenge",
     "description": "Turns pressure into towers, often by split pushing.",
     "rule": {"challenges": _ch((402210, "Turret Toppler"), (302202, "Shattered Plates"),
                                (203304, "Splitpush Strategy")), "min_level": "DIAMOND"},
     "effects": [{"hook": "tower", "value": 0.03}]},
    {"key": "champion_ocean", "label": "Champion Ocean", "polarity": "positive", "source": "challenge",
     "description": "Wins on a huge range of champions, so off-pool picks hurt them less.",
     "rule": {"challenges": _ch((401106, "Jack of All Champs"), (2024308, "Champion Ocean: 2024 Split 3"),
                                (401104, "Master Yourself")), "min_level": "DIAMOND"},
     "effects": [{"hook": "off_pool_penalty", "value": 0.5}]},
    # ------------------------------------------------------------- negative
    {"key": "reckless", "label": "Reckless", "polarity": "negative", "source": "match",
     "description": "Dies a lot in recent games.",
     "rule": {"metric": "deaths_per_min", "op": ">=", "value": 0.30, "lanes": {}},
     "effects": [{"hook": "survival", "value": -0.05}]},
    {"key": "passive", "label": "Passive", "polarity": "negative", "source": "match",
     "description": "Rarely involved in their team's kills.",
     "rule": {"metric": "kill_participation", "op": "<=", "value": 0.40,
              "lanes": {"TOP": 0.30, "JUNGLE": 0.45, "BOT": 0.45, "SUPPORT": 0.45}},
     "effects": [{"hook": "initiative", "value": -0.04}]},
    {"key": "poor_farmer", "label": "Poor Farmer", "polarity": "negative", "source": "match",
     "description": "Low CS in recent games.",
     "rule": {"metric": "cs_per_min", "op": "<=", "value": 5.5,
              "lanes": {"TOP": 5.0, "JUNGLE": 4.0, "BOT": 6.0, "SUPPORT": None}},
     "effects": [{"hook": "cs_rate", "value": -0.04}]},
    {"key": "map_blind", "label": "Map Blind", "polarity": "negative", "source": "match",
     "description": "Low vision score in recent games.",
     "rule": {"metric": "vision_per_min", "op": "<=", "value": 0.5,
              "lanes": {"TOP": 0.45, "JUNGLE": 0.7, "SUPPORT": 1.5}},
     "effects": [{"hook": "objective", "value": -0.03}]},
    {"key": "one_trick", "label": "One Trick", "polarity": "negative", "source": "match",
     "description": "Plays one champion most games: great on it, lost off it.",
     "rule": {"metric": "top_champion_share", "op": ">=", "value": 0.6, "lanes": {}},
     "effects": [{"hook": "pool_best_bonus", "value": 0.15}, {"hook": "off_pool_penalty", "value": -0.5}]},
]

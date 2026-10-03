"""Pool position -> comfort tier -> modifier (spec 9.2)."""
from __future__ import annotations

from .models import PlayerSpec


def comfort_tier(player: PlayerSpec, champion_id: int, config: dict) -> str:
    """Return BEST / COMFORT / FAMILIAR / VULNERABLE (upper-case)."""
    tiers = config["comfort_by_position"]
    for position, pooled in enumerate(player.pool):
        if pooled == champion_id and position < len(tiers):
            return tiers[position].upper()
    return "VULNERABLE"


def comfort_modifier(tier: str, config: dict) -> float:
    """Fractional modifier, e.g. 0.40 for BEST and -0.10 for VULNERABLE."""
    return float(config["comfort"][tier.lower()])

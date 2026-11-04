"""Pool position -> comfort tier -> modifier (spec 9.2)."""
from __future__ import annotations

from .models import Champion, PlayerSpec


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


def off_role(champion: Champion, lane: str, player: PlayerSpec, config: dict) -> bool:
    """True when the champion is played outside its usual roles and isn't one of the player's top pool picks.
    Always False when the rule is switched off or the champion has no role data."""
    cfg = config["off_role"]
    if not cfg["enabled"] or not champion.roles or lane in champion.roles:
        return False
    return champion.id not in player.pool[:cfg["pool_exempt"]]


def off_role_multiplier(champion: Champion, lane: str, player: PlayerSpec, config: dict) -> float:
    """Lane score multiplier: x(1 - lane_penalty) off-role, else 1.0."""
    if off_role(champion, lane, player, config):
        return max(1.0 - config["off_role"]["lane_penalty"], 0.0)
    return 1.0

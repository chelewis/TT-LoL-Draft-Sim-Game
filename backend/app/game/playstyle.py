"""Playstyle tag effects: a player's tag effects summed per hook and clamped (spec "Playstyle tags")."""
from __future__ import annotations

from .config import PLAYSTYLE_HOOKS
from .models import PlayerSpec


def effect_totals(spec: PlayerSpec) -> dict[str, float]:
    """hook -> combined value of every tag effect on this player, clamped to the hook's +/-cap.
    Unknown hooks (e.g. from a newer snapshot) are ignored."""
    totals: dict[str, float] = {}
    for hook, value in spec.tag_effects:
        if hook in PLAYSTYLE_HOOKS:
            totals[hook] = totals.get(hook, 0.0) + float(value)
    return {hook: max(-PLAYSTYLE_HOOKS[hook]["cap"], min(PLAYSTYLE_HOOKS[hook]["cap"], v))
            for hook, v in totals.items()}


def adjust_comfort(comfort: float, tier: str, tags: dict[str, float]) -> float:
    """Apply the rule-changing pool hooks to a comfort modifier (spec 9.2)."""
    if tier == "VULNERABLE" and comfort < 0:
        return comfort * (1.0 - tags.get("off_pool_penalty", 0.0))
    if tier == "BEST":
        return comfort * (1.0 + tags.get("pool_best_bonus", 0.0))
    return comfort

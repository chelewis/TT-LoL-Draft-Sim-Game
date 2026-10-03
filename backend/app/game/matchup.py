"""Lane matchup wheel: Offence > Defence > Control > Offence (spec 9.4)."""
from __future__ import annotations

from .models import Champion


def lane_matchup(a: Champion, b: Champion, config: dict) -> tuple[float, float, str | None]:
    """Return (multiplier_a, multiplier_b, label).

    label is None for an even matchup, otherwise "A_STRONG"/"A_SLIGHT"/"B_STRONG"/"B_SLIGHT".
    Multipliers here are the raw values (1.0 / 1.25 / 1.5); the coach's Draft rating is
    applied by the caller.
    """
    mm = config["lane"]["matchup_multiplier"]
    if a.strength == b.weakness:
        winner, loser, side = a, b, "A"
    elif b.strength == a.weakness:
        winner, loser, side = b, a, "B"
    else:
        return 1.0, 1.0, None
    diff = winner.attribute(winner.strength) - loser.attribute(loser.weakness)
    if diff >= mm["strong_threshold"]:
        mult, kind = mm["strong"], "STRONG"
    else:
        mult, kind = mm["slight"], "SLIGHT"
    label = f"{side}_{kind}"
    return (mult, 1.0, label) if side == "A" else (1.0, mult, label)


def apply_coach_draft(multiplier: float, draft: int, config: dict) -> float:
    """Coach Draft rating scales only the *bonus part* of a favourable multiplier."""
    if multiplier <= 1.0:
        return multiplier
    scale = 1.0 + (draft - 5) * config["coach"]["draft_matchup_scale"]
    return 1.0 + (multiplier - 1.0) * max(scale, 0.0)

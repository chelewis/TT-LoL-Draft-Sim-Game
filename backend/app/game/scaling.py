"""Champion scaling: how a champion's power changes over the game, from its scaling score
(1 early game, 2 neutral, 3 late game)."""
from __future__ import annotations

from typing import Iterable

from .models import Champion


def scaling_multiplier(champion: Champion, phase: str, config: dict) -> float:
    """The champion's power multiplier in `phase` (lane, early, mid, late or overtime). 1.0 when scaling is
    off, or for a phase or score the config has no curve for."""
    cfg = config["champion_scaling"]
    if not cfg["enabled"]:
        return 1.0
    curve = cfg["curves"].get(str(champion.scaling), {})
    return float(curve.get(phase, 1.0))


def comp_scaling(champions: Iterable[Champion]) -> float:
    """A comp's average scaling score, from 1.0 (all early game) to 3.0 (all late game)."""
    scores = [c.scaling for c in champions]
    return round(sum(scores) / len(scores), 2) if scores else 2.0

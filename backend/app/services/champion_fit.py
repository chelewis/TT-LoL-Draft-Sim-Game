"""Which champions suit a player: the simulation's own lane formula, without the dice.

The lane phase scores a player as sum(roll * stat * champion synergy weight) over aggr/aware/pos/dmg,
then multiplies by (1 + comfort) from the player's pool (game/lane_phase.py, game/comfort.py). Ranking
champions by that sum with the roll left out shows which champions a player's stats get the most from.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.game.comfort import comfort_modifier, comfort_tier
from app.game.config import SIMULATION_CONFIG
from app.game.lane_phase import champion_synergy
from app.game.models import PlayerSpec
from app.models import Champion

FIT_STATS = ("aggr", "aware", "pos", "dmg")


def rank_champions(db: Session, aggr: int, aware: int, pos: int, dmg: int, pool: list[int],
                   limit: int = 10) -> list[dict]:
    """Enabled champions ordered by lane fit for these stats and this pool, best first."""
    cfg = SIMULATION_CONFIG
    spec = PlayerSpec(0, "", "", 0, aggr, aware, pos, dmg, 0, tuple(pool))
    rows = []
    for champion in db.scalars(select(Champion).where(Champion.enabled.is_(True))):
        engine = champion.to_engine()
        weights = champion_synergy(engine, cfg)
        contributions = {stat: getattr(spec, stat) * weights[stat] for stat in FIT_STATS}
        base = sum(contributions.values())
        tier = comfort_tier(spec, engine.id, cfg)
        rows.append({
            "champion_id": engine.id,
            "name": engine.name,
            "score": round(base * (1.0 + comfort_modifier(tier, cfg)), 2),
            "base": round(base, 2),
            "comfort_tier": tier,
            "top_stat": max(contributions, key=contributions.get),
        })
    rows.sort(key=lambda r: (-r["score"], r["name"]))
    return rows[:limit]

"""Which champions suit a player: the simulation's own lane formula, without the dice.

The lane phase scores a player as sum(roll * stat * champion synergy weight) over aggr/aware/pos/dmg,
then multiplies by (1 + comfort) from the player's pool, by the strength fit, which rewards or
punishes the player's stats behind the champion's strength, and by the off-role penalty when the
champion is played outside its usual roles (game/lane_phase.py, game/comfort.py).
Ranking champions by that with the roll left out shows which champions a player's stats get the most from.

Given the player's lanes, each champion is judged in whichever of them suits it best, and champions the
off-role penalty applies to are listed after every other champion, whatever their score.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.game.comfort import comfort_modifier, comfort_tier, off_role_multiplier
from app.game.config import SIMULATION_CONFIG
from app.game.lane_phase import champion_synergy, strength_fit
from app.game.lane_preview import role_status
from app.game.models import PlayerSpec
from app.models import Champion

FIT_STATS = ("aggr", "aware", "pos", "dmg")
# best first; None = the champion has no role data (never penalised)
STATUS_ORDER = {"MAIN": 0, "SECONDARY": 1, None: 2, "OFF_ROLE_EXEMPT": 3, "OFF_ROLE": 4}


def rank_champions(db: Session, aggr: int, aware: int, pos: int, dmg: int, pool: list[int],
                   limit: int | None = 10, role: str | None = None,
                   secondary_role: str | None = None) -> list[dict]:
    """Enabled champions ordered by lane fit for these stats, pool and lanes, best first (all of them if limit
    is None). Without a role, no champion counts as off-role."""
    cfg = SIMULATION_CONFIG
    spec = PlayerSpec(0, "", role or "", 0, aggr, aware, pos, dmg, 0, tuple(pool))
    lanes = [lane for lane in dict.fromkeys((role, secondary_role)) if lane]
    rows = []
    for champion in db.scalars(select(Champion).where(Champion.enabled.is_(True))):
        engine = champion.to_engine()
        weights = champion_synergy(engine, cfg)
        contributions = {stat: getattr(spec, stat) * weights[stat] for stat in FIT_STATS}
        base = sum(contributions.values())
        tier = comfort_tier(spec, engine.id, cfg)
        fit = strength_fit(spec, engine, cfg)
        lane, status, off_mult = None, None, 1.0
        if lanes:   # the lane that suits the champion best; ties go to the primary role
            lane, status, off_mult = min(
                ((ln, role_status(engine, ln, spec, cfg), off_role_multiplier(engine, ln, spec, cfg)) for ln in lanes),
                key=lambda x: (STATUS_ORDER[x[1]], -x[2]))
        rows.append({
            "champion_id": engine.id,
            "name": engine.name,
            "class": engine.champ_class,
            "score": round(base * (1.0 + comfort_modifier(tier, cfg)) * fit * off_mult, 2),
            "base": round(base, 2),
            "comfort_tier": tier,
            "top_stat": max(contributions, key=contributions.get),
            "strength": engine.strength,
            "strength_fit": round(fit, 2),
            "lane": lane,
            "role_status": status,
            "off_role_penalty": round(1.0 - off_mult, 4),
        })
    rows.sort(key=lambda r: (r["off_role_penalty"] > 0, -r["score"], r["name"]))
    return rows[:limit]

"""Team notes for the team editor (game/team_insights.py) from the players and coach the user can see."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.game import team_insights as engine
from app.game.config import LANES, MANAGEMENT_CONFIG
from app.game.models import CoachSpec, PlayerSpec
from app.models import Champion, Coach, Player
from app.schemas.management import TeamInsightsIn
from app.services import matchup_service
from app.services.simulation_settings_service import current_config
from app.services.team_management_service import get_visible, player_view


def _spec(p: Player) -> PlayerSpec:
    view = player_view(p)
    effects = tuple((e["hook"], float(e["value"])) for t in view["tags"] for e in t.get("effects") or [])
    return PlayerSpec(p.id, p.name, p.role, p.age, p.aggr, p.aware, p.pos, p.dmg, p.cs, tuple(p.pool), effects)


def team_insights(db: Session, user_id: int, body: TeamInsightsIn) -> dict:
    roster = {lane: _spec(get_visible(db, Player, pid, user_id))
              for lane, pid in body.roster.items() if lane in LANES and pid}
    coach = None
    if body.coach_id:
        c = get_visible(db, Coach, body.coach_id, user_id)
        coach = CoachSpec(c.id, c.name, c.draft, c.synergy)
    pool_ids = {cid for p in roster.values() for cid in p.pool}
    champions = {c.id: c.to_engine() for c in db.scalars(select(Champion).where(Champion.enabled.is_(True)))}
    styles = tuple(s for s in (body.style1, body.style2) if s)
    focus = tuple(f for f in (body.focus1, body.focus2) if f)
    return engine.analyse(roster, styles, focus, coach, champions,
                          matchup_service.engine_table(db, pool_ids), current_config(db),
                          MANAGEMENT_CONFIG["player_stat_budget"])

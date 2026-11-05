"""The in-game meta as players see it: how each champion is doing in the simulation's win rate tables."""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, not_found
from app.game.pair_insights import analyse_pair
from app.models import Champion, ChampionMatchup
from app.services import matchup_service
from app.services.simulation_settings_service import current_config

BASELINE = 50.0
# A matchup's distance from 50 is softened so it can never count for more than this many points (tanh curve:
# small differences pass almost unchanged, extreme ones flatten out). Stops a few hard counters swamping the rest.
MATCHUP_SOFT_CAP = 15.0
# Weight of an opponent with no pick rate, so they still count a little.
MIN_WEIGHT = 0.1


def soften(rate: float, cap: float = MATCHUP_SOFT_CAP) -> float:
    """A matchup win rate with its distance from 50 squashed to at most `cap` points."""
    return BASELINE + cap * math.tanh((rate - BASELINE) / cap)


def lane_win_rate(matchups: list[tuple[float, float]]) -> float:
    """Expected win rate against a random lane opponent: each (win rate, opponent pick rate) matchup softened, then
    averaged weighted by how often that opponent is picked, so rare counters barely matter."""
    total = sum(max(pick, MIN_WEIGHT) for _, pick in matchups)
    return sum(soften(rate) * max(pick, MIN_WEIGHT) for rate, pick in matchups) / total


def champion_stats(db: Session) -> list[dict]:
    """One row per enabled champion, by name.

    win_rate is how the champion does in its main lane: its "against team" win rates (the table the simulation
    reads, so admin edits show here) against champions with the same main role, combined by `lane_win_rate`. A
    champion with no main role, or no data against its lane, falls back to its own stored win rate.
    pick_rate is the champion's stored pick rate.
    """
    champions = list(db.scalars(select(Champion).where(Champion.enabled.is_(True)).order_by(Champion.name)))
    engines = {c.id: c.to_engine() for c in champions}
    main_role = {cid: (e.roles[0] if e.roles else None) for cid, e in engines.items()}
    pick_rate = {c.id: c.pick_rate for c in champions}

    table = matchup_service.engine_table(db, list(engines))
    matchups: dict[int, list[tuple[float, float]]] = {cid: [] for cid in engines}
    for (a, b), rate in table.enemy.items():
        if main_role[a] is not None and main_role[a] == main_role[b]:
            matchups[a].append((rate, pick_rate[b]))
            matchups[b].append((100.0 - rate, pick_rate[a]))

    rows = []
    for champion in champions:
        engine, lane = engines[champion.id], matchups[champion.id]
        rows.append({
            "id": champion.id, "name": champion.name, "class": engine.champ_class, "roles": list(engine.roles),
            "role": main_role[champion.id],
            "win_rate": round(lane_win_rate(lane), 1) if lane else champion.win_rate,
            "win_rate_source": "matchups" if lane else "base",
            "opponents": len(lane),
            "pick_rate": champion.pick_rate,
        })
    return rows


def _cell(db: Session, kind: str, a: int, b: int) -> dict:
    """Where a pair's stored win rate came from: games played and whether an admin set it (no row: 0, False)."""
    lo, hi = min(a, b), max(a, b)
    row = db.execute(select(ChampionMatchup.games, ChampionMatchup.edited).where(
        ChampionMatchup.kind == kind, ChampionMatchup.champion_a_id == lo, ChampionMatchup.champion_b_id == hi)).first()
    return {"games": row.games if row else 0, "edited": bool(row.edited) if row else False}


def champion_pair(db: Session, a_id: int, b_id: int) -> dict:
    """How two enabled champions interact: same-team and against-team win rates (against: a's rate against b) from
    the tables the simulation reads, and notes on what the simulation does with the pair (game/pair_insights.py)."""
    if a_id == b_id:
        raise bad_request("Choose two different champions.")
    found = {c.id: c for c in db.scalars(select(Champion).where(Champion.id.in_((a_id, b_id)),
                                                                Champion.enabled.is_(True)))}
    if a_id not in found or b_id not in found:
        raise not_found("Champion not found.")
    a, b = found[a_id].to_engine(), found[b_id].to_engine()
    out = analyse_pair(a, b, matchup_service.engine_table(db, [a_id, b_id]), current_config(db))
    out["same_team"].update(_cell(db, "ally", a_id, b_id))
    out["against"].update(_cell(db, "enemy", a_id, b_id))
    return out

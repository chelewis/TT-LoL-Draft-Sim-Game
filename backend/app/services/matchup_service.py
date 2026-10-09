"""Champion x champion win rate matrices, edited by admins (same team = "ally", against team = "enemy")."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, not_found
from app.data.matchup_seed import KINDS, canonical, import_matchups
from app.models import Champion, ChampionMatchup
from app.schemas.admin import MatchupChange


def check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise not_found("Unknown win rate matrix.")
    return kind


def matrix(db: Session, kind: str) -> dict:
    """The whole matrix: its champions by name, and one [a_id, b_id, win_rate, games, edited] row per stored pair
    (a_id < b_id; for "enemy" the rate is champion a's)."""
    champions = db.execute(select(Champion.id, Champion.name).where(Champion.enabled.is_(True)).order_by(Champion.name))
    cells = db.execute(select(ChampionMatchup.champion_a_id, ChampionMatchup.champion_b_id, ChampionMatchup.win_rate,
                              ChampionMatchup.games, ChampionMatchup.edited).where(ChampionMatchup.kind == kind))
    return {"kind": kind, "champions": [{"id": cid, "name": name} for cid, name in champions],
            "cells": [list(row) for row in cells]}


def apply_changes(db: Session, kind: str, changes: list[MatchupChange], user_id: int) -> int:
    """Set cells from an admin's edits. A change is given as (row champion, column champion), either way round."""
    known = set(db.scalars(select(Champion.id)))
    wanted: dict[tuple[int, int], float | None] = {}
    for change in changes:
        if change.a == change.b:
            raise bad_request("A champion has no win rate with itself.")
        if change.a not in known or change.b not in known:
            raise bad_request(f"Unknown champion id {change.a if change.a not in known else change.b}.")
        rate = None if change.win_rate is None else round(change.win_rate, 1)
        a, b, rate, _ = canonical(kind, change.a, change.b, rate)
        wanted[(a, b)] = rate

    existing = {(m.champion_a_id, m.champion_b_id): m for m in db.scalars(
        select(ChampionMatchup).where(ChampionMatchup.kind == kind,
                                      ChampionMatchup.champion_a_id.in_({a for a, _ in wanted})))}
    for (a, b), rate in wanted.items():
        row = existing.get((a, b))
        if row is None:
            row = ChampionMatchup(kind=kind, champion_a_id=a, champion_b_id=b, games=0, wins=0)
            db.add(row)
        row.win_rate = rate
        row.edited = True
        row.updated_by_user_id = user_id
    db.commit()
    return len(wanted)


def reset(db: Session, kind: str) -> int:
    """Throw away every edit and load the matrix from its seed file again (empty when there is no file)."""
    count = import_matchups(db, kind, overwrite=True)
    db.commit()
    return count

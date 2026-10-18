"""Seed the champion x champion win rate matrices from the pair CSVs written by `scripts.champion_synergy`.

Unlike champions, the CSV is only the starting point: a matrix is imported when it has no rows, and from then on
the database is the source of truth (admins edit it in the app). `reset` in the admin API re-imports it.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.data.loader import SEED_DIR, _norm
from app.models import Champion, ChampionMatchup

log = logging.getLogger(__name__)

SEED_FILES = {"ally": "champion_synergy.csv", "enemy": "champion_counter.csv"}
KINDS = tuple(SEED_FILES)


def canonical(kind: str, a: int, b: int, win_rate: float | None, games: int = 0, wins: int = 0):
    """(a, b, win_rate, wins) with a < b. An "enemy" value is from the first champion's side, so swapping flips it."""
    if a < b:
        return a, b, win_rate, wins
    if kind == "enemy":
        win_rate = None if win_rate is None else round(100.0 - win_rate, 1)
        wins = games - wins
    return b, a, win_rate, wins


def _number(text: str | None, cast, default):
    try:
        return cast(text)
    except (TypeError, ValueError):
        return default


def read_matchup_csv(kind: str, ids_by_name: dict[str, int], seed_dir: Path = SEED_DIR) -> dict[tuple[int, int], dict]:
    """One matrix's seed CSV as {(a, b): row values} with a < b. `ids_by_name` maps normalised champion names
    to ids; rows naming other champions are skipped with a warning. Empty when there is no file."""
    path = seed_dir / SEED_FILES[kind]
    if not path.exists():
        return {}
    unknown: set[str] = set()
    cells: dict[tuple[int, int], dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            name_a, name_b = (row.get("champion_a") or "").strip(), (row.get("champion_b") or "").strip()
            a, b = ids_by_name.get(_norm(name_a)), ids_by_name.get(_norm(name_b))
            if a is None or b is None:
                unknown.update(n for n, i in ((name_a, a), (name_b, b)) if i is None)
                continue
            if a == b:
                continue
            games, wins = _number(row.get("games"), int, 0), _number(row.get("wins"), int, 0)
            rate = _number(row.get("smoothed_win_rate"), float, None)
            a, b, rate, wins = canonical(kind, a, b, rate, games, wins)
            cells[(a, b)] = {"kind": kind, "champion_a_id": a, "champion_b_id": b, "win_rate": rate,
                             "games": games, "wins": wins, "edited": False}
    if unknown:
        log.warning("seed data: %s names champions that are not in the game, skipped: %s",
                    SEED_FILES[kind], ", ".join(sorted(unknown)))
    return cells


def import_matchups(db: Session, kind: str, seed_dir: Path = SEED_DIR, overwrite: bool = False) -> int:
    """Load one matrix from its CSV. Does nothing when the matrix already has rows, unless `overwrite`.
    Returns the number of cells written."""
    if overwrite:
        db.execute(delete(ChampionMatchup).where(ChampionMatchup.kind == kind))
    elif db.scalar(select(func.count()).select_from(ChampionMatchup).where(ChampionMatchup.kind == kind)):
        return 0
    ids = {_norm(name): cid for cid, name in db.execute(select(Champion.id, Champion.name))}
    cells = read_matchup_csv(kind, ids, seed_dir)
    if cells:
        db.execute(insert(ChampionMatchup), list(cells.values()))
    return len(cells)


def seed_matchups(db: Session) -> None:
    for kind in KINDS:
        count = import_matchups(db, kind)
        if count:
            log.info("seed data: imported %s %s win rate pairs", count, kind)
    db.commit()


# ------------------------------------------------- champion renumbering (see champion_sync._renumber)
def detach_champion(db: Session, champion_id: int) -> list[dict]:
    """Take a champion's cells out of the database so its id can change; `attach_champion` puts them back."""
    touching = or_(ChampionMatchup.champion_a_id == champion_id, ChampionMatchup.champion_b_id == champion_id)
    rows = [{"kind": m.kind, "a": m.champion_a_id, "b": m.champion_b_id, "win_rate": m.win_rate, "games": m.games,
             "wins": m.wins, "edited": m.edited, "updated_by_user_id": m.updated_by_user_id}
            for m in db.scalars(select(ChampionMatchup).where(touching))]
    if rows:
        db.execute(delete(ChampionMatchup).where(touching))
    return rows


def attach_champion(db: Session, rows: list[dict], old_id: int, new_id: int) -> None:
    values = []
    for r in rows:
        first, second = (new_id if x == old_id else x for x in (r["a"], r["b"]))
        a, b, rate, wins = canonical(r["kind"], first, second, r["win_rate"], r["games"], r["wins"])
        values.append({"kind": r["kind"], "champion_a_id": a, "champion_b_id": b, "win_rate": rate,
                       "games": r["games"], "wins": wins, "edited": r["edited"],
                       "updated_by_user_id": r["updated_by_user_id"]})
    if values:
        db.execute(insert(ChampionMatchup), values)

"""Champion info edited by admins: win rate, pick rate and the attributes the simulation reads.

An edited column is listed in `Champion.edited_fields`, which stops the startup seed sync from writing the CSV
value back over it. Resetting a champion puts its CSV values back and clears that list.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.data.champion_sync import FIELDS
from app.data.loader import SeedDataError, load_seed_data
from app.models import Champion
from app.schemas.admin import ChampionChange


@dataclass(frozen=True)
class Editable:
    kind: str                       # "int", "float" or "choice"
    low: float = 0
    high: float = 0
    choices: tuple[str, ...] = ()


# database column -> what an admin may set it to
EDITABLE: dict[str, Editable] = {
    "win_rate": Editable("float", 0, 100),
    "pick_rate": Editable("float", 0, 100),
    "style": Editable("int", 1, 10),
    "difficulty": Editable("int", 1, 3),
    "damage_type": Editable("choice", choices=("P", "M", "PM")),
    "damage": Editable("int", 0, 5),
    "sturdiness": Editable("int", 0, 5),
    "crowd_control": Editable("int", 0, 5),
    "mobility": Editable("int", 0, 5),
    "utility": Editable("int", 0, 5),
    "scaling": Editable("int", 1, 3),
    "attack_range": Editable("int", 1, 3),
    "waveclear": Editable("int", 1, 3),
}


def _seed_values() -> dict[int, dict]:
    """Each CSV champion's value for every editable column, by id. Empty when the CSV cannot be read."""
    try:
        data = load_seed_data()
    except (SeedDataError, ValueError, KeyError):
        return {}
    return {c.id: {column: getattr(c, FIELDS[column]) for column in EDITABLE} for c in data.champions}


def _view(row: Champion, seed: dict | None) -> dict:
    edited = sorted(row.edited)
    return {
        "id": row.id, "name": row.name, "class": row.champ_class, "enabled": row.enabled,
        "roles": [r for r in (row.roles or "").split("|") if r],
        **{column: getattr(row, column) for column in EDITABLE},
        "edited": edited,
        # the CSV value of each edited column, so the page can show what a reset would bring back
        "seed": {column: seed[column] for column in edited if column in seed} if seed else {},
        "in_seed": seed is not None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_champions(db: Session) -> dict:
    seed = _seed_values()
    rows = db.scalars(select(Champion).order_by(Champion.name))
    return {"fields": {column: {"kind": e.kind, "min": e.low, "max": e.high, "choices": list(e.choices)}
                       for column, e in EDITABLE.items()},
            "champions": [_view(row, seed.get(row.id)) for row in rows]}


def _clean(champion: str, column: str, value) -> float | int | str:
    rule = EDITABLE.get(column)
    if rule is None:
        raise bad_request(f"{column!r} cannot be edited.")
    if rule.kind == "choice":
        if value not in rule.choices:
            raise bad_request(f"{champion}: {column} must be one of {', '.join(rule.choices)}.")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise bad_request(f"{champion}: {column} must be a number.")
    if rule.kind == "int":
        if value != int(value):
            raise bad_request(f"{champion}: {column} must be a whole number.")
        value = int(value)
    else:
        value = round(float(value), 2)
    if not rule.low <= value <= rule.high:
        raise bad_request(f"{champion}: {column} must be between {rule.low:g} and {rule.high:g}.")
    return value


def apply_changes(db: Session, changes: list[ChampionChange]) -> int:
    """Save admins' edits (all or nothing). Returns how many values changed."""
    rows = {c.id: c for c in db.scalars(select(Champion).where(Champion.id.in_({ch.id for ch in changes})))}
    planned: list[tuple[Champion, str, object]] = []
    for change in changes:
        row = rows.get(change.id)
        if row is None:
            raise bad_request(f"Unknown champion id {change.id}.")
        for column, value in change.values.items():
            planned.append((row, column, _clean(row.name, column, value)))

    count = 0
    for row, column, value in planned:
        edited = row.edited | {column}
        row.edited_fields = "|".join(sorted(edited))
        if getattr(row, column) != value:
            setattr(row, column, value)
            count += 1
    db.commit()
    return count


def reset(db: Session, champion_ids: list[int] | None = None) -> int:
    """Put the CSV values back for the given champions (all when None) and forget their edits.
    Returns how many champions had edits."""
    try:
        data = load_seed_data()
    except (SeedDataError, ValueError, KeyError) as exc:
        raise bad_request(f"The champion CSV could not be read, so nothing was reset: {exc}") from exc
    seed = {c.id: c for c in data.champions}
    query = select(Champion).where(Champion.edited_fields != "")
    if champion_ids is not None:
        query = query.where(Champion.id.in_(champion_ids))
    count = 0
    for row in db.scalars(query):
        source = seed.get(row.id)
        if source is not None:
            for column in row.edited:
                if column in FIELDS:
                    setattr(row, column, getattr(source, FIELDS[column]))
        row.edited_fields = ""
        count += 1
    db.commit()
    return count

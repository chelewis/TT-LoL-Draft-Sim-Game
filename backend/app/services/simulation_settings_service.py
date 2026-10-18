"""Simulation settings changed by admins: stored overrides of SIMULATION_CONFIG (see EDITABLE_SETTINGS)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import iso
from app.core.errors import bad_request
from app.game.config import (EDITABLE_SETTINGS, SIMULATION_CONFIG, config_value, flatten_overrides, simulation_config,
                             validate_overrides)
from app.models import SimulationSettings


def _row(db: Session) -> SimulationSettings | None:
    return db.scalar(select(SimulationSettings).order_by(SimulationSettings.id).limit(1))


def overrides(db: Session) -> dict:
    row = _row(db)
    return dict(row.overrides or {}) if row else {}


def current_config(db: Session) -> dict:
    """The config a simulation started now would use."""
    return simulation_config(overrides(db))


def describe(db: Session) -> dict:
    """Every editable setting with its default and current value."""
    row = _row(db)
    cfg = simulation_config(row.overrides if row else None)
    fields = [{**spec, "default": config_value(SIMULATION_CONFIG, spec["path"]),
               "value": config_value(cfg, spec["path"])} for spec in EDITABLE_SETTINGS]
    return {"fields": fields, "updated_at": iso(row.updated_at) if row else None}


def save(db: Session, values: dict[str, Any], user_id: int) -> dict:
    """Set some settings, keeping the others as they are. A value equal to its default drops the override."""
    try:
        validate_overrides(values)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    merged = flatten_overrides(overrides(db))
    for path, value in values.items():
        if value == config_value(SIMULATION_CONFIG, path):
            merged.pop(path, None)
        else:
            merged[path] = value
    row = _row(db)
    if row is None:
        row = SimulationSettings()
        db.add(row)
    row.overrides = validate_overrides(merged)
    row.updated_by_user_id = user_id
    db.commit()
    return describe(db)


def reset(db: Session, user_id: int) -> dict:
    row = _row(db)
    if row is not None:
        row.overrides = {}
        row.updated_by_user_id = user_id
        db.commit()
    return describe(db)

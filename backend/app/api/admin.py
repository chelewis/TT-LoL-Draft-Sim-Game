"""Admin-only endpoints for global config. Every route requires a user listed in LDM_ADMIN_USERNAMES."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models import User
from app.schemas.admin import MatchupChangesIn, PasswordResetIn, SimulationSettingsIn
from app.services import matchup_service as svc
from app.services import simulation_settings_service as sim_settings
from app.services import user_admin_service as users

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
log = logging.getLogger(__name__)


# ------------------------------------------------- champion win rate matrices
@router.get("/matchups/{kind}")
def get_matchups(kind: str, db: Session = Depends(get_db)):
    return svc.matrix(db, svc.check_kind(kind))


@router.put("/matchups/{kind}")
def update_matchups(kind: str, body: MatchupChangesIn, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    updated = svc.apply_changes(db, svc.check_kind(kind), body.changes, user.id)
    log.info("admin_matchups_updated user_id=%s kind=%s cells=%s", user.id, kind, updated)
    return {"updated": updated}


@router.post("/matchups/{kind}/reset")
def reset_matchups(kind: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    cells = svc.reset(db, svc.check_kind(kind))
    log.info("admin_matchups_reset user_id=%s kind=%s cells=%s", user.id, kind, cells)
    return {"cells": cells}


# ------------------------------------------------- simulation settings
@router.get("/simulation")
def get_simulation_settings(db: Session = Depends(get_db)):
    return sim_settings.describe(db)


@router.put("/simulation")
def update_simulation_settings(body: SimulationSettingsIn, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    out = sim_settings.save(db, body.values, user.id)
    log.info("admin_simulation_settings_updated user_id=%s settings=%s", user.id, sorted(body.values))
    return out


@router.post("/simulation/reset")
def reset_simulation_settings(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    out = sim_settings.reset(db, user.id)
    log.info("admin_simulation_settings_reset user_id=%s", user.id)
    return out


# ------------------------------------------------- users
@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    return users.list_users(db)


@router.post("/users/{user_id}/password", status_code=204)
def reset_user_password(user_id: int, body: PasswordResetIn, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    users.reset_password(db, user_id, body.password)
    log.info("admin_password_reset admin_id=%s user_id=%s", user.id, user_id)
    return Response(status_code=204)


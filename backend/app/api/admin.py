"""Admin-only endpoints for global config. Every route requires a user listed in LDM_ADMIN_USERNAMES."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models import User
from app.schemas.admin import MatchupChangesIn
from app.services import matchup_service as svc

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

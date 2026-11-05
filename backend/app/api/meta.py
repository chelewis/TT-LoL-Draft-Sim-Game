"""Read-only views of the in-game meta, for every signed-in player."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.services import meta_service

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/champions")
def champion_stats(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Every enabled champion with its win rate (from the against-team win rate table) and pick rate."""
    return meta_service.champion_stats(db)


@router.get("/pair")
def champion_pair(a: int = Query(...), b: int = Query(...), db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    """Two champions' same-team and against-team win rates (against: a's rate against b), with notes on how they
    interact in the simulation."""
    return meta_service.champion_pair(db, a, b)

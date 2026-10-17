from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.services import game_service as svc

router = APIRouter(prefix="/series", tags=["series"])


@router.get("/{series_id}")
async def get_series(series_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.series_result(db, series_id, user)

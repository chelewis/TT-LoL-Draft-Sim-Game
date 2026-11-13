from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.services import notification_service as svc

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ReadIn(BaseModel):
    ids: list[int] | None = Field(default=None, max_length=100)   # none: mark everything read


@router.get("")
def inbox(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.inbox(db, user)


@router.post("/read")
def mark_read(body: ReadIn | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.mark_read(db, user, (body or ReadIn()).ids)

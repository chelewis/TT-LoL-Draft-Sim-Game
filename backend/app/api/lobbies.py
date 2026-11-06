from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.game import LobbyCreate, SideSelect, TeamSelect
from app.services import game_service as svc
from app.services import lobby_rules
from app.websocket.manager import manager

router = APIRouter(prefix="/lobbies", tags=["lobbies"])


@router.post("", status_code=201)
async def create_lobby(body: LobbyCreate | None = None, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    settings = (body or LobbyCreate()).settings
    mode = (body or LobbyCreate()).mode
    lobby, game = svc.create_lobby(db, user, settings.model_dump(), mode)
    return svc.lobby_view(db, game, user)


@router.get("/rulesets")
def list_rulesets(_: User = Depends(get_current_user)):
    """The ruleset presets for the create-lobby form, and the rank tiers in order."""
    return lobby_rules.rulesets_view()


@router.post("/{lobby_code}/join")
async def join_lobby(lobby_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lobby, game, events = svc.join_lobby(db, user, lobby_code)
    await manager.publish(events)
    return svc.lobby_view(db, game, user)


@router.get("/{lobby_id}")
async def get_lobby(lobby_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = svc.game_for_lobby(db, lobby_id, user.id)
    await manager.publish(svc.expire_if_needed(db, game))
    return svc.lobby_view(db, game, user)


@router.post("/{lobby_id}/leave")
async def leave_lobby(lobby_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = svc.game_for_lobby(db, lobby_id, user.id)
    await manager.publish(svc.leave_lobby(db, game, user))
    return svc.lobby_view(db, game, user)


@router.post("/{lobby_id}/side")
async def choose_side(lobby_id: int, body: SideSelect, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    game = svc.game_for_lobby(db, lobby_id, user.id)
    await manager.publish(svc.set_side(db, game, user, body.side))
    return svc.game_state(db, game, user)


@router.post("/{lobby_id}/team")
async def choose_team(lobby_id: int, body: TeamSelect, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    game = svc.game_for_lobby(db, lobby_id, user.id)
    await manager.publish(svc.select_team(db, game, user, body.team_id, body.side))
    return svc.game_state(db, game, user)

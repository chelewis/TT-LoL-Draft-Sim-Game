from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import Game, User
from app.schemas.game import ChatIn, DraftActionIn, DraftHoverIn, LineupIn, ReadyIn, SeriesReadyIn
from app.services import game_service as svc
from app.websocket.manager import manager

router = APIRouter(prefix="/games", tags=["games"])


async def _load(db: Session, game_id: int, user: User, spectate: bool = False) -> Game:
    """Fetch the caller's game, first applying any expired lobby / draft timers. `spectate`: a read-only request,
    which members of the game's season may also make."""
    game = svc.get_game(db, game_id, user.id, spectate)
    events = svc.expire_if_needed(db, game)
    events += svc.advance_timeouts(db, game)
    await manager.publish(events)
    return game


@router.get("")
async def my_games(active: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [svc.lobby_view(db, g, user) for g in svc.user_games(db, user.id, active_only=active)]


@router.get("/{game_id}")
async def get_game(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.game_state(db, await _load(db, game_id, user, spectate=True), user)


@router.get("/{game_id}/state")
async def get_state(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.game_state(db, await _load(db, game_id, user, spectate=True), user)


@router.post("/{game_id}/ready")
async def ready(game_id: int, body: ReadyIn | None = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.set_ready(db, game, user, (body or ReadyIn()).ready))
    return svc.game_state(db, game, user)


# ------------------------------------------------------------------ draft
@router.get("/{game_id}/draft")
async def get_draft(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user, spectate=True)
    return svc.draft_view(db, game)


@router.post("/{game_id}/draft/pick")
async def pick(game_id: int, body: DraftActionIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.draft_action(db, game, user, "PICK", body.champion_id))
    return svc.draft_view(db, game)


@router.post("/{game_id}/draft/ban")
async def ban(game_id: int, body: DraftActionIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.draft_action(db, game, user, "BAN", body.champion_id))
    return svc.draft_view(db, game)


@router.post("/{game_id}/draft/hover")
async def hover(game_id: int, body: DraftHoverIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.draft_hover(db, game, user, body.champion_id, body.draft_action))
    return svc.draft_view(db, game)


# ----------------------------------------------------------------- lineup
@router.put("/{game_id}/lineup")
async def put_lineup(game_id: int, body: LineupIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.set_lineup(db, game, user, [a.model_dump() for a in body.assignments], body.side))
    return svc.game_state(db, game, user)


@router.get("/{game_id}/lineup/preview")
async def lineup_preview(game_id: int, side: str | None = None, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    return svc.comfort_preview(db, game, user, side)


@router.get("/{game_id}/matchups")
async def matchups(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    return svc.matchup_preview(db, game, user)


@router.post("/{game_id}/lineup/ready")
async def lineup_ready(game_id: int, side: str | None = None, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.confirm_lineup(db, game, user, side))
    return svc.game_state(db, game, user)


# ---------------------------------------------------------------- results
@router.get("/{game_id}/result")
async def result(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.game_result(db, await _load(db, game_id, user, spectate=True))


@router.get("/{game_id}/result/events")
async def result_events(game_id: int, after: int = 0, limit: int = 200, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user, spectate=True)
    return svc.result_events(db, game, after, max(1, min(limit, 500)))


@router.post("/{game_id}/rerun")
async def rerun(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.rerun_simulation(db, game, user))
    return svc.game_state(db, game, user)


@router.post("/{game_id}/series/ready")
async def series_ready(game_id: int, body: SeriesReadyIn | None = None, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    body = body or SeriesReadyIn()
    await manager.publish(svc.ready_next_game(db, game, user, body.ready, body.side))
    return svc.game_state(db, game, user)


@router.post("/{game_id}/rematch")
async def rematch(game_id: int, body: ReadyIn | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    await manager.publish(svc.ready_rematch(db, game, user, (body or ReadyIn()).ready))
    return svc.game_state(db, game, user)


# ------------------------------------------------------------------- chat
@router.get("/{game_id}/chat")
async def get_chat(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.chat_history(db, await _load(db, game_id, user, spectate=True))


@router.post("/{game_id}/chat", status_code=201)
async def post_chat(game_id: int, body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = await _load(db, game_id, user)
    message, events = svc.send_chat(db, game, user, body.text)
    await manager.publish(events)
    return message


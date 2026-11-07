from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.season import AdvanceIn, AutoSimIn, SeasonCreate, SeasonJoinIn, SeasonTeamIn
from app.services import season_match_service as matches
from app.services import season_service as svc
from app.websocket.manager import manager

router = APIRouter(prefix="/seasons", tags=["seasons"])


@router.post("", status_code=201)
def create_season(body: SeasonCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.season_view(db, svc.create_season(db, user, body), user)


@router.get("")
def my_seasons(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.list_seasons(db, user)


# the invite routes come before /{season_id} so "join" is never read as a season id
@router.get("/join/{code}")
def join_preview(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.join_preview(db, code, user)


@router.post("/join/{code}", status_code=201)
async def join_season(code: str, body: SeasonJoinIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    season = svc.join_season(db, code, user, body.team_id)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.get("/{season_id}")
def get_season(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.season_view(db, svc.get_season(db, season_id, user), user)


@router.post("/{season_id}/teams", status_code=201)
async def enter_team(season_id: int, body: SeasonTeamIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    svc.enter_team(db, season, user, body.team_id)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.delete("/{season_id}/teams/mine")
async def withdraw_team(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    svc.withdraw_team(db, season, user)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.post("/{season_id}/teams/{season_team_id}/release")
async def release_team(season_id: int, season_team_id: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """A manager leaves their team, or the creator removes them: the CPU runs the team from then on."""
    season = svc.get_season(db, season_id, user)
    await manager.publish(await run_in_threadpool(svc.release_team, db, season, user, season_team_id))
    if not matches.is_member(db, season, user.id):
        return None                     # you left the season
    return svc.season_view(db, season, user)


@router.post("/{season_id}/start")
async def start_season(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    svc.start_season(db, season, user)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.post("/{season_id}/advance")
async def advance_round(season_id: int, body: AdvanceIn | None = None, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    # a round can simulate many games: run it off the event loop so live drafts stay responsive
    events = await run_in_threadpool(svc.advance_round, db, season, user, (body or AdvanceIn()).force)
    await manager.publish(events)
    return svc.season_view(db, season, user)


@router.post("/{season_id}/cancel")
async def cancel_season(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    svc.cancel_season(db, season, user)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.get("/{season_id}/schedule")
def schedule(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.schedule_view(db, svc.get_season(db, season_id, user), user)


@router.get("/{season_id}/teams/{season_team_id}")
def team_detail(season_id: int, season_team_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return svc.team_detail(db, svc.get_season(db, season_id, user), season_team_id, user)


@router.post("/matches/{match_id}/play")
async def play_match(match_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    season, match = svc.get_match(db, match_id, user)
    game, events = matches.play_match(db, season, match, user)
    await manager.publish(events)
    return {"game_id": game.id, "series_id": game.series_id}


@router.post("/matches/{match_id}/auto")
async def auto_sim_match(match_id: int, body: AutoSimIn | None = None, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    season, match = svc.get_match(db, match_id, user)
    ready = (body or AutoSimIn()).ready
    await manager.publish(await run_in_threadpool(matches.auto_sim_my_match, db, season, match, user, ready))
    return svc.season_view(db, season, user)

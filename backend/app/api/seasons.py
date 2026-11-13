from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.season import (AdvanceIn, AutoSimIn, LanePickIn, PoolAddIn, PoolGenerateIn, SeasonCreate,
                                 SeasonJoinIn, SeasonTeamIn)
from app.services import season_draft_service as drafts
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
    season = svc.join_season(db, code, user, body)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.get("/{season_id}")
def get_season(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.season_view(db, svc.get_season(db, season_id, user), user)


@router.post("/{season_id}/teams", status_code=201)
async def enter_team(season_id: int, body: SeasonTeamIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    svc.enter_team(db, season, user, body)
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


# ------------------------------------------------------- player draft pool
@router.get("/{season_id}/pool")
def pool(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The season's players on no roster: the draft pool, or (once the season is under way) the free agents."""
    return drafts.pool_view(db, svc.get_season(db, season_id, user))


@router.post("/{season_id}/pool/players", status_code=201)
async def add_pool_players(season_id: int, body: PoolAddIn, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    drafts.add_pool_players(db, season, user, body.player_ids)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.post("/{season_id}/pool/generate", status_code=201)
async def generate_pool(season_id: int, body: PoolGenerateIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    drafts.generate_pool(db, season, user, body.per_role, body.strength)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.delete("/{season_id}/pool")
async def clear_pool(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    drafts.clear_pool(db, season, user)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


@router.delete("/{season_id}/pool/{player_id}")
async def remove_pool_player(season_id: int, player_id: int, db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    drafts.remove_pool_player(db, season, user, player_id)
    await manager.publish([matches.season_event(season.id)])
    return svc.season_view(db, season, user)


# ----------------------------------------------------------- player draft
@router.post("/{season_id}/draft/pick")
async def draft_pick(season_id: int, body: LanePickIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    await manager.publish(await run_in_threadpool(drafts.make_pick, db, season, user, body.player_id, body.lane))
    return svc.season_view(db, season, user)


@router.post("/{season_id}/draft/auto")
async def draft_auto_pick(season_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The best available player for the team on the clock (its manager, or the creator moving the draft on)."""
    season = svc.get_season(db, season_id, user)
    await manager.publish(await run_in_threadpool(drafts.auto_pick_now, db, season, user))
    return svc.season_view(db, season, user)


# ----------------------------------------------------------- free agency
@router.post("/{season_id}/free-agents/sign")
async def sign_free_agent(season_id: int, body: LanePickIn, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    season = svc.get_season(db, season_id, user)
    await manager.publish(drafts.sign_free_agent(db, season, user, body.player_id, body.lane))
    return svc.season_view(db, season, user)

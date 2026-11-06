"""Public sharing: publish your players, coaches and teams; search other users' public ones and copy them."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.management import PublicIn
from app.services import sharing_service as share
from app.services import team_management_service as teams

router = APIRouter(tags=["public"])

def Stat():
    """A 1-10 attribute bound (a fresh Query per parameter)."""
    return Query(default=None, ge=1, le=10)


# ---------------------------------------------------------------- publish
@router.put("/players/{player_id}/public")
def publish_player(player_id: int, body: PublicIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Only an unedited Riot import can be public; it's renamed to its Riot game name."""
    return teams.player_view(share.set_player_public(db, user.id, player_id, body.public))


@router.put("/coaches/{coach_id}/public")
def publish_coach(coach_id: int, body: PublicIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return teams.coach_view(share.set_coach_public(db, user.id, coach_id, body.public))


@router.put("/teams/{team_id}/public")
def publish_team(team_id: int, body: PublicIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A public team needs a complete roster of players that could each be public."""
    return teams.team_view(db, share.set_team_public(db, user.id, team_id, body.public))


# ----------------------------------------------------------------- search
@router.get("/public/players")
def search_players(
    q: str | None = Query(default=None, max_length=40), role: str | None = None,
    rank_min: str | None = None, rank_max: str | None = None, region: str | None = Query(default=None, max_length=8),
    aggr_min: int | None = Stat(), aggr_max: int | None = Stat(), aware_min: int | None = Stat(),
    aware_max: int | None = Stat(), pos_min: int | None = Stat(), pos_max: int | None = Stat(),
    dmg_min: int | None = Stat(), dmg_max: int | None = Stat(), cs_min: int | None = Stat(), cs_max: int | None = Stat(),
    total_min: int | None = None, total_max: int | None = None,
    champions: list[int] = Query(default_factory=list), tags: list[str] = Query(default_factory=list),
    sort: str = "newest", offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Other users' public players. Every filter is optional; champions and tags must all match."""
    lows = {"aggr": aggr_min, "aware": aware_min, "pos": pos_min, "dmg": dmg_min, "cs": cs_min}
    highs = {"aggr": aggr_max, "aware": aware_max, "pos": pos_max, "dmg": dmg_max, "cs": cs_max}
    return share.search_players(
        db, user.id, q=q, role=role, rank_min=rank_min, rank_max=rank_max, region=region,
        stat_min={k: v for k, v in lows.items() if v is not None},
        stat_max={k: v for k, v in highs.items() if v is not None},
        total_min=total_min, total_max=total_max, champions=champions, tags=tags,
        sort=sort, offset=offset, limit=limit)


@router.get("/public/coaches")
def search_coaches(
    q: str | None = Query(default=None, max_length=40), draft_min: int | None = Stat(), draft_max: int | None = Stat(),
    synergy_min: int | None = Stat(), synergy_max: int | None = Stat(), sort: str = "newest",
    offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    return share.search_coaches(db, user.id, q=q, draft_min=draft_min, draft_max=draft_max,
                                synergy_min=synergy_min, synergy_max=synergy_max, sort=sort,
                                offset=offset, limit=limit)


@router.get("/public/teams")
def search_teams(
    q: str | None = Query(default=None, max_length=40), style: str | None = None, focus: str | None = None,
    total_min: int | None = None, total_max: int | None = None, rank_min: str | None = None,
    rank_max: str | None = None, champion: int | None = None, player: str | None = Query(default=None, max_length=40),
    coach_draft_min: int | None = Stat(), coach_synergy_min: int | None = Stat(), sort: str = "newest",
    offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    return share.search_teams(db, user.id, q=q, style=style, focus=focus, total_min=total_min,
                              total_max=total_max, rank_min=rank_min, rank_max=rank_max, champion=champion,
                              player=player, coach_draft_min=coach_draft_min,
                              coach_synergy_min=coach_synergy_min, sort=sort, offset=offset, limit=limit)


# ------------------------------------------------------------------- copy
@router.post("/public/players/{player_id}/copy", status_code=201)
def copy_player(player_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return teams.player_view(share.copy_player(db, user.id, player_id))


@router.post("/public/coaches/{coach_id}/copy", status_code=201)
def copy_coach(coach_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return teams.coach_view(share.copy_coach(db, user.id, coach_id))


@router.post("/public/teams/{team_id}/copy", status_code=201)
def copy_team(team_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return teams.team_view(db, share.copy_team(db, user.id, team_id))

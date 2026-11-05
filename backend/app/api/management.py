"""Champion catalogue and team / player / coach management endpoints (spec 5.6, 7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.game.config import DRAFT_CONFIG, LANES, MANAGEMENT_CONFIG
from app.models import Champion, Coach, Lobby, Player, Team, User
from app.schemas.management import ChampionFitIn, CoachIn, PlayerIn, TeamIn, TeamInsightsIn
from app.services import champion_fit, game_service, lobby_rules, playstyle_service, team_insights_service
from app.services.simulation_settings_service import current_config
from app.services import team_management_service as svc

router = APIRouter(tags=["management"])


@router.get("/config")
def public_config(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Game rules the client needs for forms and hints (the server still enforces everything)."""
    m = MANAGEMENT_CONFIG
    sim = current_config(db)
    ts, lane, coach = sim["team_style"], sim["lane"], sim["coach"]
    return {
        # the live numbers behind the team editor's field help
        "team_rules": {
            "styles_enabled": ts["enabled"],
            "primary_bonus": ts["primary_bonus"], "secondary_bonus": ts["secondary_bonus"],
            "scaling_lane_penalty": ts["scaling_lane_penalty"], "focus_lane_bonus": ts["focus_lane_bonus"],
            "focus_cs_bonus": sim["cs"]["focus_bonus"], "focus_assist_boost": lane["focus_assist_boost"],
            "jungle_assist": lane["assist"]["jungle"], "support_assist": lane["assist"]["support_to_bot"],
            "coach_synergy_scale": coach["synergy_scale"], "coach_draft_scale": coach["draft_matchup_scale"],
            "off_role_penalty": sim["off_role"]["lane_penalty"] if sim["off_role"]["enabled"] else 0,
        },
        "lanes": LANES,
        "draft_timer_seconds": DRAFT_CONFIG["timer_seconds"],
        "player_stat_budget": m["player_stat_budget"],
        "coach_stat_budget": m["coach_stat_budget"],
        "stat_range": m["stat_range"],
        "champion_pool_size": m["champion_pool_size"],
    }


@router.get("/playstyle-tags")
def list_playstyle_tags(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Enabled playstyle tags, for labels and tooltips."""
    return [playstyle_service.public_tag(t) for t in playstyle_service.enabled_tags(db)]


@router.get("/champions")
def list_champions(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(Champion).where(Champion.enabled.is_(True)).order_by(Champion.name))
    return [r.to_engine().to_dict() for r in rows]


@router.post("/champion-fit")
def rank_champion_fit(body: ChampionFitIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Champions ranked by how well these (possibly unsaved) stats and pool score with them in lane."""
    return champion_fit.rank_champions(db, body.aggr, body.aware, body.pos, body.dmg, body.pool, body.limit,
                                       body.role, body.secondary_role)


@router.post("/team-insights")
def team_insights(body: TeamInsightsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Strengths, weaknesses, suggested playstyles and focus lanes, and ideal comps for an (unsaved) team."""
    return team_insights_service.team_insights(db, user.id, body)


# ------------------------------------------------------------------- teams
@router.get("/teams")
def list_teams(selectable: bool | None = None, game_id: int | None = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """With `game_id`, each team also lists `rule_issues`: why it breaks that lobby's restrictions."""
    views = svc.list_teams(db, user.id, selectable)
    if game_id is not None:
        game = game_service.get_game(db, game_id, user.id)
        settings = db.get(Lobby, game.lobby_id).settings or {}
        for v in views:
            v["rule_issues"] = lobby_rules.team_rule_issues(v, settings)
    return views


@router.post("/teams", status_code=201)
def create_team(body: TeamIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.team_view(db, svc.create_team(db, user.id, body))


@router.get("/teams/{team_id}")
def get_team(team_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.team_view(db, svc.get_visible(db, Team, team_id, user.id))


@router.put("/teams/{team_id}")
def update_team(team_id: int, body: TeamIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.team_view(db, svc.update_team(db, user.id, team_id, body))


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(team_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc.delete_team(db, user.id, team_id)
    return Response(status_code=204)


@router.post("/teams/{team_id}/duplicate", status_code=201)
def duplicate_team(team_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.team_view(db, svc.duplicate_team(db, user.id, team_id))


# ----------------------------------------------------------------- players
@router.get("/players")
def list_players(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [svc.player_view(p) for p in svc.list_players(db, user.id)]


@router.post("/players", status_code=201)
def create_player(body: PlayerIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.player_view(svc.create_player(db, user.id, body))


@router.get("/players/{player_id}")
def get_player(player_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.player_view(svc.get_visible(db, Player, player_id, user.id))


@router.put("/players/{player_id}")
def update_player(player_id: int, body: PlayerIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return svc.player_view(svc.update_player(db, user.id, player_id, body))


@router.delete("/players/{player_id}", status_code=204)
def delete_player(player_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc.delete_player(db, user.id, player_id)
    return Response(status_code=204)


# ----------------------------------------------------------------- coaches
@router.get("/coaches")
def list_coaches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [svc.coach_view(c) for c in svc.list_coaches(db, user.id)]


@router.post("/coaches", status_code=201)
def create_coach(body: CoachIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.coach_view(svc.create_coach(db, user.id, body))


@router.put("/coaches/{coach_id}")
def update_coach(coach_id: int, body: CoachIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.coach_view(svc.update_coach(db, user.id, coach_id, body))


@router.delete("/coaches/{coach_id}", status_code=204)
def delete_coach(coach_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc.delete_coach(db, user.id, coach_id)
    return Response(status_code=204)


# ------------------------------------------------------------- riot import
from app.core.config import settings  # noqa: E402
from app.integrations.riot.client import RiotClient  # noqa: E402
from app.integrations.riot.config import PLATFORM_CLUSTER  # noqa: E402
from app.integrations.riot.errors import RiotError  # noqa: E402
from app.schemas.management import RiotPreviewIn  # noqa: E402
from app.services import riot_import_service  # noqa: E402


def get_riot_client():
    """Dependency: a Riot client for this request (tests override it with a fake)."""
    client = RiotClient(settings.riot_api_key)
    try:
        yield client
    finally:
        client.close()


def get_optional_riot_client():
    """Dependency: a Riot client, or None when Riot import is not set up (tests override it with a fake)."""
    if not settings.riot_enabled:
        yield None
        return
    yield from get_riot_client()


def _riot_guard():
    if not settings.riot_enabled:
        raise HTTPException(status_code=503, detail="Riot import is not set up on this server.")


@router.get("/riot/status")
def riot_status(_: User = Depends(get_current_user)):
    return {"enabled": settings.riot_enabled, "regions": sorted(PLATFORM_CLUSTER)}


# plain `def` endpoints: they make several blocking HTTP calls and run in FastAPI's thread pool
@router.post("/riot/preview", dependencies=[Depends(get_current_user), Depends(_riot_guard)])
def riot_preview(body: RiotPreviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 client: RiotClient = Depends(get_riot_client)):
    try:
        return riot_import_service.preview(db, client, user.id, riot_id=body.riot_id, region=body.region, role=body.role)
    except RiotError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/players/{player_id}/riot-refresh", dependencies=[Depends(get_current_user), Depends(_riot_guard)])
def riot_refresh(player_id: int, role: str | None = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user), client: RiotClient = Depends(get_riot_client)):
    player = svc.get_owned(db, Player, player_id, user.id)
    try:
        return riot_import_service.refresh(db, client, user.id, player, role)
    except RiotError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

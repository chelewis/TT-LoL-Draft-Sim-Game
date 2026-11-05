"""Admin-only endpoints for global config. Every route requires a user listed in LDM_ADMIN_USERNAMES."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.api.management import get_optional_riot_client
from app.integrations.riot import challenges
from app.integrations.riot.errors import RiotError
from app.models import User
from app.schemas.admin import MatchupChangesIn, SimulationSettingsIn
from app.schemas.management import CoachIn, PlayerIn, TeamIn
from app.services import matchup_service as svc
from app.services import simulation_settings_service as sim_settings
from app.services import team_management_service as teams

from app.schemas.admin import (ChampionChangesIn, ChampionResetIn, MatchupChangesIn, PasswordResetIn,
                               PlaystyleTagIn, SimulationSettingsIn)
from app.services import champion_admin_service as champion_admin
from app.services import matchup_service as svc
from app.services import simulation_settings_service as sim_settings
from app.services import playstyle_service as playstyle
from app.services import user_admin_service as users

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
log = logging.getLogger(__name__)


# ------------------------------------------------- champion info (win rate, pick rate, attributes)
@router.get("/champions")
def list_champions(db: Session = Depends(get_db)):
    return champion_admin.list_champions(db)


@router.put("/champions")
def update_champions(body: ChampionChangesIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    updated = champion_admin.apply_changes(db, body.changes)
    log.info("admin_champions_updated user_id=%s champions=%s values=%s",
             user.id, sorted(c.id for c in body.changes), updated)
    return {"updated": updated}


@router.post("/champions/reset")
def reset_champions(body: ChampionResetIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    count = champion_admin.reset(db, body.ids)
    log.info("admin_champions_reset user_id=%s ids=%s champions=%s", user.id, body.ids, count)
    return {"reset": count}


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


# ------------------------------------------------- simulation settings
@router.get("/simulation")
def get_simulation_settings(db: Session = Depends(get_db)):
    return sim_settings.describe(db)


@router.put("/simulation")
def update_simulation_settings(body: SimulationSettingsIn, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    out = sim_settings.save(db, body.values, user.id)
    log.info("admin_simulation_settings_updated user_id=%s settings=%s", user.id, sorted(body.values))
    return out


@router.post("/simulation/reset")
def reset_simulation_settings(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    out = sim_settings.reset(db, user.id)
    log.info("admin_simulation_settings_reset user_id=%s", user.id)
    return out


# ------------------------------------------------- default teams / players / coaches
# Default content has owner_user_id = NULL; the management service treats owner None as that scope.
# Reads use the normal /teams, /players and /coaches routes, which already list defaults.
@router.post("/defaults/teams", status_code=201)
def create_default_team(body: TeamIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    team = teams.create_team(db, None, body)
    log.info("admin_default_team_created user_id=%s id=%s", user.id, team.id)
    return teams.team_view(db, team)


@router.put("/defaults/teams/{team_id}")
def update_default_team(team_id: int, body: TeamIn, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    team = teams.update_team(db, None, team_id, body)
    log.info("admin_default_team_updated user_id=%s id=%s", user.id, team_id)
    return teams.team_view(db, team)


@router.delete("/defaults/teams/{team_id}", status_code=204)
def delete_default_team(team_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    teams.delete_team(db, None, team_id)
    log.info("admin_default_team_deleted user_id=%s id=%s", user.id, team_id)
    return Response(status_code=204)


@router.post("/defaults/players", status_code=201)
def create_default_player(body: PlayerIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    player = teams.create_player(db, None, body)
    log.info("admin_default_player_created user_id=%s id=%s", user.id, player.id)
    return teams.player_view(player)


@router.put("/defaults/players/{player_id}")
def update_default_player(player_id: int, body: PlayerIn, db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    player = teams.update_player(db, None, player_id, body)
    log.info("admin_default_player_updated user_id=%s id=%s", user.id, player_id)
    return teams.player_view(player)


@router.delete("/defaults/players/{player_id}", status_code=204)
def delete_default_player(player_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    teams.delete_player(db, None, player_id)   # also clears it from every team that rostered it, users' included
    log.info("admin_default_player_deleted user_id=%s id=%s", user.id, player_id)
    return Response(status_code=204)


@router.post("/defaults/coaches", status_code=201)
def create_default_coach(body: CoachIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    coach = teams.create_coach(db, None, body)
    log.info("admin_default_coach_created user_id=%s id=%s", user.id, coach.id)
    return teams.coach_view(coach)


@router.put("/defaults/coaches/{coach_id}")
def update_default_coach(coach_id: int, body: CoachIn, db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    coach = teams.update_coach(db, None, coach_id, body)
    log.info("admin_default_coach_updated user_id=%s id=%s", user.id, coach_id)
    return teams.coach_view(coach)


@router.delete("/defaults/coaches/{coach_id}", status_code=204)
def delete_default_coach(coach_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    teams.delete_coach(db, None, coach_id)   # teams using it, users' included, are left without a coach
    log.info("admin_default_coach_deleted user_id=%s id=%s", user.id, coach_id)
    return Response(status_code=204)


# ------------------------------------------------- users
@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    return users.list_users(db)


@router.post("/users/{user_id}/password", status_code=204)
def reset_user_password(user_id: int, body: PasswordResetIn, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    users.reset_password(db, user_id, body.password)
    log.info("admin_password_reset admin_id=%s user_id=%s", user.id, user_id)
    return Response(status_code=204)


# ---------------------------------------------------------- playstyle tags
@router.get("/playstyle-tags")
def list_playstyle_tags(db: Session = Depends(get_db)):
    return playstyle.list_all(db)


@router.get("/playstyle-tags/options")
def playstyle_tag_options(client=Depends(get_optional_riot_client)):
    """Pickers for the tag editor. The challenge list comes from Riot when a key is set (cached for a day)."""
    if client is None:
        return playstyle.options(None, "Riot import is not set up, so challenges can only be added by id.")
    try:
        listed = challenges.load(lambda: client.challenges_config("NA1"))
    except RiotError as exc:
        return playstyle.options(None, f"Could not load Riot's challenge list: {exc.message}")
    return playstyle.options(listed)


@router.post("/playstyle-tags", status_code=201)
def create_playstyle_tag(body: PlaystyleTagIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    log.info("admin %s created playstyle tag %s", user.username, body.key)
    return playstyle.create(db, body, user.id)


@router.put("/playstyle-tags/{tag_id}")
def update_playstyle_tag(tag_id: int, body: PlaystyleTagIn, db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    log.info("admin %s updated playstyle tag %s", user.username, body.key)
    return playstyle.update(db, tag_id, body, user.id)


@router.delete("/playstyle-tags/{tag_id}")
def delete_playstyle_tag(tag_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    log.info("admin %s deleted playstyle tag %s", user.username, tag_id)
    return playstyle.delete(db, tag_id)

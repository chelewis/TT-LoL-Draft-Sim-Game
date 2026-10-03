"""Create / edit / delete teams, players and coaches, plus the validation rules of spec section 5.6."""
from __future__ import annotations

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.game.config import LANES, MANAGEMENT_CONFIG
from app.models import Champion, Coach, Player, PlayerPoolEntry, Team, TeamRosterSlot
from app.schemas.management import CoachIn, PlayerIn, TeamIn

log = logging.getLogger(__name__)
CFG = MANAGEMENT_CONFIG
STYLES = ("early", "scaling", "teamfight", "skirmish")


# ------------------------------------------------------------------ views
def over_budget_by(player: Player, cfg: dict = CFG) -> int:
    """Points over the soft stat ceiling (0 for default players and within-budget players)."""
    if player.owner_user_id is None and cfg["system_players_exempt"]:
        return 0
    return max(0, player.stat_total - cfg["player_stat_budget"])


def player_view(p: Player) -> dict:
    return {
        "id": p.id, "name": p.name, "role": p.role, "age": p.age, "region": p.region,
        "aggr": p.aggr, "aware": p.aware, "pos": p.pos, "dmg": p.dmg, "cs": p.cs,
        "pool": p.pool, "stat_total": p.stat_total, "over_budget_by": over_budget_by(p),
        "is_default": p.owner_user_id is None,
        "riot": None if not p.riot_puuid else {
            "game_name": p.riot_game_name, "tag_line": p.riot_tag_line, "region": p.riot_region,
            "imported_at": iso(p.riot_imported_at), "verified": False, "data_source": p.riot_data_source,
            "games_used": p.riot_games_used, "is_solo_source": p.riot_data_source in (None, "SOLO")},
    }


def coach_view(c: Coach | None) -> dict | None:
    if c is None:
        return None
    return {"id": c.id, "name": c.name, "draft": c.draft, "synergy": c.synergy, "is_default": c.owner_user_id is None}


def team_issues(team: Team) -> list[str]:
    issues = []
    filled = {s.lane for s in team.slots}
    missing = [lane for lane in LANES if lane not in filled]
    if missing:
        issues.append("Missing players for: " + ", ".join(missing))
    if team.coach is None:
        issues.append("No coach selected")
    if not team.style1 or not team.style2:
        issues.append("Choose two playstyles")
    return issues


def team_view(db: Session, team: Team) -> dict:
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_([s.player_id for s in team.slots])))}
    roster = {s.lane: player_view(players[s.player_id]) for s in team.slots if s.player_id in players}
    over = [{"player_id": p["id"], "name": p["name"], "total": p["stat_total"], "over_by": p["over_budget_by"]}
            for p in roster.values() if p["over_budget_by"] > 0]
    issues = team_issues(team)
    return {
        "id": team.id, "name": team.name, "logo": team.logo, "region": team.region, "fanbase": team.fanbase,
        "style1": team.style1, "style2": team.style2, "focus1": team.focus1, "focus2": team.focus2,
        "coach": coach_view(team.coach),
        "roster": {lane: roster.get(lane) for lane in LANES},
        "selectable": not issues, "issues": issues,
        "over_budget": bool(over), "over_budget_players": over,
        "is_default": team.owner_user_id is None,
    }


# ------------------------------------------------------------ access helpers
def _visible(model, user_id: int):
    return or_(model.owner_user_id == user_id, model.owner_user_id.is_(None))


def get_visible(db: Session, model, obj_id: int, user_id: int):
    obj = db.get(model, obj_id)
    if obj is None or (obj.owner_user_id is not None and obj.owner_user_id != user_id):
        raise not_found()
    return obj


def get_owned(db: Session, model, obj_id: int, user_id: int):
    obj = get_visible(db, model, obj_id, user_id)
    if obj.owner_user_id is None:
        raise forbidden("Default content is read-only. Duplicate it to make your own copy.")
    return obj


def _check_limit(db: Session, model, user_id: int, limit: int, label: str) -> None:
    count = db.scalar(select(func.count()).select_from(model).where(model.owner_user_id == user_id))
    if count >= limit:
        raise conflict(f"You have reached the limit of {limit} {label}.")


# ---------------------------------------------------------------- players
def _validate_player(db: Session, body: PlayerIn) -> None:
    lo, hi = CFG["stat_range"]
    if body.role not in LANES:
        raise bad_request(f"Role must be one of {', '.join(LANES)}.")
    for stat in ("aggr", "aware", "pos", "dmg", "cs"):
        value = getattr(body, stat)
        if not lo <= value <= hi:
            raise bad_request(f"{stat} must be between {lo} and {hi}.")
    if len(body.pool) != CFG["champion_pool_size"] or len(set(body.pool)) != len(body.pool):
        raise bad_request(f"A champion pool needs exactly {CFG['champion_pool_size']} different champions.")
    known = set(db.scalars(select(Champion.id).where(Champion.id.in_(body.pool), Champion.enabled.is_(True))))
    if known != set(body.pool):
        raise bad_request("The champion pool contains an unknown champion.")
    total = body.aggr + body.aware + body.pos + body.dmg + body.cs
    if CFG["enforce_budget"] and total > CFG["player_stat_budget"]:
        raise bad_request(f"Stats may total at most {CFG['player_stat_budget']}.")


def _apply_riot(player: Player, body: PlayerIn, user_id: int) -> None:
    """Link the player to a Riot account if the body carries a valid preview token for this user."""
    if not body.riot_ref:
        return
    from app.services.riot_import_service import decode_riot_ref
    ref = decode_riot_ref(body.riot_ref, user_id)
    player.riot_puuid, player.riot_game_name = ref["puuid"], ref["game_name"]
    player.riot_tag_line, player.riot_region = ref["tag_line"], ref["region"]
    player.riot_imported_at = utcnow()
    player.riot_data_source, player.riot_games_used = ref.get("source"), ref.get("games")


def _apply_player(player: Player, body: PlayerIn) -> None:
    for field in ("name", "role", "age", "region", "aggr", "aware", "pos", "dmg", "cs"):
        setattr(player, field, getattr(body, field))
    player.pool_entries = [PlayerPoolEntry(position=i + 1, champion_id=cid) for i, cid in enumerate(body.pool)]


def create_player(db: Session, user_id: int, body: PlayerIn) -> Player:
    _validate_player(db, body)
    _check_limit(db, Player, user_id, CFG["max_players_per_user"], "players")
    player = Player(owner_user_id=user_id)
    _apply_player(player, body)
    _apply_riot(player, body, user_id)
    db.add(player)
    db.commit()
    return player


def update_player(db: Session, user_id: int, player_id: int, body: PlayerIn) -> Player:
    player = get_owned(db, Player, player_id, user_id)
    _validate_player(db, body)
    if body.role != player.role:
        slot = db.scalar(select(TeamRosterSlot).where(TeamRosterSlot.player_id == player.id))
        if slot is not None and not CFG["allow_off_role_roster"]:
            raise conflict("This player is on a team roster; remove them from it before changing their role.")
    player.pool_entries.clear()
    db.flush()
    _apply_player(player, body)
    _apply_riot(player, body, user_id)
    db.commit()
    return player


def delete_player(db: Session, user_id: int, player_id: int) -> None:
    player = get_owned(db, Player, player_id, user_id)
    for slot in db.scalars(select(TeamRosterSlot).where(TeamRosterSlot.player_id == player.id)):
        db.delete(slot)  # the affected teams become unselectable until refilled
    db.delete(player)
    db.commit()


# ---------------------------------------------------------------- coaches
def _validate_coach(body: CoachIn) -> None:
    lo, hi = CFG["stat_range"]
    for stat in ("draft", "synergy"):
        if not lo <= getattr(body, stat) <= hi:
            raise bad_request(f"{stat} must be between {lo} and {hi}.")
    if body.draft + body.synergy > CFG["coach_stat_budget"]:
        raise bad_request(f"Draft + Synergy may total at most {CFG['coach_stat_budget']}.")


def create_coach(db: Session, user_id: int, body: CoachIn) -> Coach:
    _validate_coach(body)
    _check_limit(db, Coach, user_id, CFG["max_coaches_per_user"], "coaches")
    coach = Coach(owner_user_id=user_id, name=body.name, draft=body.draft, synergy=body.synergy)
    db.add(coach)
    db.commit()
    return coach


def update_coach(db: Session, user_id: int, coach_id: int, body: CoachIn) -> Coach:
    coach = get_owned(db, Coach, coach_id, user_id)
    _validate_coach(body)
    coach.name, coach.draft, coach.synergy = body.name, body.draft, body.synergy
    db.commit()
    return coach


def delete_coach(db: Session, user_id: int, coach_id: int) -> None:
    coach = get_owned(db, Coach, coach_id, user_id)
    for team in db.scalars(select(Team).where(Team.coach_id == coach.id)):
        team.coach_id = None
    db.delete(coach)
    db.commit()


# ------------------------------------------------------------------ teams
def _validate_team(db: Session, user_id: int, body: TeamIn, team_id: int | None) -> None:
    for style in (body.style1, body.style2):
        if style is not None and style not in STYLES:
            raise bad_request(f"Playstyle must be one of {', '.join(STYLES)}.")
    if body.style1 and body.style1 == body.style2:
        raise bad_request("Choose two different playstyles.")
    for focus in (body.focus1, body.focus2):
        if focus is not None and focus not in LANES:
            raise bad_request(f"Focus lane must be one of {', '.join(LANES)}.")
    if body.focus1 and body.focus1 == body.focus2:
        raise bad_request("Choose two different focus lanes.")
    if body.coach_id is not None:
        get_visible(db, Coach, body.coach_id, user_id)
    seen: set[int] = set()
    for lane, player_id in body.roster.items():
        if lane not in LANES:
            raise bad_request(f"Unknown lane {lane!r}.")
        if player_id is None:
            continue
        if player_id in seen:
            raise bad_request("A player can only fill one roster slot.")
        seen.add(player_id)
        player = get_visible(db, Player, player_id, user_id)
        if player.role != lane and not CFG["allow_off_role_roster"]:
            raise bad_request(f"{player.name} is a {player.role} player and cannot play {lane}.")
    duplicate = db.scalar(select(Team).where(Team.owner_user_id == user_id, Team.name == body.name))
    if duplicate is not None and duplicate.id != team_id:
        raise conflict("You already have a team with that name.")


def _apply_team(team: Team, body: TeamIn) -> None:
    for field in ("name", "logo", "region", "fanbase", "style1", "style2", "focus1", "focus2", "coach_id"):
        setattr(team, field, getattr(body, field))
    team.slots = [TeamRosterSlot(lane=lane, player_id=pid) for lane, pid in body.roster.items() if pid is not None]


def create_team(db: Session, user_id: int, body: TeamIn) -> Team:
    _validate_team(db, user_id, body, None)
    _check_limit(db, Team, user_id, CFG["max_teams_per_user"], "teams")
    team = Team(owner_user_id=user_id)
    _apply_team(team, body)
    db.add(team)
    db.commit()
    return team


def update_team(db: Session, user_id: int, team_id: int, body: TeamIn) -> Team:
    team = get_owned(db, Team, team_id, user_id)
    _validate_team(db, user_id, body, team.id)
    team.slots.clear()
    db.flush()
    _apply_team(team, body)
    db.commit()
    return team


def delete_team(db: Session, user_id: int, team_id: int) -> None:
    team = get_owned(db, Team, team_id, user_id)
    db.delete(team)
    db.commit()


def duplicate_team(db: Session, user_id: int, team_id: int) -> Team:
    """Copy a visible team (and its roster players and coach) into the user's account."""
    source = get_visible(db, Team, team_id, user_id)
    _check_limit(db, Team, user_id, CFG["max_teams_per_user"], "teams")

    coach = None
    if source.coach is not None:
        coach = Coach(owner_user_id=user_id, name=source.coach.name, draft=source.coach.draft,
                      synergy=source.coach.synergy)
        db.add(coach)

    copies: dict[str, Player] = {}
    for slot in source.slots:
        original = db.get(Player, slot.player_id)
        copy = Player(owner_user_id=user_id, name=original.name, role=original.role, age=original.age,
                      region=original.region, aggr=original.aggr, aware=original.aware, pos=original.pos,
                      dmg=original.dmg, cs=original.cs)
        copy.pool_entries = [PlayerPoolEntry(position=e.position, champion_id=e.champion_id)
                             for e in original.pool_entries]
        db.add(copy)
        copies[slot.lane] = copy
    db.flush()

    base_name = f"{source.name} (copy)"
    name, n = base_name, 2
    while db.scalar(select(Team).where(Team.owner_user_id == user_id, Team.name == name)):
        name, n = f"{base_name} {n}", n + 1
    team = Team(owner_user_id=user_id, name=name[:40], logo=source.logo, region=source.region,
                fanbase=source.fanbase, style1=source.style1, style2=source.style2,
                focus1=source.focus1, focus2=source.focus2, coach_id=coach.id if coach else None)
    team.slots = [TeamRosterSlot(lane=lane, player_id=p.id) for lane, p in copies.items()]
    db.add(team)
    db.commit()
    return team


# ----------------------------------------------------------------- lists
def list_teams(db: Session, user_id: int, selectable: bool | None = None) -> list[dict]:
    teams = db.scalars(select(Team).where(_visible(Team, user_id)).order_by(Team.owner_user_id.is_(None), Team.name))
    views = [team_view(db, t) for t in teams]
    if selectable is not None:
        views = [v for v in views if v["selectable"] == selectable]
    return views


def list_players(db: Session, user_id: int) -> list[Player]:
    return list(db.scalars(select(Player).where(_visible(Player, user_id))
                           .order_by(Player.owner_user_id.is_(None), Player.name)))


def list_coaches(db: Session, user_id: int) -> list[Coach]:
    return list(db.scalars(select(Coach).where(_visible(Coach, user_id))
                           .order_by(Coach.owner_user_id.is_(None), Coach.name)))

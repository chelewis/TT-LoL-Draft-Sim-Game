"""Public sharing: users publish players, coaches and teams; others search them and copy them into their account.

Only genuine, unedited Riot imports can be public players, and they use their Riot game name. A public team needs
a complete roster of shareable players. Something that stops qualifying (an edit, a deleted player) is taken off
public automatically. Copies are independent: the owner's later changes never reach them.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.core.errors import bad_request, not_found
from app.game.config import LANES
from app.integrations.riot.config import RANK_TIERS
from app.models import Coach, Player, PlayerPoolEntry, Team, TeamRosterSlot, User
from app.services import import_seal
from app.services import team_management_service as teams

MAX_PAGE = 50


# ------------------------------------------------------------ share checks
def player_share_issues(p: Player) -> list[str]:
    if p.owner_user_id is None:
        return ["Default players are already visible to everyone."]
    if not p.riot_puuid:
        return ["Only players imported from Riot can be made public."]
    status = import_seal.check(p)["status"]
    if status == "unverified":
        return ["This import can't be verified. Refresh it from Riot to make it public."]
    if status == "edited":
        return ["This import was edited. Only unedited Riot imports can be made public (a refresh from Riot restores it)."]
    return []


def coach_share_issues(c: Coach) -> list[str]:
    return ["Default coaches are already visible to everyone."] if c.owner_user_id is None else []


def team_share_issues(db: Session, t: Team) -> list[str]:
    if t.owner_user_id is None:
        return ["Default teams are already visible to everyone."]
    issues = teams.team_issues(t)
    if issues:
        return issues
    players = [db.get(Player, s.player_id) for s in t.slots]
    blocked = [p.name if p else "a deleted player" for p in players if p is None or player_share_issues(p)]
    if blocked:
        return ["Every player must be an unedited Riot import to share the team. Not shareable: " + ", ".join(blocked)]
    return []


# --------------------------------------------------------- publish / revalidate
def _publish(obj, public: bool) -> None:
    obj.is_public = public
    obj.published_at = utcnow() if public else None


def set_player_public(db: Session, user_id: int, player_id: int, public: bool) -> Player:
    p = teams.get_owned(db, Player, player_id, user_id)
    if public:
        issues = player_share_issues(p)
        if issues:
            raise bad_request(issues[0])
        p.name = (p.riot_game_name or p.name)[:40]   # public players go by their Riot name
        if not p.is_public:
            _publish(p, True)
    else:
        _publish(p, False)
        revalidate_teams(db, _teams_with_players(db, [p.id]))
    db.commit()
    return p


def set_coach_public(db: Session, user_id: int, coach_id: int, public: bool) -> Coach:
    c = teams.get_owned(db, Coach, coach_id, user_id)
    if public != c.is_public:
        _publish(c, public)
    db.commit()
    return c


def set_team_public(db: Session, user_id: int, team_id: int, public: bool) -> Team:
    t = teams.get_owned(db, Team, team_id, user_id)
    if public:
        issues = team_share_issues(db, t)
        if issues:
            raise bad_request(issues[0])
        if not t.is_public:
            _publish(t, True)
    else:
        _publish(t, False)
    db.commit()
    return t


def _teams_with_players(db: Session, player_ids: Iterable[int]) -> list[Team]:
    ids = list(player_ids)
    if not ids:
        return []
    return list(db.scalars(select(Team).where(Team.is_public.is_(True), Team.id.in_(
        select(TeamRosterSlot.team_id).where(TeamRosterSlot.player_id.in_(ids))))))


def revalidate_teams(db: Session, team_list: Iterable[Team]) -> None:
    """Unpublish public teams that no longer qualify. Does not commit."""
    db.flush()
    for t in team_list:
        db.refresh(t)   # the roster may have just changed
        if t.is_public and team_share_issues(db, t):
            _publish(t, False)


def revalidate_player(db: Session, p: Player) -> None:
    """After an edit: a public player that stopped qualifying is unpublished, and so are its public teams.
    Does not commit."""
    if p.is_public:
        if player_share_issues(p):
            _publish(p, False)
        else:
            p.name = (p.riot_game_name or p.name)[:40]
    revalidate_teams(db, _teams_with_players(db, [p.id]))


# ------------------------------------------------------------------ search
def _owners(db: Session, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(wanted)))}


def _page(items: list, offset: int, limit: int) -> dict:
    limit = max(1, min(MAX_PAGE, limit))
    offset = max(0, offset)
    return {"total": len(items), "offset": offset, "limit": limit, "items": items[offset:offset + limit]}


def _tier_index(tier: str | None) -> int | None:
    return RANK_TIERS.index(tier) if tier in RANK_TIERS else None


def _tier_range(rank_min: str | None, rank_max: str | None) -> list[str] | None:
    """The tiers between the two bounds (inclusive), or None when neither is set."""
    if not rank_min and not rank_max:
        return None
    lo = _tier_index(rank_min) or 0
    hi = _tier_index(rank_max)
    hi = len(RANK_TIERS) - 1 if hi is None else hi
    return list(RANK_TIERS[lo:hi + 1])


def _public(model, user_id: int):
    return select(model).where(model.is_public.is_(True), model.owner_user_id.is_not(None),
                               model.owner_user_id != user_id, model.season_id.is_(None))


STATS = ("aggr", "aware", "pos", "dmg", "cs")


def search_players(db: Session, user_id: int, *, q: str | None = None, role: str | None = None,
                   rank_min: str | None = None, rank_max: str | None = None, region: str | None = None,
                   stat_min: dict[str, int] | None = None, stat_max: dict[str, int] | None = None,
                   total_min: int | None = None, total_max: int | None = None,
                   champions: list[int] | None = None, tags: list[str] | None = None,
                   sort: str = "newest", offset: int = 0, limit: int = 20) -> dict:
    stmt = _public(Player, user_id)
    if q:
        stmt = stmt.where(func.lower(Player.name).contains(q.strip().lower()))
    if role:
        stmt = stmt.where(or_(Player.role == role, Player.secondary_role == role))
    tiers = _tier_range(rank_min, rank_max)
    if tiers is not None:
        stmt = stmt.where(Player.riot_rank_tier.in_(tiers))
    if region:
        stmt = stmt.where(func.upper(Player.riot_region) == region.upper())
    for stat, value in (stat_min or {}).items():
        stmt = stmt.where(getattr(Player, stat) >= value)
    for stat, value in (stat_max or {}).items():
        stmt = stmt.where(getattr(Player, stat) <= value)
    total = sum((getattr(Player, s) for s in STATS[1:]), Player.aggr)
    if total_min is not None:
        stmt = stmt.where(total >= total_min)
    if total_max is not None:
        stmt = stmt.where(total <= total_max)
    for cid in champions or []:
        stmt = stmt.where(exists().where(PlayerPoolEntry.player_id == Player.id, PlayerPoolEntry.champion_id == cid))
    players = [p for p in db.scalars(stmt) if not player_share_issues(p)]
    views = [teams.player_view(p) for p in players]
    if tags:
        wanted = set(tags)
        views = [v for v in views if wanted <= {t["key"] for t in v["tags"]}]
    published = {p.id: p.published_at for p in players}
    owners = _owners(db, (p.owner_user_id for p in players))
    owner_of = {p.id: p.owner_user_id for p in players}
    rank_of = {p.id: _tier_index(p.riot_rank_tier) or -1 for p in players}
    key = {
        "total": lambda v: (-v["stat_total"], v["name"].lower()),
        "rank": lambda v: (-rank_of[v["id"]], -v["stat_total"]),
        "name": lambda v: v["name"].lower(),
    }.get(sort, lambda v: -(published[v["id"]].timestamp() if published[v["id"]] else 0))
    views.sort(key=key)
    for v in views:
        v["owner"] = owners.get(owner_of[v["id"]])
        v["published_at"] = iso(published[v["id"]])
    return _page(views, offset, limit)


def search_coaches(db: Session, user_id: int, *, q: str | None = None, draft_min: int | None = None,
                   draft_max: int | None = None, synergy_min: int | None = None, synergy_max: int | None = None,
                   sort: str = "newest", offset: int = 0, limit: int = 20) -> dict:
    stmt = _public(Coach, user_id)
    if q:
        stmt = stmt.where(func.lower(Coach.name).contains(q.strip().lower()))
    for column, lo, hi in ((Coach.draft, draft_min, draft_max), (Coach.synergy, synergy_min, synergy_max)):
        if lo is not None:
            stmt = stmt.where(column >= lo)
        if hi is not None:
            stmt = stmt.where(column <= hi)
    coaches = list(db.scalars(stmt))
    key = {
        "total": lambda c: (-(c.draft + c.synergy), c.name.lower()),
        "name": lambda c: c.name.lower(),
    }.get(sort, lambda c: -(c.published_at.timestamp() if c.published_at else 0))
    coaches.sort(key=key)
    owners = _owners(db, (c.owner_user_id for c in coaches))
    views = [{**teams.coach_view(c), "owner": owners.get(c.owner_user_id), "published_at": iso(c.published_at)}
             for c in coaches]
    return _page(views, offset, limit)


def average_rank(view: dict) -> float | None:
    """The roster's average rank tier index (0 = Iron), None when no player is ranked."""
    tiers = [_tier_index(((p.get("riot") or {}).get("rank") or {}).get("tier"))
             for p in (view["roster"] or {}).values() if p]
    tiers = [t for t in tiers if t is not None]
    return sum(tiers) / len(tiers) if tiers else None


def search_teams(db: Session, user_id: int, *, q: str | None = None, style: str | None = None,
                 focus: str | None = None, total_min: int | None = None, total_max: int | None = None,
                 rank_min: str | None = None, rank_max: str | None = None, champion: int | None = None,
                 player: str | None = None, coach_draft_min: int | None = None,
                 coach_synergy_min: int | None = None, sort: str = "newest", offset: int = 0,
                 limit: int = 20) -> dict:
    stmt = _public(Team, user_id)
    if q:
        stmt = stmt.where(func.lower(Team.name).contains(q.strip().lower()))
    if style:
        stmt = stmt.where(or_(Team.style1 == style, Team.style2 == style))
    if focus:
        stmt = stmt.where(or_(Team.focus1 == focus, Team.focus2 == focus))
    found = [t for t in db.scalars(stmt) if not team_share_issues(db, t)]
    lo, hi = _tier_index(rank_min), _tier_index(rank_max)
    results = []
    for t in found:
        v = teams.team_view(db, t)
        roster = [p for lane in LANES if (p := v["roster"].get(lane))]
        total = sum(p["stat_total"] for p in roster)
        avg = average_rank(v)
        if total_min is not None and total < total_min or total_max is not None and total > total_max:
            continue
        if lo is not None and (avg is None or avg < lo) or hi is not None and (avg is None or avg > hi):
            continue
        if champion is not None and not any(champion in p["pool"] for p in roster):
            continue
        if player and not any(player.strip().lower() in p["name"].lower() for p in roster):
            continue
        coach = v["coach"] or {}
        if coach_draft_min is not None and coach.get("draft", 0) < coach_draft_min:
            continue
        if coach_synergy_min is not None and coach.get("synergy", 0) < coach_synergy_min:
            continue
        v["stat_total"], v["average_rank"] = total, avg
        v["published_at"], v["_published"], v["_owner"] = iso(t.published_at), t.published_at, t.owner_user_id
        results.append(v)
    key = {
        "total": lambda v: (-v["stat_total"], v["name"].lower()),
        "rank": lambda v: (-(v["average_rank"] if v["average_rank"] is not None else -1), -v["stat_total"]),
        "name": lambda v: v["name"].lower(),
    }.get(sort, lambda v: -(v["_published"].timestamp() if v["_published"] else 0))
    results.sort(key=key)
    owners = _owners(db, (v["_owner"] for v in results))
    for v in results:
        v["owner"] = owners.get(v.pop("_owner"))
        v.pop("_published")
    return _page(results, offset, limit)


# -------------------------------------------------------------------- copy
def _get_public(db: Session, model, obj_id: int, user_id: int):
    obj = db.get(model, obj_id)
    if obj is None or not obj.is_public or obj.owner_user_id is None or obj.season_id is not None:
        raise not_found()
    if obj.owner_user_id == user_id:
        raise bad_request("That's already yours.")
    return obj


def copy_player(db: Session, user_id: int, player_id: int) -> Player:
    source = _get_public(db, Player, player_id, user_id)
    teams.check_limit(db, Player, user_id, teams.CFG["max_players_per_user"], "players")
    copy = teams.copy_player(source, user_id)
    db.add(copy)
    db.commit()
    return copy


def copy_coach(db: Session, user_id: int, coach_id: int) -> Coach:
    source = _get_public(db, Coach, coach_id, user_id)
    teams.check_limit(db, Coach, user_id, teams.CFG["max_coaches_per_user"], "coaches")
    copy = Coach(owner_user_id=user_id, name=source.name, draft=source.draft, synergy=source.synergy)
    db.add(copy)
    db.commit()
    return copy


def copy_team(db: Session, user_id: int, team_id: int) -> Team:
    source = _get_public(db, Team, team_id, user_id)
    if team_share_issues(db, source):
        raise not_found()
    return teams.copy_team(db, user_id, source, name_suffix="")

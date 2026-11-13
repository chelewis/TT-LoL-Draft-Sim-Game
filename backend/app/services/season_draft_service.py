"""Player Draft seasons and free agency.

Player Draft: managers enter a team identity (name, logo, playstyles, coach) with an empty roster, the creator fills a
pool of players (copies of their own players, or generated ones), and once the season starts the managers snake-draft
their five players from it. Every pick must leave the pool able to fill every team's open lanes, so nobody is ever
stuck. An optional pick clock auto-picks the best available player; teams the CPU runs pick straight away. When the
last pick is in, the competition is drawn up as in Bring Your Own.

Free agency (both roster modes): every season player not on a roster is a free agent: the undrafted pool, a batch
generated when the competition starts, and players released by signings. A manager signs one into a lane, replacing
(and releasing) whoever was there, up to the season's signing limit.
"""
from __future__ import annotations

import random
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.game import player_generator
from app.game.config import LANES
from app.game.season_draft import PoolPlayer, auto_pick, lane_shortfall, pick_problem, snake_order
from app.models import (Champion, Coach, Player, Season, SeasonDraftPick, SeasonMatch, SeasonTeam,
                        SeasonTransaction, Team, TeamRosterSlot, User)
from app.schemas.season import SeasonTeamIn
from app.services import lobby_rules
from app.services import notification_service as notes
from app.services import season_match_service as matches
from app.services import season_service as ss
from app.services import team_management_service as teams
from app.services.analytics import track

Events = list[dict]
MAX_POOL = 240               # pool players a season can hold
SECONDARY_ROLE_CHANCE = 0.3  # generated pool players who can also play a second lane


# ------------------------------------------------------------------- pool
def _rostered(season: Season):
    return (select(TeamRosterSlot.player_id).join(Team, Team.id == TeamRosterSlot.team_id)
            .where(Team.season_id == season.id))


def pool_players(db: Session, season: Season) -> list[Player]:
    """The season's players on no roster: the draft pool before and during the draft, the free agents after it."""
    return list(db.scalars(select(Player).where(Player.season_id == season.id, Player.id.not_in(_rostered(season)))
                           .order_by(Player.id)))


def _lanes(p: Player) -> frozenset[str]:
    return frozenset(lane for lane in (p.role, p.secondary_role) if lane in LANES)


def _engine_pool(players: list[Player]) -> list[PoolPlayer]:
    return [PoolPlayer(p.id, _lanes(p), p.stat_total, p.role) for p in players]


def pool_view(db: Session, season: Season) -> dict:
    players = pool_players(db, season)
    return {"players": [{**teams.player_view(p), "lanes": sorted(_lanes(p), key=LANES.index),
                         "generated": p.owner_user_id is None} for p in players]}


def _require_pool_setup(season: Season, user: User) -> None:
    ss._require_creator(season, user)
    if season.roster_mode != "DRAFT":
        raise conflict("Only Player Draft seasons have a draft pool.")
    if season.status != "SETUP":
        raise conflict("The pool is fixed once the season starts.")


def _pool_room(db: Session, season: Season, adding: int) -> None:
    if len(pool_players(db, season)) + adding > MAX_POOL:
        raise conflict(f"A draft pool holds at most {MAX_POOL} players.")


def add_pool_players(db: Session, season: Season, user: User, player_ids: list[int]) -> int:
    """Copy some of your players (or default players) into the pool. Each must meet the season's player rules
    (max rank, player stat cap), and the same player can't be in the pool twice. Returns how many were added."""
    _require_pool_setup(season, user)
    _pool_room(db, season, len(set(player_ids)))
    rules = {**ss._rules(season), "max_team_total": None}
    seen = {lobby_rules.player_identity(teams.player_view(p)) for p in pool_players(db, season)}
    copies = []
    for pid in dict.fromkeys(player_ids):
        source = teams.get_visible(db, Player, pid, user.id)
        view = teams.player_view(source)
        identity = lobby_rules.player_identity(view)
        if identity in seen:
            raise conflict(f"{source.name} is already in the pool.")
        broken = lobby_rules.team_rule_issues({"roster": {"TOP": view}}, rules)
        if broken:
            raise bad_request(f"{source.name} breaks this season's rules: " + "; ".join(broken))
        seen.add(identity)
        copies.append(teams.copy_player(source, user.id, season.id))
    db.add_all(copies)
    db.commit()
    track("season_pool_added", season_id=season.id, count=len(copies))
    return len(copies)


def _champions(db: Session) -> list:
    return [c.to_engine() for c in db.scalars(select(Champion).where(Champion.enabled.is_(True)))]


def _taken_names(db: Session, season: Season) -> set[str]:
    return set(db.scalars(select(func.lower(Player.name)).where(Player.season_id == season.id)))


def _generate_players(db: Session, season: Season, per_role: int, strength: str, rng: random.Random,
                      secondary: bool) -> int:
    """Generated players, `per_role` for each lane, sized like a CPU team of `strength` under the season's rules."""
    champions, names, rules = _champions(db), _taken_names(db, season), ss._rules(season)
    made = 0
    for lane in LANES:
        for _ in range(per_role):
            total = rng.choice(player_generator.player_totals(rules, strength, rng))
            data = player_generator.generate_player(lane, total, champions, rng, names)
            names.add(data["name"].lower())
            player = ss._new_player(season, data)
            if secondary and rng.random() < SECONDARY_ROLE_CHANCE:
                player.secondary_role = rng.choice([other for other in LANES if other != lane])
            db.add(player)
            made += 1
    db.flush()
    return made


def generate_pool(db: Session, season: Season, user: User, per_role: int, strength: str) -> int:
    _require_pool_setup(season, user)
    _pool_room(db, season, per_role * len(LANES))
    made = _generate_players(db, season, per_role, strength, random.Random(secrets.randbits(64)), secondary=True)
    db.commit()
    track("season_pool_generated", season_id=season.id, count=made, strength=strength)
    return made


def remove_pool_player(db: Session, season: Season, user: User, player_id: int) -> None:
    _require_pool_setup(season, user)
    player = db.get(Player, player_id)
    if player is None or player.season_id != season.id or player.id not in {p.id for p in pool_players(db, season)}:
        raise not_found("That player isn't in the pool.")
    db.delete(player)
    db.commit()


def clear_pool(db: Session, season: Season, user: User) -> None:
    _require_pool_setup(season, user)
    for p in pool_players(db, season):
        db.delete(p)
    db.commit()


def _draft_needs(count: int) -> dict[str, int]:
    return {lane: count for lane in LANES}


def pool_summary(db: Session, season: Season) -> dict:
    """Setup: pool size per lane (a player who plays two lanes counts in both), and what's missing for the
    managers entered so far (every manager needs one player per lane)."""
    players = pool_players(db, season)
    by_lane = {lane: sum(lane in _lanes(p) for p in players) for lane in LANES}
    managers = sum(st.manager_user_id is not None for st in ss.season_teams(db, season))
    return {"count": len(players), "by_lane": by_lane,
            "shortfall": lane_shortfall(_draft_needs(max(1, managers)), _engine_pool(players))}


def check_pool(db: Session, season: Season) -> None:
    managers = sum(st.manager_user_id is not None for st in ss.season_teams(db, season))
    missing = lane_shortfall(_draft_needs(managers), _engine_pool(pool_players(db, season)))
    if missing:
        short = ", ".join(f"{n} {lane}" for lane, n in missing.items())
        raise conflict(f"The draft pool can't fill every manager's roster yet: it's short of {short}. "
                       "Add or generate more players.")


# ----------------------------------------------------------- draft teams
def create_draft_team(db: Session, season: Season, user: User, body: SeasonTeamIn) -> Team:
    """A Player Draft team: the manager's chosen identity and coach, with an empty roster to draft into."""
    name = (body.name or "").strip()
    if not name:
        raise bad_request("Give your team a name.")
    rng = random.Random(secrets.randbits(64))
    style1, style2 = body.style1, body.style2
    for style in (style1, style2):
        if style is not None and style not in teams.STYLES:
            raise bad_request(f"Playstyle must be one of {', '.join(teams.STYLES)}.")
    if style1 and style1 == style2:
        raise bad_request("Choose two different playstyles.")
    if not style1 or not style2:                  # any style not chosen is picked at random
        rest = [s for s in teams.STYLES if s not in (style1, style2)]
        rng.shuffle(rest)
        style1, style2 = style1 or rest.pop(), style2 or rest.pop()
    if body.coach_id is not None:
        source = teams.get_visible(db, Coach, body.coach_id, user.id)
        coach = Coach(owner_user_id=user.id, season_id=season.id, name=source.name, draft=source.draft,
                      synergy=source.synergy)
    else:
        c = player_generator.generate_coach("EVEN", rng, _taken_names(db, season))
        coach = Coach(owner_user_id=user.id, season_id=season.id, name=c["name"], draft=c["draft"], synergy=c["synergy"])
    db.add(coach)
    db.flush()
    logo = body.logo.strip() or "".join(w[0] for w in name.split() if w[:1].isalnum()).upper()[:4]
    team = Team(owner_user_id=user.id, season_id=season.id, name=name, logo=logo, region="", fanbase="small",
                style1=style1, style2=style2, coach_id=coach.id)
    db.add(team)
    db.flush()
    return team


# ------------------------------------------------------------------ draft
def draft_teams(db: Session, season: Season) -> list[SeasonTeam]:
    return list(db.scalars(select(SeasonTeam).where(SeasonTeam.season_id == season.id,
                                                    SeasonTeam.draft_position.is_not(None))
                           .order_by(SeasonTeam.draft_position)))


def _picks(db: Session, season: Season) -> list[SeasonDraftPick]:
    return list(db.scalars(select(SeasonDraftPick).where(SeasonDraftPick.season_id == season.id)
                           .order_by(SeasonDraftPick.pick_number)))


def _pick_count(db: Session, season: Season) -> int:
    return db.scalar(select(func.count()).select_from(SeasonDraftPick)
                     .where(SeasonDraftPick.season_id == season.id)) or 0


def _open_lanes(db: Session, st: SeasonTeam) -> list[str]:
    filled = set(db.scalars(select(TeamRosterSlot.lane).where(TeamRosterSlot.team_id == st.team_id)))
    return [lane for lane in LANES if lane not in filled]


def on_the_clock(db: Session, season: Season) -> tuple[int, SeasonTeam] | None:
    """(pick number, team) for the next pick; None once every pick is in."""
    order = draft_teams(db, season)
    number = _pick_count(db, season) + 1
    if not order or number > len(order) * len(LANES):
        return None
    st_id = snake_order([st.id for st in order], number)
    return number, next(st for st in order if st.id == st_id)


def start_draft(db: Session, season: Season, rng: random.Random) -> None:
    """The managers' teams draft in a random snake order. The caller commits."""
    managed = [st for st in ss.season_teams(db, season) if st.manager_user_id is not None]
    rng.shuffle(managed)
    for i, st in enumerate(managed):
        st.draft_position = i + 1
    season.status = "PLAYER_DRAFT"
    db.flush()
    _advance_draft(db, season)
    track("season_draft_started", season_id=season.id, teams=len(managed))


def _set_clock(season: Season, st: SeasonTeam) -> None:
    seconds = ss._options(season).get("draft_pick_seconds") or 0
    season.pick_deadline_at = utcnow() + timedelta(seconds=seconds) if seconds and st.manager_user_id else None


def _record_pick(db: Session, season: Season, number: int, st: SeasonTeam, player_id: int, lane: str,
                 auto: bool) -> None:
    db.add(TeamRosterSlot(team_id=st.team_id, lane=lane, player_id=player_id))
    db.add(SeasonDraftPick(season_id=season.id, pick_number=number, season_team_id=st.id, player_id=player_id,
                           lane=lane, auto=auto))
    db.flush()
    team = db.get(Team, st.team_id)
    db.refresh(team)                         # its roster changed underneath the loaded relationship


def _state(db: Session, season: Season) -> tuple[list[Player], list[SeasonTeam], list[list[str]]]:
    order = draft_teams(db, season)
    return pool_players(db, season), order, [_open_lanes(db, st) for st in order]


def _auto_pick_for(db: Session, season: Season, number: int, st: SeasonTeam) -> None:
    pool, order, open_lanes = _state(db, season)
    index = next(i for i, t in enumerate(order) if t.id == st.id)
    choice = auto_pick(_engine_pool(pool), open_lanes, index)
    if choice is None:
        # can't happen while the pool stays fillable, but never stall the draft: anyone who plays an open lane,
        # else anyone at all
        lanes = open_lanes[index]
        fits = [(p.id, lane) for p in sorted(pool, key=lambda p: -p.stat_total) for lane in lanes if lane in _lanes(p)]
        choice = fits[0] if fits else (max(pool, key=lambda p: p.stat_total).id, lanes[0]) if pool else None
    if choice is None:
        raise conflict("The draft pool is empty.")
    _record_pick(db, season, number, st, choice[0], choice[1], auto=True)


def _advance_draft(db: Session, season: Season) -> None:
    """After a pick: the CPU picks for any team it runs that's now on the clock; then either the clock starts for
    the next manager or, with every pick in, the competition begins."""
    while True:
        nxt = on_the_clock(db, season)
        if nxt is None:
            season.pick_deadline_at = None
            ss._begin_competition(db, season, random.Random(secrets.randbits(64)))
            track("season_draft_completed", season_id=season.id)
            return
        number, st = nxt
        if st.manager_user_id is not None:
            _set_clock(season, st)
            _tell_on_the_clock(db, season, number, st)
            return
        _auto_pick_for(db, season, number, st)


def _tell_on_the_clock(db: Session, season: Season, number: int, st: SeasonTeam) -> None:
    """Tell a manager it's their pick, unless they made the pick just before too (the turn of the snake)."""
    order = [t.id for t in draft_teams(db, season)]
    if number > 1 and snake_order(order, number - 1) == st.id:
        return
    seconds = ss._options(season).get("draft_pick_seconds") or 0
    clock = f" You have {ss._in_words(timedelta(seconds=seconds))}." if seconds else ""
    notes.notify(db, st.manager_user_id, "ON_THE_CLOCK", f"{season.name}: you're on the clock",
                 f"Pick {number} of the player draft is yours.{clock}", ss.season_link(season), season.id,
                 key=f"season:{season.id}:pick:{number}")


def _require_drafting(season: Season) -> None:
    if season.status != "PLAYER_DRAFT":
        raise conflict("The player draft isn't in progress.")


def make_pick(db: Session, season: Season, user: User, player_id: int, lane: str) -> Events:
    _require_drafting(season)
    with matches.simulating(season.id):
        db.refresh(season)
        _require_drafting(season)
        number, st = on_the_clock(db, season)
        if st.manager_user_id != user.id:
            raise conflict("It's not your pick.")
        pool, order, open_lanes = _state(db, season)
        index = next(i for i, t in enumerate(order) if t.id == st.id)
        problem = pick_problem(_engine_pool(pool), open_lanes, index, player_id, lane)
        if problem:
            raise conflict(problem)
        _record_pick(db, season, number, st, player_id, lane, auto=False)
        _advance_draft(db, season)
        db.commit()
    return [matches.season_event(season.id)]


def auto_pick_now(db: Session, season: Season, user: User) -> Events:
    """Pick the best available player for the team on the clock: its manager asking, or the creator moving the
    draft on for someone who isn't there."""
    _require_drafting(season)
    with matches.simulating(season.id):
        db.refresh(season)
        _require_drafting(season)
        number, st = on_the_clock(db, season)
        if user.id not in (st.manager_user_id, season.created_by):
            raise forbidden("Only the manager on the clock or the season's creator can do that.")
        _auto_pick_for(db, season, number, st)
        _advance_draft(db, season)
        db.commit()
    return [matches.season_event(season.id)]


def after_manager_left(db: Session, season: Season) -> None:
    """A manager left during the draft: if their team is on the clock the CPU picks for it now. The caller commits."""
    if season.status == "PLAYER_DRAFT":
        _advance_draft(db, season)


def process_draft_clocks(db: Session, now=None) -> Events:
    """Auto-pick for every manager whose pick clock has run out. Run by the background loop."""
    now = now or utcnow()
    due = db.scalars(select(Season).where(Season.status == "PLAYER_DRAFT", Season.pick_deadline_at.is_not(None),
                                          Season.pick_deadline_at <= now)).all()
    events: Events = []
    for season in due:
        try:
            with matches.simulating(season.id):
                db.refresh(season)
                if season.status != "PLAYER_DRAFT" or season.pick_deadline_at is None \
                        or season.pick_deadline_at > now:
                    continue
                number, st = on_the_clock(db, season)
                _auto_pick_for(db, season, number, st)
                _advance_draft(db, season)
                db.commit()
                events.append(matches.season_event(season.id))
        except HTTPException:             # busy (another request is picking): try again next time
            db.rollback()
    return events


def draft_view(db: Session, season: Season, refs: dict[int, dict], viewer: User) -> dict | None:
    order = draft_teams(db, season)
    if not order:
        return None
    names = dict(db.execute(select(Player.id, Player.name).where(Player.season_id == season.id)).all())
    clock = on_the_clock(db, season) if season.status == "PLAYER_DRAFT" else None
    mine = next((st for st in order if st.manager_user_id == viewer.id), None)
    return {
        "order": [refs.get(st.id) for st in order],
        "picks": [{"pick_number": p.pick_number, "team": refs.get(p.season_team_id), "player_id": p.player_id,
                   "player_name": names.get(p.player_id, "?"), "lane": p.lane, "auto": p.auto}
                  for p in _picks(db, season)],
        "total_picks": len(order) * len(LANES),
        "current_pick": clock[0] if clock else None,
        "on_the_clock": refs.get(clock[1].id) if clock else None,
        "pick_deadline_at": iso(season.pick_deadline_at),
        "my_turn": bool(clock and mine and clock[1].id == mine.id),
        "my_open_lanes": _open_lanes(db, mine) if mine else [],
        "complete": clock is None,
    }


# ---------------------------------------------------------- free agency
def add_free_agents(db: Session, season: Season, rng: random.Random) -> None:
    """The batch of generated free agents a season starts with (when free agency is on). The caller commits."""
    options = ss._options(season)
    per_role = options.get("free_agents_per_role") or 0
    if (options.get("max_signings") or 0) and per_role:
        _generate_players(db, season, per_role, "EVEN", rng, secondary=False)


def signings_used(db: Session, st: SeasonTeam) -> int:
    return db.scalar(select(func.count()).select_from(SeasonTransaction)
                     .where(SeasonTransaction.season_team_id == st.id, SeasonTransaction.type == "SIGN")) or 0


def _rule_issues(db: Session, season: Season, team: Team) -> tuple[list[str], int]:
    """The team's broken rules, apart from the team stat cap (returned as the total, compared separately so a
    signing that brings an over-the-cap team down is allowed). Generated players have no rank, like CPU players, so
    a max rank only applies to the rest."""
    rules = ss._rules(season)
    view = teams.team_view(db, team)
    roster = {lane: p for lane, p in view["roster"].items() if p}
    issues = lobby_rules.team_rule_issues(view, {**rules, "max_rank": None, "max_team_total": None})
    ranked = {lane: p for lane, p in roster.items() if not (p["is_default"] and not p["riot"])}
    issues += lobby_rules.team_rule_issues({"roster": ranked}, {**rules, "duplicate_clause": False,
                                                                "max_player_total": None, "max_team_total": None})
    return issues, sum(p["stat_total"] for p in roster.values())


def free_agency_view(db: Session, season: Season, viewer: User) -> dict:
    limit = ss._options(season).get("max_signings") or 0
    mine = next((st for st in ss.season_teams(db, season) if st.manager_user_id == viewer.id), None)
    return {"enabled": bool(limit), "max_signings": limit, "open": season.status in matches.PLAYING,
            "signings_left": max(0, limit - signings_used(db, mine)) if mine and limit else None}


def sign_free_agent(db: Session, season: Season, user: User, player_id: int, lane: str) -> Events:
    """Sign a free agent into one of your team's lanes; the player who was there becomes a free agent."""
    limit = ss._options(season).get("max_signings") or 0
    if not limit:
        raise conflict("Free agency is off in this season.")
    if season.status not in matches.PLAYING:
        raise conflict("Free agency opens once the season is under way.")
    st = next((st for st in ss.season_teams(db, season) if st.manager_user_id == user.id), None)
    if st is None:
        raise forbidden("You don't manage a team in this season.")
    with matches.simulating(season.id):
        db.refresh(season)
        if signings_used(db, st) >= limit:
            raise conflict(f"Your team has used all {limit} of its signings.")
        player = db.get(Player, player_id)
        if player is None or player.season_id != season.id or player.id not in {p.id for p in pool_players(db, season)}:
            raise not_found("That player isn't a free agent.")
        if lane not in _lanes(player):
            raise bad_request(f"{player.name} can't play {lane}.")
        busy = db.scalar(select(SeasonMatch.id).where(
            SeasonMatch.season_id == season.id, SeasonMatch.status == "LIVE",
            (SeasonMatch.home_team_id == st.id) | (SeasonMatch.away_team_id == st.id)).limit(1))
        if busy is not None:
            raise conflict("Your team is in the middle of a match. Sign players once it's finished.")
        team = db.get(Team, st.team_id)
        before, before_total = _rule_issues(db, season, team)
        slot = next((s for s in team.slots if s.lane == lane), None)
        released = db.get(Player, slot.player_id) if slot else None
        if slot is None:
            team.slots.append(TeamRosterSlot(lane=lane, player_id=player.id))
        else:
            slot.player_id = player.id
        db.flush()
        after, after_total = _rule_issues(db, season, team)
        cap = ss._rules(season).get("max_team_total")
        broken = [i for i in after if i not in before]
        if cap is not None and after_total > int(cap) and after_total > before_total:
            broken.append(f"Team stats total {after_total} (limit {cap})")
        if broken:
            db.rollback()
            raise bad_request(f"Signing {player.name} would break this season's rules: " + "; ".join(broken))
        stage = matches.current_stage(season)
        if released is not None:
            db.add(SeasonTransaction(season_id=season.id, season_team_id=st.id, type="RELEASE", player_id=released.id,
                                     player_name=released.name, lane=lane, stage=stage, round=season.current_round))
        db.add(SeasonTransaction(season_id=season.id, season_team_id=st.id, type="SIGN", player_id=player.id,
                                 player_name=player.name, lane=lane, stage=stage, round=season.current_round))
        db.commit()
    track("season_signing", season_id=season.id, user_id=user.id, lane=lane)
    return [matches.season_event(season.id)]


def transactions_view(db: Session, season: Season, refs: dict[int, dict], limit: int = 30) -> list[dict]:
    rows = db.scalars(select(SeasonTransaction).where(SeasonTransaction.season_id == season.id)
                      .order_by(SeasonTransaction.id.desc()).limit(limit))
    return [{"id": t.id, "team": refs.get(t.season_team_id), "type": t.type, "player_id": t.player_id,
             "player_name": t.player_name, "lane": t.lane, "stage": t.stage, "round": t.round,
             "created_at": iso(t.created_at)} for t in rows]

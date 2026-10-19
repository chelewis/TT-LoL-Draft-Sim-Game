"""Lobby, game state machine, draft, lineup and simulation orchestration.

The backend is authoritative: every transition and every draft / lineup action is validated here.
Service functions mutate the database and return the list of notification events the caller should
broadcast over WebSockets (REST stays authoritative; events are only notifications).
"""
from __future__ import annotations

import logging
import random
import secrets
import string
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.game.comfort import comfort_modifier, comfort_tier
from app.game.config import DRAFT_CONFIG, GAME_CONFIG, LANES, SIMULATION_CONFIG, simulation_config
from app.game.draft_engine import DraftError, DraftState, new_draft, rebuild_draft
from app.game.models import CoachSpec, PlayerSpec, TeamSetup
from app.game.simulation_engine import simulate_match
from app.game.state import damage_balance_penalty, damage_profile
from app.game.win_rates import ally_delta
from app.models import (ChatMessage, Champion, DraftActionRow, Game, GameTeamSnapshot, Lobby, MatchEventRow, MatchResultRow,
                        Series, Team, TeamLineup, User)
from app.services import matchup_service, simulation_settings_service
from app.services import team_management_service as teams
from app.services.analytics import track

log = logging.getLogger(__name__)

CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1L")
PRE_DRAFT = ("WAITING_FOR_PLAYERS", "TEAM_SELECTION", "READY_CHECK")
ACTIVE = PRE_DRAFT + ("DRAFTING", "LANE_ASSIGNMENT", "READY_TO_SIMULATE", "SIMULATING")

# explicit state machine: allowed transitions (spec section 5.2)
TRANSITIONS = {
    "WAITING_FOR_PLAYERS": {"TEAM_SELECTION", "CANCELLED"},
    "TEAM_SELECTION": {"READY_CHECK", "WAITING_FOR_PLAYERS", "CANCELLED"},
    "READY_CHECK": {"TEAM_SELECTION", "DRAFTING", "CANCELLED", "WAITING_FOR_PLAYERS"},
    "DRAFTING": {"LANE_ASSIGNMENT", "CANCELLED"},
    "LANE_ASSIGNMENT": {"READY_TO_SIMULATE", "CANCELLED"},
    "READY_TO_SIMULATE": {"SIMULATING", "CANCELLED"},
    "SIMULATING": {"COMPLETED", "CANCELLED"},
    "COMPLETED": {"READY_TO_SIMULATE"},   # re-run: same teams, draft and lineups, new seed
    "CANCELLED": set(),
}

Events = list[dict]


def _transition(game: Game, new_status: str) -> None:
    if new_status not in TRANSITIONS[game.status]:
        raise conflict(f"Invalid state change {game.status} -> {new_status}.")
    game.status = new_status


def _event(game: Game, type_: str, **fields) -> dict:
    return {"type": type_, "game_id": game.id, **fields}


# ----------------------------------------------------------------- lookup
def side_of(game: Game, user_id: int) -> str | None:
    if game.blue_player_id == user_id:
        return "BLUE"
    if game.red_player_id == user_id:
        return "RED"
    return None


def acting_side(game: Game, user: User, requested: str | None = None) -> str:
    """Which side a request is for. Multiplayer: the caller's own side. Single player: the caller holds both
    seats, so the request must say which side it is for."""
    if not game.is_solo:
        return side_of(game, user.id)
    if requested not in ("BLUE", "RED"):
        raise bad_request("Say which side this is for (BLUE or RED).")
    return requested


def get_game(db: Session, game_id: int, user_id: int) -> Game:
    game = db.get(Game, game_id)
    if game is None or side_of(game, user_id) is None:
        raise not_found("Game not found.")
    return game


def get_lobby(db: Session, lobby_id: int) -> Lobby:
    lobby = db.get(Lobby, lobby_id)
    if lobby is None:
        raise not_found("Lobby not found.")
    return lobby


def game_for_lobby(db: Session, lobby_id: int, user_id: int) -> Game:
    game = db.scalar(select(Game).where(Game.lobby_id == lobby_id))
    if game is None or side_of(game, user_id) is None:
        raise not_found("Lobby not found.")
    return game


def user_games(db: Session, user_id: int, active_only: bool = False) -> list[Game]:
    stmt = select(Game).where((Game.blue_player_id == user_id) | (Game.red_player_id == user_id))
    if active_only:
        stmt = stmt.where(Game.status.in_(ACTIVE))
    return list(db.scalars(stmt.order_by(Game.created_at.desc())))


def expire_if_needed(db: Session, game: Game) -> Events:
    """Lobbies that never started the draft are cancelled once they pass their expiry."""
    if game.status in PRE_DRAFT:
        lobby = db.get(Lobby, game.lobby_id)
        if lobby.expires_at <= utcnow():
            game.status = "CANCELLED"
            db.commit()
            track("lobby_expired", game_id=game.id)
            return [_event(game, "GAME_CANCELLED", reason="LOBBY_EXPIRED")]
    return []


# ------------------------------------------------------------------ lobby
def _new_code(db: Session) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if db.scalar(select(Lobby).where(Lobby.code == code)) is None:
            return code
    raise RuntimeError("Could not generate a unique lobby code")


DEFAULT_SETTINGS = {"hide_player_data": False, "bans_enabled": True, "timers_enabled": True,
                    "pick_seconds": DRAFT_CONFIG["timer_seconds"], "ban_seconds": DRAFT_CONFIG["timer_seconds"],
                    "series_format": "BO1", "fearless": False}
SERIES_WINS = {"BO3": 2, "BO5": 3}      # wins needed to take the series


def create_lobby(db: Session, user: User, settings: dict | None = None, mode: str = "MULTI") -> tuple[Lobby, Game]:
    """Create a lobby and its game. `settings` are the creator's lobby options (see DEFAULT_SETTINGS).

    mode "SOLO" makes a single player game: the creator holds both seats, so nobody needs to join, and
    hiding player data from "the opponent" makes no sense."""
    opts = {**DEFAULT_SETTINGS, **(settings or {})}
    solo = mode == "SOLO"
    if solo:
        opts["hide_player_data"] = False
    if opts["series_format"] not in SERIES_WINS:
        opts["series_format"], opts["fearless"] = "BO1", False     # fearless only means something across games
    now = utcnow()
    lobby = Lobby(code=_new_code(db), created_by=user.id, settings=opts,
                  created_at=now, expires_at=now + timedelta(minutes=GAME_CONFIG["lobby_expiration_minutes"]))
    db.add(lobby)
    db.flush()
    game = Game(lobby_id=lobby.id, status="TEAM_SELECTION" if solo else "WAITING_FOR_PLAYERS",
                blue_player_id=user.id, red_player_id=user.id if solo else None, is_solo=solo,
                hide_player_data=bool(opts["hide_player_data"]), bans_enabled=bool(opts["bans_enabled"]),
                timers_enabled=bool(opts["timers_enabled"]), pick_seconds=int(opts["pick_seconds"]),
                ban_seconds=int(opts["ban_seconds"]))
    if opts["series_format"] in SERIES_WINS:
        series = Series(format=opts["series_format"], wins_needed=SERIES_WINS[opts["series_format"]],
                        fearless=bool(opts["fearless"]), created_by=user.id)
        db.add(series)
        db.flush()
        game.series_id, game.game_number = series.id, 1
    db.add(game)
    db.commit()
    track("lobby_created", lobby_id=lobby.id, game_id=game.id, user_id=user.id, mode=mode,
          series_format=opts["series_format"], fearless=bool(opts["fearless"]))
    return lobby, game


def join_lobby(db: Session, user: User, code: str) -> tuple[Lobby, Game, Events]:
    lobby = db.scalar(select(Lobby).where(Lobby.code == code.strip().upper()))
    if lobby is None:
        raise not_found("No lobby with that code.")
    game = db.scalar(select(Game).where(Game.lobby_id == lobby.id))
    events = expire_if_needed(db, game)
    if game.status == "CANCELLED":
        raise conflict("That lobby has expired or was cancelled.")
    if side_of(game, user.id):
        return lobby, game, []  # already in: joining again is a no-op (reconnect)
    if game.is_solo:
        raise conflict("That is a single player game; it cannot be joined.")
    if game.status != "WAITING_FOR_PLAYERS" or (game.blue_player_id is not None and game.red_player_id is not None):
        raise conflict("That lobby is full.")
    # the joiner takes whichever side the owner has left free
    joined = "BLUE" if game.blue_player_id is None else "RED"
    if joined == "BLUE":
        game.blue_player_id = user.id
    else:
        game.red_player_id = user.id
    _transition(game, "TEAM_SELECTION")
    db.commit()
    track("lobby_joined", lobby_id=lobby.id, game_id=game.id, user_id=user.id)
    return lobby, game, [_event(game, "PLAYER_JOINED", team=joined)]


def leave_lobby(db: Session, game: Game, user: User) -> Events:
    side = side_of(game, user.id)
    if game.status in ("COMPLETED", "CANCELLED"):
        return []
    owner_id = db.get(Lobby, game.lobby_id).created_by
    if user.id != owner_id and game.status in PRE_DRAFT:
        # the joiner leaves before the draft: their side opens up again
        if side == "RED":
            game.red_player_id, game.red_team_id = None, None
        else:
            game.blue_player_id, game.blue_team_id = None, None
        game.red_ready = game.blue_ready = False
        game.status = "WAITING_FOR_PLAYERS"
        db.commit()
        return [_event(game, "PLAYER_LEFT", team=side)]
    game.status = "CANCELLED"
    db.commit()
    track("game_cancelled", game_id=game.id, user_id=user.id)
    return [_event(game, "GAME_CANCELLED", reason="PLAYER_LEFT", team=side)]


def set_side(db: Session, game: Game, user: User, side: str) -> Events:
    """Lobby owner chooses Blue or Red. If the other player is already in, the two swap sides
    (each keeps their own team); if the lobby is empty, the owner simply takes the chosen side."""
    if side not in ("BLUE", "RED"):
        raise bad_request("Side must be BLUE or RED.")
    if game.is_solo:
        raise conflict("Sides cannot be changed in a single player game.")
    if db.get(Lobby, game.lobby_id).created_by != user.id:
        raise forbidden("Only the lobby owner can change sides.")
    if game.status not in PRE_DRAFT:
        raise conflict("Sides can no longer be changed.")
    if side_of(game, user.id) == side:
        return []
    game.blue_player_id, game.red_player_id = game.red_player_id, game.blue_player_id
    game.blue_team_id, game.red_team_id = game.red_team_id, game.blue_team_id
    game.blue_ready = game.red_ready = False
    db.commit()
    track("sides_changed", game_id=game.id, user_id=user.id, side=side)
    return [_event(game, "SIDES_SWAPPED", owner_team=side)]


# --------------------------------------------------------- team selection
def select_team(db: Session, game: Game, user: User, team_id: int, requested_side: str | None = None) -> Events:
    side = acting_side(game, user, requested_side)
    if game.status not in ("WAITING_FOR_PLAYERS", "TEAM_SELECTION", "READY_CHECK"):
        raise conflict("Teams can no longer be changed.")
    team = teams.get_visible(db, Team, team_id, user.id)
    issues = teams.team_issues(team)
    if issues:
        raise bad_request("That team cannot be used yet: " + "; ".join(issues))
    if side == "BLUE":
        game.blue_team_id, game.blue_ready = team.id, False
    else:
        game.red_team_id, game.red_ready = team.id, False
    if game.status != "WAITING_FOR_PLAYERS":
        target = "READY_CHECK" if game.blue_team_id and game.red_team_id else "TEAM_SELECTION"
        if target != game.status:
            _transition(game, target)
    db.commit()
    return [_event(game, "TEAM_SELECTED", team=side)]


def set_ready(db: Session, game: Game, user: User, ready: bool = True) -> Events:
    side = side_of(game, user.id)
    if game.status != "READY_CHECK":
        raise conflict("Both players must choose a team before readying up." if not game.is_solo
                       else "Choose a team for both sides before starting.")
    if game.is_solo:       # one person, two seats: starting means both sides are ready
        game.blue_ready = game.red_ready = ready
        events = [_event(game, "PLAYER_READY", team="BLUE", ready=ready), _event(game, "PLAYER_READY", team="RED", ready=ready)]
        if ready:
            events += _start_draft(db, game)
        db.commit()
        return events
    if side == "BLUE":
        game.blue_ready = ready
    else:
        game.red_ready = ready
    events = [_event(game, "PLAYER_READY", team=side, ready=ready)]
    if game.blue_ready and game.red_ready:
        events += _start_draft(db, game)
    db.commit()
    return events


# --------------------------------------------------------------- snapshots
def build_snapshot(db: Session, team: Team) -> dict:
    view = teams.team_view(db, team)
    return {
        "team_id": team.id, "owner_user_id": team.owner_user_id, "name": view["name"], "logo": view["logo"],
        "region": view["region"], "fanbase": view["fanbase"], "style1": view["style1"], "style2": view["style2"],
        "focus1": view["focus1"], "focus2": view["focus2"], "coach": view["coach"], "roster": view["roster"],
        "over_budget": view["over_budget"], "over_budget_players": view["over_budget_players"],
    }


def snapshot_of(db: Session, game: Game, side: str) -> dict | None:
    row = db.scalar(select(GameTeamSnapshot).where(GameTeamSnapshot.game_id == game.id,
                                                   GameTeamSnapshot.team == side))
    return row.snapshot if row else None


def _player_spec(p: dict) -> PlayerSpec:
    return PlayerSpec(p["id"], p["name"], p["role"], p["age"], p["aggr"], p["aware"], p["pos"],
                      p["dmg"], p["cs"], tuple(p["pool"]))


def _lane_players(snapshot: dict, players: dict[str, int] | None) -> dict[str, dict]:
    """lane -> snapshot player for the match: the roster, with any position swaps from the lineup applied."""
    by_id = {p["id"]: p for p in snapshot["roster"].values() if p}
    return {lane: by_id.get((players or {}).get(lane), p) for lane, p in snapshot["roster"].items()}


def _snapshot_to_setup(snapshot: dict, lineup: dict[str, int], players: dict[str, int] | None = None) -> TeamSetup:
    roster = {lane: _player_spec(p) for lane, p in _lane_players(snapshot, players).items()}
    c = snapshot["coach"]
    styles = tuple(s for s in (snapshot["style1"], snapshot["style2"]) if s)
    focus = tuple(f for f in (snapshot["focus1"], snapshot["focus2"]) if f)
    return TeamSetup(snapshot["team_id"], snapshot["name"], styles, focus,
                     CoachSpec(c["id"], c["name"], c["draft"], c["synergy"]), roster, lineup)


# ------------------------------------------------------------------ draft
def _enabled_champion_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Champion.id).where(Champion.enabled.is_(True))))


def _start_draft(db: Session, game: Game, snapshots: dict[str, dict] | None = None) -> Events:
    """Freeze both teams and open the draft. Later games of a series pass the previous game's
    `snapshots` (side -> snapshot) so the rosters stay the same for the whole series."""
    for side, team_id in (("BLUE", game.blue_team_id), ("RED", game.red_team_id)):
        if snapshots is not None:
            db.add(GameTeamSnapshot(game_id=game.id, team=side, snapshot=snapshots[side]))
            continue
        team = db.get(Team, team_id)
        if team is None or teams.team_issues(team):
            raise conflict(f"The {side.lower()} team is no longer valid.")
        db.add(GameTeamSnapshot(game_id=game.id, team=side, snapshot=build_snapshot(db, team)))
    _transition(game, "DRAFTING")
    now = utcnow()
    game.started_at = now
    game.current_action = 0
    _begin_action(game, now)
    track("draft_started", game_id=game.id)
    return [_event(game, "DRAFT_STARTED"), _action_started_event(game)]


def draft_actions(game: Game) -> list[str]:
    """The game's draft sequence: the configured order, without bans if the lobby disabled them."""
    actions = DRAFT_CONFIG["actions"]
    return actions if game.bans_enabled else [a for a in actions if not a.endswith("_BAN")]


def _begin_action(game: Game, started_at) -> None:
    """Start the timer for the game's current action (no expiry when timers are disabled)."""
    game.action_started_at = started_at
    game.hovered_champion_id = None
    if not game.timers_enabled:
        game.action_expires_at = None
        return
    seconds = game.ban_seconds if draft_actions(game)[game.current_action].endswith("_BAN") else game.pick_seconds
    game.action_expires_at = started_at + timedelta(seconds=seconds)


def _action_started_event(game: Game) -> dict:
    action = draft_actions(game)[game.current_action]
    return _event(game, "DRAFT_ACTION_STARTED", draft_action=game.current_action, action=action,
                  started_at=iso(game.action_started_at), expires_at=iso(game.action_expires_at))


def load_draft(db: Session, game: Game) -> DraftState:
    rows = db.scalars(select(DraftActionRow).where(DraftActionRow.game_id == game.id)
                      .order_by(DraftActionRow.action_number)).all()
    return rebuild_draft(draft_actions(game), _enabled_champion_ids(db),
                         [(r.team, r.action_type, r.champion_id, r.auto) for r in rows],
                         locked=fearless_locked_ids(db, game))


def _record_action(db: Session, game: Game, draft: DraftState, team: str, action_type: str,
                   champion_id: int, auto: bool, completed_at) -> Events:
    """Apply one validated action to the draft, persist it and move the game forward."""
    number = draft.cursor
    draft.apply(team, action_type, champion_id, auto=auto)
    db.add(DraftActionRow(game_id=game.id, action_number=number, team=team, action_type=action_type,
                          champion_id=champion_id, auto=auto, started_at=game.action_started_at,
                          completed_at=completed_at))
    events = [_event(game, "CHAMPION_PICKED" if action_type == "PICK" else "CHAMPION_BANNED",
                     team=team, champion_id=champion_id, draft_action=number, auto=auto)]
    track("champion_picked" if action_type == "PICK" else "champion_banned", game_id=game.id, team=team, auto=auto)
    game.current_action = draft.cursor
    if draft.complete:
        game.action_started_at = game.action_expires_at = None
        game.hovered_champion_id = None
        _transition(game, "LANE_ASSIGNMENT")
        _default_lineups(db, game, draft)
        track("draft_completed", game_id=game.id)
        events.append(_event(game, "DRAFT_COMPLETED"))
    else:
        _begin_action(game, game.action_expires_at if auto else completed_at)
        events.append(_action_started_event(game))
    return events


def advance_timeouts(db: Session, game: Game, now=None) -> Events:
    """Apply an automatic action for every draft timer that has expired: the hovered champion if it is
    still legal, otherwise a random legal one."""
    events: Events = []
    now = now or utcnow()
    if game.status != "DRAFTING":
        return events
    draft = load_draft(db, game)
    rng = random.Random(secrets.randbits(64))
    while game.status == "DRAFTING" and game.action_expires_at and game.action_expires_at <= now:
        action = draft.current
        pool = draft.available()
        hovered = game.hovered_champion_id
        champion_id = hovered if hovered in pool else rng.choice(pool)
        events += _record_action(db, game, draft, action.team, action.action_type, champion_id,
                                 True, game.action_expires_at)
    if events:
        db.commit()
    return events


def draft_action(db: Session, game: Game, user: User, action_type: str, champion_id: int) -> Events:
    events = advance_timeouts(db, game)
    side = side_of(game, user.id)
    if game.status != "DRAFTING":
        raise conflict("The draft is not in progress.")
    draft = load_draft(db, game)
    if game.is_solo and draft.current is not None:
        side = draft.current.team        # the single player acts for whichever side is up; type/duplicate checks still apply
    try:
        draft.validate(side, action_type, champion_id)
    except DraftError as exc:
        track("invalid_action", game_id=game.id, user_id=user.id, reason=str(exc))
        raise conflict(str(exc)) from exc
    events += _record_action(db, game, draft, side, action_type, champion_id, False, utcnow())
    db.commit()
    return events


def draft_hover(db: Session, game: Game, user: User, champion_id: int | None, draft_action: int) -> Events:
    """Remember the champion the acting side has hovered, so a timeout locks it in. Private: never broadcast."""
    events = advance_timeouts(db, game)
    if game.status != "DRAFTING":
        raise conflict("The draft is not in progress.")
    draft = load_draft(db, game)
    current = draft.current
    if current is None or draft_action != draft.cursor:
        return events                    # the action already resolved; the hover is stale
    if not game.is_solo and current.team != side_of(game, user.id):
        raise conflict("It is not your turn.")
    if champion_id is not None:
        try:
            draft.validate(current.team, current.action_type, champion_id)
        except DraftError as exc:
            raise conflict(str(exc)) from exc
    game.hovered_champion_id = champion_id
    db.commit()
    return events


# ---------------------------------------------------------------- lineup
def _own_lineup(db: Session, game: Game, side: str) -> dict[str, int]:
    rows = db.scalars(select(TeamLineup).where(TeamLineup.game_id == game.id, TeamLineup.team == side))
    return {r.lane: r.champion_id for r in rows}


def _own_players(db: Session, game: Game, side: str) -> dict[str, int]:
    """lane -> player id for the lanes in the saved lineup (differs from the roster after a position swap)."""
    rows = db.scalars(select(TeamLineup).where(TeamLineup.game_id == game.id, TeamLineup.team == side))
    return {r.lane: r.player_id for r in rows}


def _default_lineups(db: Session, game: Game, draft: DraftState) -> None:
    """When the draft ends, each side starts with its picks in pick order (top, jungle, mid, bot, support),
    matching the champ select rows. Players then swap champions or positions before confirming."""
    for side in ("BLUE", "RED"):
        snap = snapshot_of(db, game, side)
        if snap is None:
            continue
        for lane, cid in zip(LANES, draft.picks[side]):
            p = snap["roster"].get(lane)
            if p:
                db.add(TeamLineup(game_id=game.id, team=side, lane=lane, champion_id=cid, player_id=p["id"]))


def set_lineup(db: Session, game: Game, user: User, assignments: list[dict], requested_side: str | None = None) -> Events:
    side = acting_side(game, user, requested_side)
    if game.status != "LANE_ASSIGNMENT":
        raise conflict("Lineups can only be edited during lane assignment.")
    if (game.blue_lineup_ready if side == "BLUE" else game.red_lineup_ready):
        raise conflict("Your lineup is already confirmed.")
    picks = set(load_draft(db, game).picks[side])
    snap = snapshot_of(db, game, side)
    roster_ids = {lane: p["id"] for lane, p in snap["roster"].items() if p}
    given = [a.get("player_id") for a in assignments]
    if any(pid is not None for pid in given):
        # a position swap: every lane names its player, and each roster player plays exactly one lane
        if any(pid is None for pid in given) or len(set(given)) != len(given) \
                or not set(given) <= set(roster_ids.values()):
            raise bad_request("Each lane needs a different player from your roster.")
    lanes_seen, champs_seen = set(), set()
    for a in assignments:
        lane, cid = a["lane"], a["champion_id"]
        if lane not in LANES:
            raise bad_request(f"Unknown lane {lane!r}.")
        if cid not in picks:
            raise bad_request("You can only assign champions your team picked.")
        if lane in lanes_seen:
            raise bad_request("Each lane can only have one champion.")
        if cid in champs_seen:
            raise bad_request("A champion can only be assigned once.")
        lanes_seen.add(lane)
        champs_seen.add(cid)
    db.execute(delete(TeamLineup).where(TeamLineup.game_id == game.id, TeamLineup.team == side))
    for a in assignments:
        db.add(TeamLineup(game_id=game.id, team=side, lane=a["lane"], champion_id=a["champion_id"],
                          player_id=a.get("player_id") or roster_ids[a["lane"]]))
    db.commit()
    return [_event(game, "LINEUP_UPDATED", team=side)]


def confirm_lineup(db: Session, game: Game, user: User, requested_side: str | None = None) -> Events:
    side = acting_side(game, user, requested_side)
    if game.status != "LANE_ASSIGNMENT":
        raise conflict("Lineups can only be confirmed during lane assignment.")
    lineup = _own_lineup(db, game, side)
    if set(lineup) != set(LANES):
        raise bad_request("Assign a champion to every lane before confirming.")
    if side == "BLUE":
        game.blue_lineup_ready = True
    else:
        game.red_lineup_ready = True
    track("lineup_confirmed", game_id=game.id, team=side)
    events = [_event(game, "PLAYER_READY", team=side, ready=True, phase="LINEUP")]
    if game.blue_lineup_ready and game.red_lineup_ready:
        _transition(game, "READY_TO_SIMULATE")
        events += run_simulation(db, game)
    db.commit()
    return events


def comfort_preview(db: Session, game: Game, user: User, requested_side: str | None = None) -> list[dict]:
    side = acting_side(game, user, requested_side)
    snap = snapshot_of(db, game, side)
    if snap is None:
        raise conflict("The draft has not started.")
    cfg = SIMULATION_CONFIG
    out = []
    lane_players = _lane_players(snap, _own_players(db, game, side))
    for lane, cid in _own_lineup(db, game, side).items():
        p = lane_players[lane]
        spec = _player_spec(p)
        tier = comfort_tier(spec, cid, cfg)
        out.append({"lane": lane, "player_id": p["id"], "champion_id": cid, "tier": tier,
                    "modifier": comfort_modifier(tier, cfg)})
    return out


ATTRIBUTES = ("damage", "sturdiness", "cc", "mobility", "utility")


def matchup_preview(db: Session, game: Game, user: User) -> dict:
    """What the drafted comps mean for the simulation, for the "Show Matchup Data" panel once the draft is done:
    each team's damage mix and itemization penalty, attribute totals and same-team synergy, and lane vs lane win
    rates. Both lineups are shown, including the opponent's current lanes, so swaps can be planned around them."""
    if game.status not in ("LANE_ASSIGNMENT", "READY_TO_SIMULATE", "SIMULATING", "COMPLETED"):
        raise conflict("Matchup data is available once the draft is complete.")
    draft = draft_view(db, game)
    picks = {"BLUE": draft["blue_picks"], "RED": draft["red_picks"]}
    lineups = {s: _own_lineup(db, game, s) for s in ("BLUE", "RED")}

    cfg = simulation_settings_service.current_config(db)
    ids = picks["BLUE"] + picks["RED"]
    champs = {c.id: c.to_engine() for c in db.scalars(select(Champion).where(Champion.id.in_(ids)))}
    table = matchup_service.engine_table(db, ids)

    def rate(delta: float | None) -> float | None:
        return None if delta is None else round(delta, 1)

    teams = {}
    for s, team_ids in picks.items():
        members = [champs[c] for c in team_ids if c in champs]
        profile = damage_profile(members)
        lineup = lineups[s]
        duo = None
        if "BOT" in lineup and "SUPPORT" in lineup:
            duo = table.ally_rate(lineup["BOT"], lineup["SUPPORT"])
        teams[s] = {
            "champions": team_ids,
            "damage_profile": profile,
            "damage_penalty": round(damage_balance_penalty(profile, cfg), 3),
            "totals": {a: sum(getattr(c, a) for c in members) for a in ATTRIBUTES},
            "ally_synergy": rate(ally_delta(team_ids, table, cfg)),
            "duo_win_rate": duo,
        }

    lanes = {}
    for lane in LANES:
        blue, red = lineups["BLUE"].get(lane), lineups["RED"].get(lane)
        lanes[lane] = {"blue": blue, "red": red,
                       "blue_win_rate": table.enemy_rate(blue, red) if blue and red else None}
    wr, db_cfg = cfg["win_rates"], cfg["damage_balance"]
    return {
        "teams": teams,
        "lineups": lineups,
        "lanes": lanes,
        # false when the against-team matrix has no win rates at all, so the panel can say why lanes are blank
        "counter_data": matchup_service.has_rates(db, "enemy"),
        "settings": {"win_rates_enabled": wr["enabled"], "baseline": wr["baseline"],
                     "damage_balance_enabled": db_cfg["enabled"], "damage_threshold": db_cfg["threshold"],
                     "max_damage_penalty": db_cfg["max_penalty"]},
    }


# ------------------------------------------------------------- simulation
def run_simulation(db: Session, game: Game) -> Events:
    events = []
    _transition(game, "SIMULATING")
    game.seed = secrets.randbits(31)
    overrides = simulation_settings_service.overrides(db)
    cfg = simulation_config(overrides)
    game.simulation_version = cfg["version"]
    track("simulation_started", game_id=game.id, seed=game.seed, simulation_version=cfg["version"])
    events.append(_event(game, "SIMULATION_STARTED"))

    champions = {c.id: c.to_engine() for c in db.scalars(select(Champion))}
    setups = {}
    for side in ("BLUE", "RED"):
        setups[side] = _snapshot_to_setup(snapshot_of(db, game, side), _own_lineup(db, game, side),
                                          _own_players(db, game, side))
    table = matchup_service.engine_table(db, [c for setup in setups.values() for c in setup.lineup.values()])
    result = simulate_match(setups["BLUE"], setups["RED"], champions, game.seed, cfg, table)

    data = result.to_dict(include_events=False)
    data["config_overrides"] = overrides
    db.add(MatchResultRow(game_id=game.id, winner=result.winner, win_condition=result.win_condition,
                          duration_seconds=result.duration_seconds, mvp_player_id=result.mvp["player_id"],
                          ace_player_id=result.ace["player_id"], blue_gold=result.teams["BLUE"]["gold"],
                          red_gold=result.teams["RED"]["gold"], seed=game.seed,
                          simulation_version=cfg["version"], data=data))
    for e in result.events:
        db.add(MatchEventRow(game_id=game.id, sequence=e.sequence, phase=e.phase, minute=e.minute,
                             event_type=e.type, payload=e.payload))
    _transition(game, "COMPLETED")
    game.completed_at = utcnow()
    track("game_completed", game_id=game.id, seed=game.seed, winner=result.winner,
          win_condition=result.win_condition, simulation_version=cfg["version"])
    log.info("game_id=%s simulation_version=%s seed=%s winner=%s", game.id, cfg["version"], game.seed, result.winner)
    events.append(_event(game, "SIMULATION_COMPLETED", winner=result.winner))
    return events


def rerun_simulation(db: Session, game: Game, user: User) -> Events:
    """Simulate a finished match again with the same snapshots, draft and lineups but a new seed.
    The previous result and its events are replaced."""
    if game.status != "COMPLETED":
        raise conflict("Only a finished match can be re-run.")
    if game.series_id is not None:
        raise conflict("Matches in a series can't be re-run.")
    if db.get(Lobby, game.lobby_id).created_by != user.id:
        raise forbidden("Only the lobby owner can re-run the match.")
    # bulk deletes run immediately, so the new result does not collide with the unique game_id
    db.execute(delete(MatchEventRow).where(MatchEventRow.game_id == game.id))
    db.execute(delete(MatchResultRow).where(MatchResultRow.game_id == game.id))
    _transition(game, "READY_TO_SIMULATE")
    events = run_simulation(db, game)
    track("simulation_rerun", game_id=game.id, user_id=user.id)
    db.commit()
    return events


# ----------------------------------------------------------------- series
# A series is one Game per game played. Sides can change between games (the loser picks), so results are
# tallied per "series team", named by the side that team played in game 1.
def _other(side: str) -> str:
    return "RED" if side == "BLUE" else "BLUE"


def _series_team(game: Game, side: str) -> str:
    """The series team playing `side` in this game. The mapping is its own inverse, so it also turns a
    series team into the side it plays in this game."""
    return _other(side) if game.sides_swapped else side


def series_games(db: Session, series_id: int) -> list[Game]:
    return list(db.scalars(select(Game).where(Game.series_id == series_id).order_by(Game.game_number)))


def _game_winner(db: Session, game: Game) -> str | None:
    return db.scalar(select(MatchResultRow.winner).where(MatchResultRow.game_id == game.id))


def series_score(db: Session, series: Series, games: list[Game]) -> dict:
    """Wins per series team, and whether the series is decided or abandoned (a game was cancelled)."""
    ids = [g.id for g in games if g.status == "COMPLETED"]
    winners = dict(db.execute(select(MatchResultRow.game_id, MatchResultRow.winner)
                              .where(MatchResultRow.game_id.in_(ids))).all()) if ids else {}
    score = {"BLUE": 0, "RED": 0}
    for g in games:
        if g.id in winners:
            score[_series_team(g, winners[g.id])] += 1
    winner = next((team for team, wins in score.items() if wins >= series.wins_needed), None)
    return {"score": score, "winner": winner, "complete": winner is not None,
            "abandoned": winner is None and any(g.status == "CANCELLED" for g in games)}


def fearless_locked_ids(db: Session, game: Game) -> set[int]:
    """Fearless draft: every champion picked in an earlier game of the series."""
    if game.series_id is None or game.game_number <= 1 or not db.get(Series, game.series_id).fearless:
        return set()
    return set(db.scalars(select(DraftActionRow.champion_id).join(Game, Game.id == DraftActionRow.game_id)
                          .where(Game.series_id == game.series_id, Game.game_number < game.game_number,
                                 DraftActionRow.action_type == "PICK")))


def _series_summary(db: Session, game: Game) -> dict | None:
    if game.series_id is None:
        return None
    series = db.get(Series, game.series_id)
    return {"id": series.id, "format": series.format, "fearless": series.fearless, "game_number": game.game_number}


def series_state(db: Session, game: Game) -> dict | None:
    """The series as seen from this game: every side below is this game's Blue/Red."""
    if game.series_id is None:
        return None
    series = db.get(Series, game.series_id)
    games = series_games(db, series.id)
    tally = series_score(db, series, games)
    following = next((g for g in games if g.game_number == game.game_number + 1), None)
    winner = _game_winner(db, game) if game.status == "COMPLETED" else None
    return {
        "id": series.id, "format": series.format, "wins_needed": series.wins_needed, "fearless": series.fearless,
        "game_number": game.game_number,
        "score": {side: tally["score"][_series_team(game, side)] for side in ("BLUE", "RED")},
        "complete": tally["complete"], "abandoned": tally["abandoned"],
        "series_winner": _series_team(game, tally["winner"]) if tally["winner"] else None,
        "loser_side": _other(winner) if winner else None,
        "next_game_id": following.id if following else None,
        "next_ready": {"blue": game.blue_next_ready, "red": game.red_next_ready},
        "next_loser_side": game.next_loser_side,
    }


def ready_next_game(db: Session, game: Game, user: User, ready: bool = True, side: str | None = None) -> Events:
    """Ready up for the next game of the series. The previous game's loser must say which side they want.
    Once both sides are ready the next game starts straight in the draft."""
    if game.series_id is None:
        raise conflict("This game is not part of a series.")
    if game.status != "COMPLETED":
        raise conflict("Finish this game before readying up for the next one.")
    series = db.get(Series, game.series_id)
    games = series_games(db, series.id)
    tally = series_score(db, series, games)
    if tally["complete"] or tally["abandoned"]:
        raise conflict("The series is over.")
    if any(g.game_number > game.game_number for g in games):
        raise conflict("The next game has already started.")
    loser = _other(_game_winner(db, game))
    me = side_of(game, user.id)
    chooses = game.is_solo or me == loser          # single player: you choose for the losing team
    if ready and chooses and side not in ("BLUE", "RED"):
        raise bad_request("Choose Blue or Red for the next game.")
    if game.is_solo:
        game.blue_next_ready = game.red_next_ready = ready
        sides = ["BLUE", "RED"]
    else:
        if me == "BLUE":
            game.blue_next_ready = ready
        else:
            game.red_next_ready = ready
        sides = [me]
    if chooses:
        game.next_loser_side = side if ready else None
    events = [_event(game, "SERIES_READY", team=s, ready=ready) for s in sides]
    if game.blue_next_ready and game.red_next_ready:
        events += _start_next_game(db, game, loser)
    db.commit()
    return events


def _start_next_game(db: Session, prev: Game, loser: str) -> Events:
    """Create the series' next game with the same players, teams and frozen snapshots, swapping sides if the
    loser asked for the other side, and open its draft. Each game has its own lobby row (one game per lobby)."""
    swap = prev.next_loser_side != loser

    def flip(blue, red):
        return (red, blue) if swap else (blue, red)

    prev_lobby = db.get(Lobby, prev.lobby_id)
    now = utcnow()
    lobby = Lobby(code=_new_code(db), created_by=prev_lobby.created_by, settings=prev_lobby.settings,
                  created_at=now, expires_at=now + timedelta(minutes=GAME_CONFIG["lobby_expiration_minutes"]))
    db.add(lobby)
    db.flush()
    blue_player, red_player = flip(prev.blue_player_id, prev.red_player_id)
    blue_team, red_team = flip(prev.blue_team_id, prev.red_team_id)
    blue_snap, red_snap = flip(snapshot_of(db, prev, "BLUE"), snapshot_of(db, prev, "RED"))
    game = Game(lobby_id=lobby.id, status="READY_CHECK", blue_player_id=blue_player, red_player_id=red_player,
                blue_team_id=blue_team, red_team_id=red_team, is_solo=prev.is_solo,
                hide_player_data=prev.hide_player_data, bans_enabled=prev.bans_enabled,
                timers_enabled=prev.timers_enabled, pick_seconds=prev.pick_seconds, ban_seconds=prev.ban_seconds,
                series_id=prev.series_id, game_number=prev.game_number + 1,
                sides_swapped=prev.sides_swapped != swap, blue_ready=True, red_ready=True)
    db.add(game)
    db.flush()
    events = _start_draft(db, game, {"BLUE": blue_snap, "RED": red_snap})
    track("series_game_started", series_id=prev.series_id, game_id=game.id, game_number=game.game_number)
    return [_event(prev, "SERIES_NEXT_GAME", next_game_id=game.id, game_number=game.game_number), *events]


def series_result(db: Session, series_id: int, user: User) -> dict:
    """Every game of a series with its draft and result. Team keys (`teams`, `score`, `winner`, each game's
    `blue_team`/`red_team`/`winner`) name the side that team played in game 1."""
    series = db.get(Series, series_id)
    games = series_games(db, series_id) if series else []
    if not games or side_of(games[0], user.id) is None:
        raise not_found("Series not found.")
    results = {r.game_id: r for r in db.scalars(
        select(MatchResultRow).where(MatchResultRow.game_id.in_([g.id for g in games])))}
    out = []
    for g in games:
        r = results.get(g.id) if g.status == "COMPLETED" else None
        draft = draft_view(db, g) if g.started_at else None
        out.append({
            "game_id": g.id, "game_number": g.game_number, "status": g.status,
            "blue_team": _series_team(g, "BLUE"), "red_team": _series_team(g, "RED"),
            "winner": _series_team(g, r.winner) if r else None,
            "win_condition": r.win_condition if r else None,
            "duration_seconds": r.duration_seconds if r else None,
            "mvp": r.data.get("mvp") if r else None,
            "draft": {"bans": draft["bans"], "blue_picks": draft["blue_picks"],
                      "red_picks": draft["red_picks"]} if draft else None,
        })
    first = games[0]
    return {
        "id": series.id, "format": series.format, "wins_needed": series.wins_needed, "fearless": series.fearless,
        "mode": "SOLO" if first.is_solo else "MULTI",
        "teams": {side: (snapshot_of(db, first, side) or {}).get("name") for side in ("BLUE", "RED")},
        **series_score(db, series, games),
        "games": out,
    }


# ---------------------------------------------------------- state views
HIDDEN_PLAYER_FIELDS = ("age", "aggr", "aware", "pos", "dmg", "cs", "pool", "stat_total", "region", "riot")


def _mask_player(p: dict | None) -> dict | None:
    if p is None:
        return None
    masked = {k: v for k, v in p.items() if k not in HIDDEN_PLAYER_FIELDS}
    masked["hidden"] = True
    return masked


def _mask_team(view: dict) -> dict:
    out = dict(view)
    out["roster"] = {lane: _mask_player(p) for lane, p in view["roster"].items()}
    out["over_budget_players"] = [{k: v for k, v in o.items() if k != "total"} for o in view["over_budget_players"]]
    out["hidden"] = True
    return out


def _team_view(db: Session, game: Game, side: str, viewer_side: str) -> dict | None:
    snap = snapshot_of(db, game, side)
    if snap is not None:
        view = {k: snap[k] for k in ("name", "logo", "region", "fanbase", "style1", "style2", "focus1", "focus2",
                                     "coach", "roster", "over_budget", "over_budget_players")}
        view["id"] = snap["team_id"]
    else:
        team_id = game.blue_team_id if side == "BLUE" else game.red_team_id
        if team_id is None:
            return None
        team = db.get(Team, team_id)
        if team is None:
            return None
        full = teams.team_view(db, team)
        view = {k: full[k] for k in ("id", "name", "logo", "region", "fanbase", "style1", "style2", "focus1",
                                     "focus2", "coach", "roster", "over_budget", "over_budget_players")}
    if side != viewer_side and game.hide_player_data and game.status != "COMPLETED":
        return _mask_team(view)
    return view


def draft_view(db: Session, game: Game) -> dict:
    draft = load_draft(db, game)
    current = draft.current if game.status == "DRAFTING" else None
    return {
        "actions": draft_actions(game),
        "timers_enabled": game.timers_enabled,
        "pick_seconds": game.pick_seconds,
        "ban_seconds": game.ban_seconds,
        "current_action": draft.cursor,
        "current_team": current.team if current else None,
        "action_type": current.action_type if current else None,
        "started_at": iso(game.action_started_at) if current else None,
        "expires_at": iso(game.action_expires_at) if current else None,
        "bans": [{"team": t, "champion_id": c} for t, c in draft.bans],
        "blue_picks": draft.picks["BLUE"],
        "red_picks": draft.picks["RED"],
        "history": [{"action_number": i, "team": t, "action_type": k, "champion_id": c, "auto": a}
                    for i, t, k, c, a in draft.history],
        "complete": draft.complete,
        "fearless_locked": sorted(draft.locked),
    }


def _settings_view(db: Session, game: Game) -> dict:
    series = db.get(Series, game.series_id) if game.series_id else None
    return {"hide_player_data": game.hide_player_data, "bans_enabled": game.bans_enabled,
            "timers_enabled": game.timers_enabled, "pick_seconds": game.pick_seconds,
            "ban_seconds": game.ban_seconds, "mode": "SOLO" if game.is_solo else "MULTI",
            "series_format": series.format if series else "BO1", "fearless": bool(series and series.fearless)}


def game_state(db: Session, game: Game, viewer: User) -> dict:
    side = side_of(game, viewer.id)
    lobby = db.get(Lobby, game.lobby_id)
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(
        [i for i in (game.blue_player_id, game.red_player_id) if i])))}

    def player(uid, team_id, ready, lineup_ready):
        return None if uid is None else {"id": uid, "username": users[uid].username, "team_id": team_id,
                                         "ready": ready, "lineup_ready": lineup_ready}

    state = {
        "game_id": game.id,
        "lobby_id": lobby.id,
        "lobby_code": lobby.code,
        "status": game.status,
        "settings": _settings_view(db, game),
        "expires_at": iso(lobby.expires_at) if game.status in PRE_DRAFT else None,
        "you": {"user_id": viewer.id, "team": side, "is_owner": lobby.created_by == viewer.id},
        "players": {
            "blue": player(game.blue_player_id, game.blue_team_id, game.blue_ready, game.blue_lineup_ready),
            "red": player(game.red_player_id, game.red_team_id, game.red_ready, game.red_lineup_ready),
        },
        "teams": {"BLUE": _team_view(db, game, "BLUE", side), "RED": _team_view(db, game, "RED", side)},
        "draft": None,
        "lineup": None,
        "result_available": game.status == "COMPLETED",
        "seed": game.seed if game.status == "COMPLETED" else None,
        "simulation_version": game.simulation_version if game.status == "COMPLETED" else None,
        "series": series_state(db, game),
    }
    if game.status in ("DRAFTING", "LANE_ASSIGNMENT", "READY_TO_SIMULATE", "SIMULATING", "COMPLETED"):
        state["draft"] = draft_view(db, game)
        lineups = {"yours": _own_lineup(db, game, side)}
        visible = [side]
        if game.is_solo:        # one person sees (and edits) both lineups
            lineups["blue"] = _own_lineup(db, game, "BLUE")
            lineups["red"] = _own_lineup(db, game, "RED")
            visible = ["BLUE", "RED"]
        if game.status == "COMPLETED":  # the opponent's assignments stay hidden until the game is over
            other = "RED" if side == "BLUE" else "BLUE"
            lineups["opponent"] = _own_lineup(db, game, other)
            visible = ["BLUE", "RED"]
        # lane -> player id per visible side (a position swap moves players off their roster lane)
        lineups["players"] = {s: _own_players(db, game, s) for s in visible}
        state["lineup"] = lineups
    return state


def game_result(db: Session, game: Game) -> dict:
    if game.status != "COMPLETED":
        raise conflict("The match has not finished.")
    row = db.scalar(select(MatchResultRow).where(MatchResultRow.game_id == game.id))
    draft = draft_view(db, game)
    return {
        "game_id": game.id,
        **row.data,
        "draft": {"bans": draft["bans"], "blue_picks": draft["blue_picks"], "red_picks": draft["red_picks"],
                  "history": draft["history"]},
        "lineups": {side: _own_lineup(db, game, side) for side in ("BLUE", "RED")},
        "teams_info": {side: snapshot_of(db, game, side) for side in ("BLUE", "RED")},
    }


def result_events(db: Session, game: Game, after: int = 0, limit: int = 200) -> dict:
    if game.status != "COMPLETED":
        raise conflict("The match has not finished.")
    rows = db.scalars(select(MatchEventRow).where(MatchEventRow.game_id == game.id, MatchEventRow.sequence > after)
                      .order_by(MatchEventRow.sequence).limit(limit)).all()
    return {
        "events": [{"sequence": r.sequence, "phase": r.phase, "minute": round(r.minute, 2),
                    "type": r.event_type, "payload": r.payload} for r in rows],
        "next_after": rows[-1].sequence if len(rows) == limit else None,
    }


def lobby_view(db: Session, game: Game, viewer: User) -> dict:
    lobby = db.get(Lobby, game.lobby_id)
    return {"id": lobby.id, "code": lobby.code, "game_id": game.id, "status": game.status,
            "settings": _settings_view(db, game), "expires_at": iso(lobby.expires_at),
            "created_by": lobby.created_by, "you": side_of(game, viewer.id), "series": _series_summary(db, game)}


# ------------------------------------------------------------------- chat
CHAT_MAX_LENGTH = 200
CHAT_HISTORY = 100
CHAT_BURST = (5, timedelta(seconds=10))   # at most 5 messages per 10 seconds per player


def _chat_view(msg: ChatMessage, username: str) -> dict:
    return {"id": msg.id, "user_id": msg.user_id, "username": username, "team": msg.team,
            "body": msg.body, "created_at": iso(msg.created_at)}


def chat_history(db: Session, game: Game) -> list[dict]:
    """The latest messages of a game's all-chat, oldest first."""
    rows = db.execute(select(ChatMessage, User.username).join(User, User.id == ChatMessage.user_id)
                      .where(ChatMessage.game_id == game.id)
                      .order_by(ChatMessage.id.desc()).limit(CHAT_HISTORY)).all()
    return [_chat_view(m, name) for m, name in reversed(rows)]


def send_chat(db: Session, game: Game, user: User, text: str) -> tuple[dict, Events]:
    """Post to the game's all-chat; both players see it. Plain text only (the client never renders HTML)."""
    body = " ".join(text.split())          # collapse newlines and runs of spaces
    if not body:
        raise bad_request("Type a message first.")
    if len(body) > CHAT_MAX_LENGTH:
        raise bad_request(f"Messages are limited to {CHAT_MAX_LENGTH} characters.")
    if game.status == "CANCELLED":
        raise conflict("This game was cancelled.")
    limit, window = CHAT_BURST
    recent = db.scalars(select(ChatMessage.id).where(ChatMessage.game_id == game.id, ChatMessage.user_id == user.id,
                                                     ChatMessage.created_at > utcnow() - window)).all()
    if len(recent) >= limit:
        raise bad_request("Slow down: you're sending messages too fast.")
    msg = ChatMessage(game_id=game.id, user_id=user.id, team=side_of(game, user.id), body=body, created_at=utcnow())
    db.add(msg)
    db.commit()
    view = _chat_view(msg, user.username)
    return view, [_event(game, "CHAT_MESSAGE", message=view)]


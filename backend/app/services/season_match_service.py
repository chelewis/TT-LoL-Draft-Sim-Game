"""Playing season fixtures: live through the normal draft (a manager against the CPU), or auto-played with the CPU
deciding for both sides. Every game is an ordinary Game row with `season_match_id` set, so results, replays and
series all work as they do for lobbies.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import bad_request, conflict, forbidden
from app.game.competition import wins_needed
from app.models import Game, MatchResultRow, Season, SeasonMatch, SeasonTeam, User
from app.services import game_service as gs
from app.services.analytics import track

Events = list[dict]
PLAYING = ("REGULAR", "PLAYOFFS")

_busy: set[int] = set()
_busy_lock = threading.Lock()


@contextmanager
def simulating(season_id: int):
    """Only one simulation (a round, or an auto-simmed match) runs per season at a time, so a double click can't
    play the same fixture twice."""
    with _busy_lock:
        if season_id in _busy:
            raise conflict("This season is already simulating. Try again in a moment.")
        _busy.add(season_id)
    try:
        yield
    finally:
        with _busy_lock:
            _busy.discard(season_id)


# ----------------------------------------------------------------- lookups
def current_stage(season: Season) -> str:
    """The stage being played: the playoffs once they've started, else the Swiss stage or round robin."""
    if season.status == "PLAYOFFS":
        return "PLAYOFF"
    return "SWISS" if season.format == "SWISS" else "REGULAR"


def is_member(db: Session, season: Season, user_id: int) -> bool:
    """The creator and every team manager belong to the season (and may watch any of its games)."""
    if season.created_by == user_id:
        return True
    return db.scalar(select(SeasonTeam.id).where(SeasonTeam.season_id == season.id,
                                                 SeasonTeam.manager_user_id == user_id)) is not None


def can_view_game(db: Session, game: Game, user_id: int) -> bool:
    match = db.get(SeasonMatch, game.season_match_id)
    return match is not None and is_member(db, db.get(Season, match.season_id), user_id)


def match_games(db: Session, match: SeasonMatch) -> list[Game]:
    return list(db.scalars(select(Game).where(Game.season_match_id == match.id).order_by(Game.id)))


def _sides(db: Session, match: SeasonMatch) -> tuple[SeasonTeam, SeasonTeam]:
    return db.get(SeasonTeam, match.home_team_id), db.get(SeasonTeam, match.away_team_id)


def has_manager(db: Session, match: SeasonMatch) -> bool:
    return any(st.manager_user_id is not None for st in _sides(db, match))


def game_season_info(db: Session, game: Game) -> dict | None:
    """What a game page shows about the season it belongs to (and links back to)."""
    match = db.get(SeasonMatch, game.season_match_id)
    if match is None:
        return None
    season = db.get(Season, match.season_id)
    return {"season_id": season.id, "season_name": season.name, "match_id": match.id, "stage": match.stage,
            "round": match.round, "format": match.format}


# ----------------------------------------------------------------- results
def _tally(db: Session, match: SeasonMatch, games: list[Game]) -> dict[int, int]:
    """Games won by each season team in the fixture (keyed by SeasonTeam id)."""
    home, away = _sides(db, match)
    by_team = {home.team_id: home.id, away.team_id: away.id}
    wins = {home.id: 0, away.id: 0}
    done = [g.id for g in games if g.status == "COMPLETED"]
    winners = dict(db.execute(select(MatchResultRow.game_id, MatchResultRow.winner)
                              .where(MatchResultRow.game_id.in_(done))).all()) if done else {}
    for g in games:
        side = winners.get(g.id)
        if side:
            team_id = g.blue_team_id if side == "BLUE" else g.red_team_id
            if team_id in by_team:
                wins[by_team[team_id]] += 1
    return wins


def on_game_completed(db: Session, game: Game) -> None:
    """A season game finished (called by game_service.run_simulation): update the fixture's score, and decide it
    once a team has won enough games. The caller commits."""
    match = db.get(SeasonMatch, game.season_match_id)
    if match is None or match.status == "COMPLETED":
        return
    db.flush()
    wins = _tally(db, match, match_games(db, match))
    match.home_score, match.away_score = wins[match.home_team_id], wins[match.away_team_id]
    need = wins_needed(match.format)
    if max(match.home_score, match.away_score) >= need:
        match.status = "COMPLETED"
        match.winner_team_id = match.home_team_id if match.home_score > match.away_score else match.away_team_id
        match.completed_at = utcnow()
        track("season_match_completed", season_id=match.season_id, match_id=match.id, mode=match.played_mode)


# -------------------------------------------------------------- new games
def _lobby_settings(season: Season, match: SeasonMatch) -> dict:
    rules = season.settings["rules"]
    return {**rules, "series_format": match.format,
            "fearless": bool(rules.get("fearless")) and match.format != "BO1",
            "hide_player_data": False}       # against the CPU there is no opponent to hide anything from


def _new_game(db: Session, season: Season, match: SeasonMatch, blue: SeasonTeam, red: SeasonTeam,
              blue_user: int | None, red_user: int | None, owner_id: int) -> Game:
    """A game of the fixture between `blue` and `red`, waiting at the ready check (flushed, so it has an id).
    The first game also opens the fixture's series when it is a best of 3 or 5."""
    settings = _lobby_settings(season, match)
    lobby = gs._open_lobby(db, owner_id, settings)
    game = Game(lobby_id=lobby.id, status="READY_CHECK", blue_player_id=blue_user, red_player_id=red_user,
                blue_team_id=blue.team_id, red_team_id=red.team_id, is_solo=False, vs_cpu=True,
                hide_player_data=False, bans_enabled=bool(settings["bans_enabled"]),
                timers_enabled=bool(settings["timers_enabled"]), pick_seconds=int(settings["pick_seconds"]),
                ban_seconds=int(settings["ban_seconds"]), season_match_id=match.id,
                blue_ready=True, red_ready=True, sides_swapped=blue.id != match.home_team_id)
    previous = match_games(db, match)
    if match.series_id is None:
        gs._open_series(db, game, settings, owner_id)
        match.series_id = game.series_id
    else:
        game.series_id = match.series_id
        game.game_number = max((g.game_number for g in previous), default=0) + 1
    db.add(game)
    db.flush()
    return game


def _my_team(db: Session, match: SeasonMatch, user: User) -> SeasonTeam:
    mine = next((st for st in _sides(db, match) if st.manager_user_id == user.id), None)
    if mine is None:
        raise forbidden("You don't manage a team in this match.")
    return mine


def _check_playable(season: Season, match: SeasonMatch) -> None:
    if season.status not in PLAYING:
        raise conflict("The season isn't in progress.")
    if match.stage != current_stage(season) or match.round != season.current_round:
        raise conflict("That match isn't in the current round.")
    if match.status == "COMPLETED":
        raise conflict("That match has already been played.")


def play_match(db: Session, season: Season, match: SeasonMatch, user: User) -> tuple[Game, Events]:
    """Play your fixture live: opens the first game straight in the draft (the CPU plays the other side).
    Calling it again returns the game in progress (or the latest one, between games of a series)."""
    _check_playable(season, match)
    mine = _my_team(db, match, user)
    games = match_games(db, match)
    if games:
        return games[-1], []
    home, away = _sides(db, match)
    other = away if mine.id == home.id else home
    if other.manager_user_id is not None:
        raise bad_request("Matches between two managers arrive with multiplayer seasons.")
    blue_user = user.id if mine.id == home.id else None
    red_user = user.id if mine.id == away.id else None
    game = _new_game(db, season, match, home, away, blue_user, red_user, user.id)
    match.status, match.played_mode = "LIVE", "LIVE"
    events = gs._start_draft(db, game)
    db.commit()
    track("season_match_live", season_id=season.id, match_id=match.id, game_id=game.id, user_id=user.id)
    return game, events


def auto_play_match(db: Session, season: Season, match: SeasonMatch,
                    lookups: gs.CpuLookups | None = None) -> Events:
    """Decide the fixture with the CPU playing both sides: finish a game in progress, then play new games until
    the series is won. The losing team takes Blue in the next game. The caller commits."""
    events: Events = []
    lookups = lookups or gs.CpuLookups(db)
    if match.status == "SCHEDULED":
        match.played_mode = "AUTO"
    match.status = "LIVE" if match.status == "SCHEDULED" else match.status
    home, away = _sides(db, match)
    for _ in range(10):                     # a best of 5 needs at most 5 games; this only guards a bad state
        if match.status == "COMPLETED":
            break
        games = match_games(db, match)
        last = games[-1] if games else None
        if last is not None and last.status in gs.ACTIVE:
            events += gs.autoplay_game(db, last, lookups)
            continue
        if last is None:
            blue, red = home, away
        else:
            winner = db.scalar(select(MatchResultRow.winner).where(MatchResultRow.game_id == last.id))
            blue_won = winner == "BLUE"
            last_blue = home if last.blue_team_id == home.team_id else away
            last_red = away if last_blue is home else home
            blue, red = (last_red, last_blue) if blue_won else (last_blue, last_red)   # the loser takes Blue
        game = _new_game(db, season, match, blue, red, None, None, season.created_by)
        events += gs.autoplay_game(db, game, lookups)
    return events


def auto_sim_my_match(db: Session, season: Season, match: SeasonMatch, user: User) -> Events:
    """Let the CPU play your fixture for you (including the rest of one you started live)."""
    _check_playable(season, match)
    _my_team(db, match, user)
    home, away = _sides(db, match)
    if home.manager_user_id is not None and away.manager_user_id is not None:
        raise bad_request("Matches between two managers arrive with multiplayer seasons.")
    with simulating(season.id):
        db.refresh(match)
        if match.status == "COMPLETED":
            raise conflict("That match has already been played.")
        events = auto_play_match(db, season, match)
        db.commit()
    track("season_match_auto", season_id=season.id, match_id=match.id, user_id=user.id)
    return events

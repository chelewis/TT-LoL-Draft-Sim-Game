"""Seasons: create a league, enter teams, fill the rest with CPU teams, play it round by round, and the views of
the standings, schedule and teams. Playing individual fixtures lives in season_match_service.

Bring Your Own: each manager enters one of their own teams (a frozen copy plays the season). Friends join with the
season's invite code; the CPU generates and runs every team nobody manages. Rounds close when the creator advances
them, or by themselves at the round deadline.
"""
from __future__ import annotations

import random
import secrets
import string
from datetime import timedelta

from fastapi import HTTPException

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import iso, utcnow
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.game import competition, player_generator
from app.models import (Champion, Coach, Game, MatchResultRow, Player, PlayerPoolEntry, Season, SeasonMatch,
                        SeasonTeam, Team, TeamRosterSlot, User)
from app.schemas.season import SeasonCreate
from app.services import game_service as gs
from app.services import lobby_rules
from app.services import season_match_service as matches
from app.services import team_management_service as teams
from app.services.analytics import track

Events = list[dict]
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1L")
FINISHED = ("COMPLETED", "CANCELLED")
MAX_ACTIVE_SEASONS = 10          # seasons a user can have created that haven't finished
IN_PLAY = ("DRAFTING", "LANE_ASSIGNMENT", "READY_TO_SIMULATE", "SIMULATING")
# at the round deadline a match managers are still drafting gets this long to finish before the CPU takes over
DEADLINE_GRACE = timedelta(minutes=30)


# ----------------------------------------------------------------- access
def _rules(season: Season) -> dict:
    return season.settings["rules"]


def _options(season: Season) -> dict:
    return {k: v for k, v in season.settings.items() if k != "rules"}


def get_season(db: Session, season_id: int, user: User) -> Season:
    season = db.get(Season, season_id)
    if season is None or not matches.is_member(db, season, user.id):
        raise not_found("Season not found.")
    return season


def get_match(db: Session, match_id: int, user: User) -> tuple[Season, SeasonMatch]:
    match = db.get(SeasonMatch, match_id)
    if match is None:
        raise not_found("Match not found.")
    return get_season(db, match.season_id, user), match


def _require_creator(season: Season, user: User) -> None:
    if season.created_by != user.id:
        raise forbidden("Only the season's creator can do that.")


def season_teams(db: Session, season: Season) -> list[SeasonTeam]:
    return list(db.scalars(select(SeasonTeam).where(SeasonTeam.season_id == season.id)
                           .order_by(SeasonTeam.seed, SeasonTeam.id)))


def _season_matches(db: Session, season: Season) -> list[SeasonMatch]:
    return list(db.scalars(select(SeasonMatch).where(SeasonMatch.season_id == season.id)
                           .order_by(SeasonMatch.round, SeasonMatch.slot, SeasonMatch.id)))


# ------------------------------------------------------------------ setup
def _new_code(db: Session) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if db.scalar(select(Season.id).where(Season.code == code)) is None:
            return code
    raise RuntimeError("Could not generate a unique season code")


def create_season(db: Session, user: User, body: SeasonCreate) -> Season:
    if body.roster_mode != "BYO":
        raise bad_request("Player Draft seasons are coming soon. Choose Bring Your Own for now.")
    active = db.scalar(select(func.count()).select_from(Season).where(Season.created_by == user.id,
                                                                     Season.status.not_in(FINISHED)))
    if active >= MAX_ACTIVE_SEASONS:
        raise conflict(f"You can run at most {MAX_ACTIVE_SEASONS} seasons at once. Finish or cancel one first.")
    options = body.options.model_dump()
    if body.format == "SWISS":
        # 8 teams: 2 wins to qualify, 2 losses out; 16 teams: 3 and 3. Half the field reaches the bracket.
        options["swiss_wins"] = options["swiss_losses"] = options["team_count"].bit_length() - 2
        options["playoff_size"] = options["team_count"] // 2
        options["rr_double"] = False
    season = Season(name=body.name.strip(), code=_new_code(db), created_by=user.id, status="SETUP",
                    roster_mode=body.roster_mode, format=body.format,
                    settings={"rules": body.rules.model_dump(), **options})
    db.add(season)
    db.commit()
    track("season_created", season_id=season.id, user_id=user.id, format=season.format,
          roster_mode=season.roster_mode, team_count=options["team_count"])
    return season


def list_seasons(db: Session, user: User) -> list[dict]:
    managed = select(SeasonTeam.season_id).where(SeasonTeam.manager_user_id == user.id)
    rows = db.scalars(select(Season).where(or_(Season.created_by == user.id, Season.id.in_(managed)))
                      .order_by(Season.created_at.desc()))
    return [season_summary(db, s, user) for s in rows]


def _copy_into_season(db: Session, season: Season, source: Team, owner_id: int) -> Team:
    """A frozen copy of a team (its players and coach too) that belongs to the season."""
    coach = None
    if source.coach is not None:
        coach = Coach(owner_user_id=owner_id, season_id=season.id, name=source.coach.name,
                      draft=source.coach.draft, synergy=source.coach.synergy)
        db.add(coach)
    copies: dict[str, Player] = {}
    for slot in source.slots:
        copy = teams.copy_player(db.get(Player, slot.player_id), owner_id, season.id)
        db.add(copy)
        copies[slot.lane] = copy
    db.flush()
    team = Team(owner_user_id=owner_id, season_id=season.id, name=source.name, logo=source.logo,
                region=source.region, fanbase=source.fanbase, style1=source.style1, style2=source.style2,
                focus1=source.focus1, focus2=source.focus2, coach_id=coach.id if coach else None)
    team.slots = [TeamRosterSlot(lane=lane, player_id=p.id) for lane, p in copies.items()]
    db.add(team)
    db.flush()
    return team


def enter_team(db: Session, season: Season, user: User, team_id: int) -> SeasonTeam:
    """Bring Your Own: enter one of your teams. A frozen copy plays in the season, so later edits to your team
    don't change it. The team must be complete and meet the season's rules."""
    if season.status != "SETUP":
        raise conflict("Teams can only be entered before the season starts.")
    if season.roster_mode != "BYO":
        raise conflict("This season drafts its players; there's no team to bring.")
    existing = season_teams(db, season)
    if any(st.manager_user_id == user.id for st in existing):
        raise conflict("You already have a team in this season. Withdraw it first to enter another.")
    if sum(st.manager_user_id is not None for st in existing) >= _options(season)["human_slots"]:
        raise conflict("Every manager slot in this season is taken.")
    source = teams.get_visible(db, Team, team_id, user.id)
    taken = {t.name.lower() for t in db.scalars(select(Team).where(Team.id.in_([st.team_id for st in existing])))}
    if source.name.lower() in taken:
        raise conflict(f"A team called {source.name} is already in this season. Enter a different team.")
    issues = teams.team_issues(source)
    if issues:
        raise bad_request("That team can't be entered yet: " + "; ".join(issues))
    broken = lobby_rules.team_rule_issues(teams.team_view(db, source), _rules(season))
    if broken:
        raise bad_request("That team breaks this season's rules: " + "; ".join(broken))
    copy = _copy_into_season(db, season, source, user.id)
    st = SeasonTeam(season_id=season.id, team_id=copy.id, manager_user_id=user.id)
    db.add(st)
    db.commit()
    track("season_team_entered", season_id=season.id, user_id=user.id)
    return st


def _delete_team_copy(db: Session, team: Team) -> None:
    player_ids = [s.player_id for s in team.slots]
    coach = team.coach
    db.delete(team)
    db.flush()
    for pid in player_ids:
        player = db.get(Player, pid)
        if player is not None and player.season_id is not None:
            db.delete(player)
    if coach is not None and coach.season_id is not None:
        db.delete(coach)


def _by_code(db: Session, code: str) -> Season:
    season = db.scalar(select(Season).where(Season.code == code.strip().upper()))
    if season is None or season.status == "CANCELLED":
        raise not_found("No season with that code.")
    return season


def join_preview(db: Session, code: str, user: User) -> dict:
    """What someone with the invite code sees before joining: the season, its rules and the open manager slots."""
    season = _by_code(db, code)
    sts = season_teams(db, season)
    managers = sum(st.manager_user_id is not None for st in sts)
    slots = _options(season)["human_slots"]
    has_team = any(st.manager_user_id == user.id for st in sts)
    creator = db.get(User, season.created_by)
    return {
        "id": season.id, "name": season.name, "code": season.code, "status": season.status,
        "roster_mode": season.roster_mode, "format": season.format, "rules": _rules(season),
        "options": _options(season), "ruleset_name": lobby_rules.ruleset(_rules(season).get("ruleset"))["name"],
        "created_by": {"id": creator.id, "username": creator.username} if creator else None,
        "managers": managers, "open_slots": max(0, slots - managers),
        "is_member": matches.is_member(db, season, user.id), "has_team": has_team,
        "can_join": season.status == "SETUP" and managers < slots and not has_team,
    }


def join_season(db: Session, code: str, user: User, team_id: int) -> Season:
    """Join with the invite code by entering one of your teams (the same checks as entering it from the hub)."""
    season = _by_code(db, code)
    enter_team(db, season, user, team_id)
    return season


def release_team(db: Session, season: Season, user: User, season_team_id: int) -> Events:
    """Take a manager off their team: the manager leaving, or the creator removing them. Before the season starts
    their entry is withdrawn; after that the CPU runs the team for the rest of the season."""
    st = db.get(SeasonTeam, season_team_id)
    if st is None or st.season_id != season.id:
        raise not_found("Team not found.")
    if st.manager_user_id is None:
        raise conflict("The CPU already runs that team.")
    if user.id not in (season.created_by, st.manager_user_id):
        raise forbidden("Only the season's creator can remove another manager.")
    if season.status in FINISHED:
        raise conflict("The season is over.")
    manager_id = st.manager_user_id
    if season.status == "SETUP":
        team = db.get(Team, st.team_id)
        db.delete(st)
        db.flush()
        if team is not None:
            _delete_team_copy(db, team)
        db.commit()
        events: Events = []
    else:
        with matches.simulating(season.id):
            db.refresh(season)
            events = matches.hand_to_cpu(db, season, st)
            db.commit()
    track("season_manager_released", season_id=season.id, user_id=manager_id, by=user.id)
    return events + [matches.season_event(season.id)]


def withdraw_team(db: Session, season: Season, user: User) -> None:
    if season.status != "SETUP":
        raise conflict("Teams can only be withdrawn before the season starts.")
    st = next((st for st in season_teams(db, season) if st.manager_user_id == user.id), None)
    if st is None:
        raise not_found("You have no team in this season.")
    team = db.get(Team, st.team_id)
    db.delete(st)
    db.flush()
    if team is not None:
        _delete_team_copy(db, team)
    db.commit()


def _create_cpu_team(db: Session, season: Season, data: dict) -> SeasonTeam:
    c = data["coach"]
    coach = Coach(owner_user_id=None, season_id=season.id, name=c["name"], draft=c["draft"], synergy=c["synergy"])
    db.add(coach)
    players: dict[str, Player] = {}
    for lane, p in data["roster"].items():
        player = Player(owner_user_id=None, season_id=season.id, name=p["name"], role=p["role"], age=p["age"],
                        region=p["region"], aggr=p["aggr"], aware=p["aware"], pos=p["pos"], dmg=p["dmg"],
                        cs=p["cs"])
        player.pool_entries = [PlayerPoolEntry(position=i + 1, champion_id=cid) for i, cid in enumerate(p["pool"])]
        db.add(player)
        players[lane] = player
    db.flush()
    team = Team(owner_user_id=None, season_id=season.id, name=data["name"], logo=data["logo"],
                region=data["region"], fanbase="small", style1=data["style1"], style2=data["style2"],
                focus1=data["focus1"], focus2=data["focus2"], coach_id=coach.id)
    team.slots = [TeamRosterSlot(lane=lane, player_id=p.id) for lane, p in players.items()]
    db.add(team)
    db.flush()
    st = SeasonTeam(season_id=season.id, team_id=team.id, manager_user_id=None)
    db.add(st)
    return st


def _fill_with_cpu_teams(db: Session, season: Season, rng: random.Random) -> None:
    entered = season_teams(db, season)
    missing = _options(season)["team_count"] - len(entered)
    if missing <= 0:
        return
    champions = [c.to_engine() for c in db.scalars(select(Champion).where(Champion.enabled.is_(True)))]
    team_ids = [st.team_id for st in entered]
    names = set(db.scalars(select(func.lower(Player.name)).where(Player.season_id == season.id)))
    team_names = set(db.scalars(select(func.lower(Team.name)).where(Team.id.in_(team_ids)))) if team_ids else set()
    for _ in range(missing):
        data = player_generator.generate_team(_rules(season), _options(season)["cpu_strength"], champions, rng,
                                              names, team_names)
        names |= {p["name"].lower() for p in data["roster"].values()} | {data["coach"]["name"].lower()}
        team_names.add(data["name"].lower())
        _create_cpu_team(db, season, data)
    db.flush()


def start_season(db: Session, season: Season, user: User) -> None:
    """Fill the empty places with CPU teams, seed everyone at random and draw up the schedule."""
    _require_creator(season, user)
    if season.status != "SETUP":
        raise conflict("The season has already started.")
    if not any(st.manager_user_id is not None for st in season_teams(db, season)):
        raise conflict("Enter your team before starting the season.")
    rng = random.Random(secrets.randbits(64))
    _fill_with_cpu_teams(db, season, rng)
    entered = season_teams(db, season)
    rng.shuffle(entered)
    for i, st in enumerate(entered):
        st.seed = i + 1
    options = _options(season)
    season.status, season.current_round, season.started_at = "REGULAR", 1, utcnow()
    _open_round(season)
    if season.format == "SWISS":
        db.flush()
        _draw_swiss_round(db, season, 1)
        rounds = competition.swiss_rounds(options["swiss_wins"], options["swiss_losses"])
    else:
        schedule = competition.round_robin([st.id for st in entered], double=bool(options["rr_double"]))
        for r, pairs in enumerate(schedule):
            _add_round(db, season, "REGULAR", r + 1, pairs, options["regular_series"])
        rounds = len(schedule)
    db.commit()
    track("season_started", season_id=season.id, teams=len(entered), rounds=rounds, format=season.format)


def _add_round(db: Session, season: Season, stage: str, round_: int, pairs, series_format: str) -> None:
    for slot, (home, away) in enumerate(pairs):
        db.add(SeasonMatch(season_id=season.id, stage=stage, round=round_, slot=slot, home_team_id=home,
                           away_team_id=away, format=series_format))


def _swiss_records(db: Session, season: Season) -> dict[int, competition.SwissRecord]:
    options = _options(season)
    return competition.swiss_records({st.id: st.seed for st in season_teams(db, season)},
                                     _results(db, season, "SWISS"), options["swiss_wins"], options["swiss_losses"])


def _draw_swiss_round(db: Session, season: Season, round_: int) -> None:
    pairs = competition.swiss_pairings(_swiss_records(db, season))
    _add_round(db, season, "SWISS", round_, pairs, _options(season)["regular_series"])


def cancel_season(db: Session, season: Season, user: User) -> None:
    _require_creator(season, user)
    if season.status in FINISHED:
        raise conflict("The season is already over.")
    season.status, season.completed_at, season.round_deadline_at = "CANCELLED", utcnow(), None
    db.commit()


# ------------------------------------------------------------------ rounds
def _open_round(season: Season) -> None:
    """A round has opened: start its deadline, if the season has one."""
    hours = _options(season).get("round_deadline_hours") or 0
    playing = season.status in matches.PLAYING
    season.round_deadline_at = utcnow() + timedelta(hours=hours) if hours and playing else None


def _stage_rounds(db: Session, season: Season, stage: str) -> int:
    """How many rounds the stage has (Swiss: the most it can take)."""
    options = _options(season)
    if stage == "SWISS":
        return competition.swiss_rounds(options["swiss_wins"], options["swiss_losses"])
    if stage == "PLAYOFF":
        return competition.bracket_rounds(options.get("playoff_size") or 0)
    return db.scalar(select(func.max(SeasonMatch.round)).where(SeasonMatch.season_id == season.id,
                                                              SeasonMatch.stage == "REGULAR")) or 0


def _total_rounds(db: Session, season: Season) -> int:
    return _stage_rounds(db, season, matches.current_stage(season))


def _round_matches(db: Session, season: Season, round_: int, stage: str | None = None) -> list[SeasonMatch]:
    stage = stage or matches.current_stage(season)
    return list(db.scalars(select(SeasonMatch).where(SeasonMatch.season_id == season.id, SeasonMatch.stage == stage,
                                                     SeasonMatch.round == round_)
                           .order_by(SeasonMatch.slot, SeasonMatch.id)))


def advance_round(db: Session, season: Season, user: User, force: bool = False) -> Events:
    """Close the current round and open the next. Every CPU vs CPU match of the round is played now. A match a
    manager hasn't finished blocks the round, unless `force`: then the CPU plays the rest of it for them.
    After the last round the season ends and the top of the table is champion."""
    _require_creator(season, user)
    with matches.simulating(season.id):
        db.refresh(season)
        return _advance_round(db, season, force)


def _drafts_in_play(db: Session, season: Season) -> bool:
    """Whether a manager is in the middle of a game of this round right now."""
    ids = [m.id for m in _round_matches(db, season, season.current_round) if m.status != "COMPLETED"]
    if not ids:
        return False
    return db.scalar(select(Game.id).where(Game.season_match_id.in_(ids), Game.status.in_(IN_PLAY),
                                           or_(Game.blue_player_id.is_not(None), Game.red_player_id.is_not(None)))
                     .limit(1)) is not None


def process_deadlines(db: Session, now=None) -> Events:
    """Close every round whose deadline has passed, as a forced advance: the CPU plays whatever managers haven't.
    A game managers are drafting right then gets DEADLINE_GRACE to finish first. Run by the background loop."""
    now = now or utcnow()
    due = db.scalars(select(Season).where(Season.status.in_(matches.PLAYING), Season.round_deadline_at.is_not(None),
                                          Season.round_deadline_at <= now)).all()
    events: Events = []
    for season in due:
        if now < season.round_deadline_at + DEADLINE_GRACE and _drafts_in_play(db, season):
            continue
        try:
            with matches.simulating(season.id):
                db.refresh(season)
                if season.round_deadline_at is None or season.round_deadline_at > now:
                    continue                       # the round was closed meanwhile
                events += _advance_round(db, season, force=True)
                track("season_deadline_passed", season_id=season.id, round=season.current_round)
        except HTTPException:                      # busy simulating, or no longer in play: try again next time
            db.rollback()
    return events


def _advance_round(db: Session, season: Season, force: bool) -> Events:
    if season.status not in matches.PLAYING:
        raise conflict("The season isn't in progress.")
    pending = [m for m in _round_matches(db, season, season.current_round) if m.status != "COMPLETED"]
    waiting = [m for m in pending if matches.has_manager(db, m)]
    if waiting and not force:
        raise conflict(f"{len(waiting)} manager match{'es' if len(waiting) != 1 else ''} still to play this round. "
                       "Play or auto-sim them, or force the round on.")
    events: Events = []
    lookups = gs.CpuLookups(db) if pending else None
    for m in pending:
        events += matches.auto_play_match(db, season, m, lookups)
    db.flush()                       # the round's results, read back below
    stage = matches.current_stage(season)
    if stage == "REGULAR":
        _after_round_robin_round(db, season)
    elif stage == "SWISS":
        _after_swiss_round(db, season)
    else:
        _after_playoff_round(db, season)
    _open_round(season)
    db.commit()
    track("season_round_advanced", season_id=season.id, round=season.current_round, forced=bool(waiting))
    return events + [matches.season_event(season.id)]


def _after_round_robin_round(db: Session, season: Season) -> None:
    if season.current_round < _stage_rounds(db, season, "REGULAR"):
        season.current_round += 1
        return
    table = standings(db, season)
    size = _options(season).get("playoff_size") or 0
    if size:
        _start_playoffs(db, season, [row.team for row in table[:size]])
    else:
        _complete_season(db, season, table[0].team if table else None)


def _after_swiss_round(db: Session, season: Season) -> None:
    records = _swiss_records(db, season)
    for st in season_teams(db, season):
        st.eliminated = records[st.id].status == "ELIMINATED"
    if any(r.status is None for r in records.values()):
        season.current_round += 1
        _draw_swiss_round(db, season, season.current_round)
        return
    # the qualifiers are seeded by record (fewest losses), then game difference, then original seed
    qualified = sorted((r for r in records.values() if r.status == "QUALIFIED"),
                       key=lambda r: (r.losses, -r.game_diff, r.seed))
    _start_playoffs(db, season, [r.team for r in qualified])


def _playoff_format(season: Season, round_: int) -> str:
    options = _options(season)
    final = round_ == competition.bracket_rounds(options["playoff_size"])
    return options.get("final_series" if final else "playoff_series") or "BO3"


def _start_playoffs(db: Session, season: Season, seeded: list[int]) -> None:
    """Single elimination between `seeded` (best first): 1 v 8, 4 v 5, 2 v 7, 3 v 6, the better seed at home."""
    in_bracket = set(seeded)
    for st in season_teams(db, season):
        st.eliminated = st.id not in in_bracket
    season.status, season.current_round = "PLAYOFFS", 1
    _add_round(db, season, "PLAYOFF", 1, competition.bracket_first_round(seeded), _playoff_format(season, 1))
    track("season_playoffs_started", season_id=season.id, teams=len(seeded))


def _after_playoff_round(db: Session, season: Season) -> None:
    played = _round_matches(db, season, season.current_round, "PLAYOFF")
    for m in played:
        loser = m.away_team_id if m.winner_team_id == m.home_team_id else m.home_team_id
        db.get(SeasonTeam, loser).eliminated = True
    if len(played) == 1:
        _complete_season(db, season, played[0].winner_team_id)
        return
    season.current_round += 1
    # neighbouring matches feed the same next match; the winner from the upper one is at home
    pairs = [(played[i].winner_team_id, played[i + 1].winner_team_id) for i in range(0, len(played), 2)]
    _add_round(db, season, "PLAYOFF", season.current_round, pairs, _playoff_format(season, season.current_round))


def _complete_season(db: Session, season: Season, winner_team_id: int | None) -> None:
    season.winner_team_id = winner_team_id
    season.status, season.completed_at = "COMPLETED", utcnow()
    track("season_completed", season_id=season.id, winner=season.winner_team_id)


# ------------------------------------------------------------------- views
def _results(db: Session, season: Season, stage: str = "REGULAR") -> list[competition.Result]:
    rows = db.scalars(select(SeasonMatch).where(SeasonMatch.season_id == season.id, SeasonMatch.stage == stage,
                                                SeasonMatch.status == "COMPLETED")
                      .order_by(SeasonMatch.round, SeasonMatch.completed_at, SeasonMatch.id))
    return [competition.Result(m.home_team_id, m.away_team_id, m.home_score, m.away_score) for m in rows]


def standings(db: Session, season: Season) -> list[competition.StandingRow]:
    """The league table: the round robin, or the Swiss stage's records."""
    stage = "SWISS" if season.format == "SWISS" else "REGULAR"
    return competition.standings({st.id: st.seed for st in season_teams(db, season)}, _results(db, season, stage))


def _stage_label(stage: str) -> str:
    return {"REGULAR": "Regular season", "SWISS": "Swiss stage", "PLAYOFF": "Playoffs"}[stage]


def bracket_view(db: Session, season: Season, refs: dict[int, dict]) -> dict | None:
    """The playoff bracket: every round, with the matches drawn so far (later rounds stay empty until then)."""
    size = _options(season).get("playoff_size") or 0
    if not size:
        return None
    played = [m for m in _season_matches(db, season) if m.stage == "PLAYOFF"]
    rounds = []
    for r in range(1, competition.bracket_rounds(size) + 1):
        rounds.append({"round": r, "name": competition.bracket_round_name(r, size), "slots": size >> r,
                       "format": _playoff_format(season, r),
                       "matches": [_match_view(db, m, refs) for m in played if m.round == r]})
    return {"size": size, "rounds": rounds}


def _team_refs(db: Session, season: Season, viewer: User) -> dict[int, dict]:
    sts = season_teams(db, season)
    team_rows = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_([st.team_id for st in sts])))}
    user_ids = [st.manager_user_id for st in sts if st.manager_user_id]
    users = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    refs = {}
    for st in sts:
        t = team_rows.get(st.team_id)
        refs[st.id] = {"id": st.id, "team_id": st.team_id, "name": t.name if t else "?", "logo": t.logo if t else "",
                       "seed": st.seed, "is_cpu": st.manager_user_id is None, "is_you": st.manager_user_id == viewer.id,
                       "manager": {"id": st.manager_user_id, "username": users.get(st.manager_user_id)}
                       if st.manager_user_id else None}
    return refs


def _match_view(db: Session, m: SeasonMatch, refs: dict[int, dict]) -> dict:
    games = matches.match_games(db, m)
    winners = dict(db.execute(select(MatchResultRow.game_id, MatchResultRow.winner)
                              .where(MatchResultRow.game_id.in_([g.id for g in games]))).all()) if games else {}
    by_team = {ref["team_id"]: ref["id"] for ref in refs.values()}
    live = next((g for g in reversed(games) if g.status in gs.ACTIVE), None)
    return {
        "id": m.id, "stage": m.stage, "round": m.round, "slot": m.slot, "format": m.format, "status": m.status,
        "played_mode": m.played_mode, "home": refs.get(m.home_team_id), "away": refs.get(m.away_team_id),
        "home_score": m.home_score, "away_score": m.away_score, "winner_team_id": m.winner_team_id,
        "series_id": m.series_id, "live_game_id": live.id if live else None,
        "latest_game_id": games[-1].id if games else None,
        "games": [{"game_id": g.id, "game_number": g.game_number, "status": g.status,
                   "winner_team_id": by_team.get(g.blue_team_id if winners[g.id] == "BLUE" else g.red_team_id)
                   if g.id in winners else None} for g in games],
        "has_manager": any(r and not r["is_cpu"] for r in (refs.get(m.home_team_id), refs.get(m.away_team_id))),
        "auto_requested": {"home": m.home_auto_ready, "away": m.away_auto_ready},
        "yours": any(r and r["is_you"] for r in (refs.get(m.home_team_id), refs.get(m.away_team_id))),
        "completed_at": iso(m.completed_at),
    }


def _team_rating(db: Session, team_ids: list[int]) -> dict[int, int]:
    """Sum of the rostered players' stat totals, per team id."""
    rows = db.execute(select(TeamRosterSlot.team_id,
                             func.sum(Player.aggr + Player.aware + Player.pos + Player.dmg + Player.cs))
                      .join(Player, Player.id == TeamRosterSlot.player_id)
                      .where(TeamRosterSlot.team_id.in_(team_ids)).group_by(TeamRosterSlot.team_id))
    return {tid: int(total or 0) for tid, total in rows}


def season_summary(db: Session, season: Season, viewer: User) -> dict:
    sts = season_teams(db, season)
    mine = next((st for st in sts if st.manager_user_id == viewer.id), None)
    creator = db.get(User, season.created_by)
    options = _options(season)
    return {
        "id": season.id, "name": season.name, "code": season.code, "status": season.status,
        "roster_mode": season.roster_mode, "format": season.format,
        "team_count": options["team_count"], "teams_entered": len(sts),
        "managers": sum(st.manager_user_id is not None for st in sts), "human_slots": options["human_slots"],
        "current_round": season.current_round, "total_rounds": _total_rounds(db, season),
        "stage": matches.current_stage(season) if season.status in matches.PLAYING else None,
        "created_by": {"id": creator.id, "username": creator.username} if creator else None,
        "is_creator": season.created_by == viewer.id, "my_team_id": mine.id if mine else None,
        "winner_team_id": season.winner_team_id, "round_deadline_at": iso(season.round_deadline_at),
        "created_at": iso(season.created_at), "started_at": iso(season.started_at),
        "completed_at": iso(season.completed_at),
    }


def season_view(db: Session, season: Season, viewer: User) -> dict:
    """The season hub: settings, teams, standings, this round's matches and your next match."""
    refs = _team_refs(db, season, viewer)
    ratings = _team_rating(db, [r["team_id"] for r in refs.values()])
    table = standings(db, season)
    playing = season.status in matches.PLAYING
    stage = matches.current_stage(season)
    current = [_match_view(db, m, refs) for m in _round_matches(db, season, season.current_round)] if playing else []
    records = _swiss_records(db, season) if season.format == "SWISS" and season.status != "SETUP" else {}
    eliminated = {st.id for st in season_teams(db, season) if st.eliminated}
    summary = season_summary(db, season, viewer)
    my_match = next((m for m in current if m["yours"]), None)
    waiting = sum(1 for m in current if m["has_manager"] and m["status"] != "COMPLETED")
    teams_out = [{**ref, "rating": ratings.get(ref["team_id"], 0)} for ref in refs.values()]
    return {
        **summary,
        "rules": _rules(season), "options": _options(season),
        "ruleset_name": lobby_rules.ruleset(_rules(season).get("ruleset"))["name"],
        "teams": teams_out,
        "standings": [{**row.to_dict(), "team": refs.get(row.team),
                       "swiss_status": records[row.team].status if row.team in records else None,
                       "eliminated": row.team in eliminated} for row in table],
        "stage": stage if playing else None,
        "stage_label": _stage_label(stage),
        "bracket": bracket_view(db, season, refs),
        "my_team_eliminated": summary["my_team_id"] in eliminated,
        "round_matches": current,
        "my_match": my_match,
        "waiting_on_managers": waiting,
        "can_start": season.status == "SETUP" and season.created_by == viewer.id
        and any(not r["is_cpu"] for r in refs.values()),
        "can_manage": season.created_by == viewer.id and season.status not in FINISHED,
        "can_advance": playing and season.created_by == viewer.id,
        "champion": refs.get(season.winner_team_id) if season.winner_team_id else None,
    }


def schedule_view(db: Session, season: Season, viewer: User) -> dict:
    refs = _team_refs(db, season, viewer)
    order = {"REGULAR": 0, "SWISS": 0, "PLAYOFF": 1}
    rounds: dict[tuple[str, int], list[dict]] = {}
    for m in _season_matches(db, season):
        rounds.setdefault((m.stage, m.round), []).append(_match_view(db, m, refs))
    size = _options(season).get("playoff_size") or 0
    out = []
    for (stage, r), ms in sorted(rounds.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        name = competition.bracket_round_name(r, size) if stage == "PLAYOFF" else f"Round {r}"
        out.append({"stage": stage, "stage_label": _stage_label(stage), "round": r, "name": name,
                    "current": season.status in matches.PLAYING and stage == matches.current_stage(season)
                    and r == season.current_round, "matches": ms})
    return {"current_round": season.current_round, "stage": matches.current_stage(season), "rounds": out}


def _player_stats(db: Session, season: Season, team: Team) -> dict[int, dict]:
    """Season totals for each rostered player, from every finished game the team played."""
    roster_ids = {s.player_id for s in team.slots}
    stats = {pid: {"games": 0, "kills": 0, "deaths": 0, "assists": 0, "cs": 0, "gold": 0, "damage_dealt": 0,
                   "mvps": 0} for pid in roster_ids}
    rows = db.execute(select(MatchResultRow).join(Game, Game.id == MatchResultRow.game_id)
                      .join(SeasonMatch, SeasonMatch.id == Game.season_match_id)
                      .where(SeasonMatch.season_id == season.id, Game.status == "COMPLETED",
                             or_(Game.blue_team_id == team.id, Game.red_team_id == team.id))).scalars()
    for row in rows:
        for p in (row.data or {}).get("players", []):
            s = stats.get(p.get("player_id"))
            if s is None:
                continue
            s["games"] += 1
            for k in ("kills", "deaths", "assists", "cs", "gold", "damage_dealt"):
                s[k] += int(p.get(k) or 0)
            s["mvps"] += row.mvp_player_id == p.get("player_id")
    for s in stats.values():
        s["kda"] = round((s["kills"] + s["assists"]) / max(1, s["deaths"]), 2)
    return stats


def team_detail(db: Session, season: Season, season_team_id: int, viewer: User) -> dict:
    st = db.get(SeasonTeam, season_team_id)
    if st is None or st.season_id != season.id:
        raise not_found("Team not found.")
    team = db.get(Team, st.team_id)
    refs = _team_refs(db, season, viewer)
    view = teams.team_view(db, team)
    hidden = (_rules(season).get("hide_player_data") and st.manager_user_id != viewer.id
              and season.status != "COMPLETED")
    if hidden:
        view = gs._mask_team(view)
    row = next((r for r in standings(db, season) if r.team == st.id), None)
    fixtures = [_match_view(db, m, refs) for m in _season_matches(db, season)
                if st.id in (m.home_team_id, m.away_team_id)]
    return {"team": refs[st.id], "view": view, "record": row.to_dict() if row else None, "matches": fixtures,
            "player_stats": {} if hidden else {str(k): v for k, v in _player_stats(db, season, team).items()}}

"""Idempotent import of the seed CSVs into the database as default (system) content.

System rows have owner_user_id = NULL: visible to everyone, editable by nobody.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.champion_sync import log_report, sync_champions
from app.data.loader import SeedData, SeedDataError, load_seed_data
from app.data.matchup_seed import seed_matchups
from app.models import Champion, Coach, Player, PlayerPoolEntry, Team, TeamRosterSlot

log = logging.getLogger(__name__)


def seed_database(db: Session, data: SeedData | None = None) -> None:
    """Run at every backend start: sync champions with the CSV, and create the win rate matrices and default
    teams once."""
    if data is None:
        try:
            data = load_seed_data()
        except (SeedDataError, ValueError, KeyError):
            # a broken CSV edit must not take down a running game; keep what is already in the database
            if db.scalar(select(func.count()).select_from(Champion)):
                log.exception("seed data could not be loaded; keeping the existing champions")
                return
            raise
    for warning in data.warnings:
        log.warning("seed data: %s", warning)

    log_report(sync_champions(db, data))
    seed_matchups(db)

    if db.scalar(select(func.count()).select_from(Team).where(Team.owner_user_id.is_(None))):
        return

    coach_ids: dict[int, int] = {}
    for c in data.coaches:
        row = Coach(owner_user_id=None, name=c["name"], draft=c["draft"], synergy=c["synergy"])
        db.add(row)
        db.flush()
        coach_ids[c["id"]] = row.id

    player_ids: dict[int, int] = {}
    for p in data.players:
        row = Player(owner_user_id=None, name=p["name"], role=p["role"], secondary_role=p.get("secondary_role"), age=p["age"], region=p["region"],
                     aggr=p["aggr"], aware=p["aware"], pos=p["pos"], dmg=p["dmg"], cs=p["cs"])
        row.pool_entries = [PlayerPoolEntry(position=i + 1, champion_id=cid)
                            for i, cid in enumerate(data.pools[p["id"]])]
        db.add(row)
        db.flush()
        player_ids[p["id"]] = row.id

    for t in data.teams:
        row = Team(owner_user_id=None, name=t["name"], logo=t["logo"], region=t["region"], fanbase=t["fanbase"],
                   style1=t["style1"], style2=t["style2"], focus1=t["focus1"], focus2=t["focus2"],
                   coach_id=coach_ids.get(t.get("coach_id")))
        roster = data.rosters.get(t["id"])
        if roster:
            row.slots = [TeamRosterSlot(lane=lane, player_id=player_ids[pid]) for lane, pid in roster.items()]
        db.add(row)
    db.commit()

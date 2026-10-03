"""Sync champions from the seed CSVs into the database.

    python -m scripts.sync_champions             # apply
    python -m scripts.sync_champions --dry-run   # show what would change, change nothing

The backend runs the same sync on every start, so this is only needed to apply CSV edits without restarting.
New champions: add a row to backend/app/data/seed/Champions.csv (use the next free Id) and, optionally, a
matching row in ChampionStatistics.csv for win/pick rate.
"""
from __future__ import annotations

import sys

from app.core.database import Base, SessionLocal, engine
from app.data.champion_sync import sync_champions
from app.data.loader import SeedDataError, load_seed_data


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    Base.metadata.create_all(engine)
    try:
        data = load_seed_data()
    except SeedDataError as exc:
        print(f"Cannot read the champion CSVs: {exc}")
        return 1
    with SessionLocal() as db:
        report = sync_champions(db, data, commit=not dry_run)
        if dry_run:
            db.rollback()
    print(("[dry run] " if dry_run else "") + report.summary())
    for name in report.added:
        print(f"  + {name}")
    for name, columns in report.updated.items():
        print(f"  ~ {name}: {', '.join(columns)}")
    for change in report.renumbered:
        print(f"  # renumbered {change}")
    for reason in report.skipped:
        print(f"  ! skipped {reason}")
    for name in report.not_in_csv:
        print(f"  ? {name} is in the database but not in the CSV (kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

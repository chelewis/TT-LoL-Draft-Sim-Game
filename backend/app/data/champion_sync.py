"""Keep the `champions` table in step with the seed CSVs.

Runs on every backend start (and on demand via `python -m scripts.sync_champions`):

* champions in the CSV that are not in the database are **added**;
* champions that exist in both are **updated** when any value differs (stats, class, win rate, name...);
* a champion whose **id changed in the CSV** (same name, new id) is renumbered in the database, but only when
  nothing refers to the old id (no player pool, draft or lineup uses it); otherwise it is skipped with an
  explanation, because changing an id that is in use would corrupt existing data;
* champions only in the database are **left alone** (nothing is ever deleted, so players' pools and past
  games keep working), and the `enabled` flag is never changed by a sync.

The CSV is the source of truth for champion data; edit the CSV, not the table.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.data.loader import SeedData
from app.data.matchup_seed import attach_champion, detach_champion
from app.game.models import Champion as EngineChampion
from app.models import Champion, DraftActionRow, PlayerPoolEntry, TeamLineup

log = logging.getLogger(__name__)

# database column <- engine champion attribute
FIELDS = {
    "name": "name", "champ_class": "champ_class", "style": "style", "difficulty": "difficulty",
    "damage_type": "damage_type", "damage": "damage", "sturdiness": "sturdiness", "crowd_control": "cc",
    "mobility": "mobility", "utility": "utility", "win_rate": "win_rate", "pick_rate": "pick_rate",
}


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: dict[str, list[str]] = field(default_factory=dict)     # champion name -> changed column names
    renumbered: list[str] = field(default_factory=list)              # "Name: old id -> new id"
    unchanged: int = 0
    not_in_csv: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)                 # reasons a CSV row was not applied

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.renumbered)

    def summary(self) -> str:
        return (f"champions: {len(self.added)} added, {len(self.updated)} updated, {self.unchanged} unchanged"
                + (f", {len(self.renumbered)} renumbered" if self.renumbered else "")
                + (f", {len(self.skipped)} skipped" if self.skipped else "")
                + (f", {len(self.not_in_csv)} in the database but not in the CSV (kept)" if self.not_in_csv else ""))


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def sync_champions(db: Session, data: SeedData, commit: bool = True) -> SyncReport:
    """Upsert champions from `data` into the database. With commit=False the caller decides (dry runs roll back)."""
    report = SyncReport()
    existing = {c.id: c for c in db.scalars(select(Champion))}
    if _renumber(db, data, existing, report):
        db.expire_all()
        existing = {c.id: c for c in db.scalars(select(Champion))}
    names_in_use = {c.name.lower(): c.id for c in existing.values()}
    csv_ids = set()

    for champ in data.champions:
        csv_ids.add(champ.id)
        row = existing.get(champ.id)
        clash = names_in_use.get(champ.name.lower())
        if clash is not None and clash != champ.id:
            report.skipped.append(f"{champ.name!r} (id {champ.id}): the name is already used by id {clash}")
            continue
        if row is None:
            db.add(_new_row(champ))
            names_in_use[champ.name.lower()] = champ.id
            report.added.append(champ.name)
            continue
        changed = [column for column, attr in FIELDS.items() if not _same(getattr(row, column), getattr(champ, attr))]
        if not changed:
            report.unchanged += 1
            continue
        old_name = row.name
        for column in changed:
            setattr(row, column, getattr(champ, FIELDS[column]))
        names_in_use.pop(old_name.lower(), None)
        names_in_use[row.name.lower()] = row.id
        report.updated[champ.name] = changed

    report.not_in_csv = sorted(c.name for cid, c in existing.items() if cid not in csv_ids)
    if commit:
        db.commit()
    else:
        db.flush()
    return report


def _references(db: Session, champion_id: int) -> list[str]:
    """What still points at a champion id (empty when it is safe to change)."""
    found = []
    for label, model in (("player champion pools", PlayerPoolEntry), ("drafts", DraftActionRow),
                         ("lineups", TeamLineup)):
        count = db.scalar(select(func.count()).select_from(model).where(model.champion_id == champion_id))
        if count:
            found.append(f"{count} in {label}")
    return found


def _renumber(db: Session, data: SeedData, existing: dict[int, Champion], report: SyncReport) -> bool:
    """Move champions whose id changed in the CSV to their new id, when nothing refers to the old one."""
    by_name = {c.name.lower(): c for c in existing.values()}
    csv_ids = {c.id for c in data.champions}
    moved = False
    for champ in data.champions:
        row = by_name.get(champ.name.lower())
        if row is None or row.id == champ.id or champ.id in existing or row.id in csv_ids:
            continue        # not a plain renumber (the old or new id is taken by something else)
        refs = _references(db, row.id)
        if refs:
            report.skipped.append(
                f"{champ.name!r}: the CSV changed its id from {row.id} to {champ.id}, but id {row.id} is in use "
                f"({', '.join(refs)}). Keep id {row.id} in the CSV")
            continue
        old_id = row.id
        matchups = detach_champion(db, old_id)      # win rate matrix cells follow the champion to its new id
        db.execute(update(Champion).where(Champion.id == old_id).values(id=champ.id))
        attach_champion(db, matchups, old_id, champ.id)
        report.renumbered.append(f"{champ.name}: {old_id} -> {champ.id}")
        moved = True
    if moved:
        db.flush()
    return moved


def _new_row(champ: EngineChampion) -> Champion:
    return Champion(id=champ.id, name=champ.name, champ_class=champ.champ_class, style=champ.style,
                    difficulty=champ.difficulty, damage_type=champ.damage_type, damage=champ.damage,
                    sturdiness=champ.sturdiness, crowd_control=champ.cc, mobility=champ.mobility,
                    utility=champ.utility, win_rate=champ.win_rate, pick_rate=champ.pick_rate, enabled=True)


def log_report(report: SyncReport) -> None:
    log.info("seed sync: %s", report.summary())
    for name in report.added:
        log.info("seed sync: added champion %s", name)
    for name, columns in report.updated.items():
        log.info("seed sync: updated champion %s (%s)", name, ", ".join(columns))
    for change in report.renumbered:
        log.info("seed sync: renumbered champion %s", change)
    for reason in report.skipped:
        log.warning("seed sync: skipped %s", reason)

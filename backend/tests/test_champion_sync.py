"""Champion sync: CSV -> database, on demand and at every backend start."""
import dataclasses
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.data import seed_db
from app.data.champion_sync import sync_champions
from app.data.loader import SEED_DIR, load_seed_data
from app.game.models import Champion as EngineChampion
from app.main import app
from app.models import Champion, ChampionMatchup
from scripts import sync_champions as script


# counts come from the CSV so adding champions to it never breaks these tests
_SEED = load_seed_data()
TOTAL = len(_SEED.champions)
NEW_ID = max(c.id for c in _SEED.champions) + 1000     # clear of any placeholder ids in the CSV


def new_champion(cid=NEW_ID, name="Testchamp", **kw):
    values = dict(id=cid, name=name, champ_class="Mage", style=5, difficulty=2, damage_type="M", damage=3,
                  sturdiness=1, cc=2, mobility=2, utility=1, win_rate=51.5, pick_rate=4.0)
    values.update(kw)
    return EngineChampion(**values)


def with_champions(data, *extra, replace=None):
    champs = [replace.get(c.id, c) if replace else c for c in data.champions] + list(extra)
    return dataclasses.replace(data, champions=champs)


@pytest.fixture
def db(client):
    with SessionLocal() as session:
        yield session


def test_already_synced_database_reports_no_changes(db):
    report = sync_champions(db, load_seed_data())
    assert not report.changed and report.unchanged == TOTAL and report.not_in_csv == [] and report.skipped == []


def test_new_champion_is_added(db):
    data = with_champions(load_seed_data(), new_champion())
    report = sync_champions(db, data)
    assert report.added == ["Testchamp"] and not report.updated
    row = db.get(Champion, NEW_ID)
    assert row.name == "Testchamp" and row.crowd_control == 2 and row.win_rate == 51.5 and row.enabled is True
    assert db.query(Champion).count() == TOTAL + 1


def test_running_twice_changes_nothing_the_second_time(db):
    data = with_champions(load_seed_data(), new_champion())
    sync_champions(db, data)
    again = sync_champions(db, data)
    assert not again.changed and again.unchanged == TOTAL + 1


def test_changed_values_are_updated_and_reported(db):
    data = load_seed_data()
    ahri = next(c for c in data.champions if c.name == "Ahri")
    edited = dataclasses.replace(ahri, damage=1, win_rate=60.25, difficulty=3)
    report = sync_champions(db, with_champions(data, replace={ahri.id: edited}))
    assert report.updated == {"Ahri": ["difficulty", "damage", "win_rate"]} and not report.added
    row = db.get(Champion, ahri.id)
    assert (row.damage, row.win_rate, row.difficulty) == (1, 60.25, 3)


def test_changed_range_and_waveclear_are_updated(db):
    data = load_seed_data()
    ahri = next(c for c in data.champions if c.name == "Ahri")
    edited = dataclasses.replace(ahri, attack_range=1, waveclear=1)
    report = sync_champions(db, with_champions(data, replace={ahri.id: edited}))
    assert report.updated == {"Ahri": ["attack_range", "waveclear"]}
    row = db.get(Champion, ahri.id)
    assert (row.attack_range, row.waveclear) == (1, 1)
    assert row.to_engine().to_dict()["range"] == 1


def test_champions_missing_from_the_csv_are_kept_and_reported(db):
    data = load_seed_data()
    trimmed = dataclasses.replace(data, champions=data.champions[:-1])
    report = sync_champions(db, trimmed)
    assert report.not_in_csv == [data.champions[-1].name]
    assert db.get(Champion, data.champions[-1].id) is not None          # never deleted


def test_enabled_flag_is_not_overwritten(db):
    data = load_seed_data()
    db.get(Champion, 1).enabled = False
    db.commit()
    edited = dataclasses.replace(next(c for c in data.champions if c.id == 1), win_rate=70.0)
    sync_champions(db, with_champions(data, replace={1: edited}))
    row = db.get(Champion, 1)
    assert row.enabled is False and row.win_rate == 70.0


def test_name_clash_with_another_id_is_skipped_not_applied(db):
    data = load_seed_data()
    clash = new_champion(cid=NEW_ID + 1, name=data.champions[0].name.upper())          # same name as id 1
    report = sync_champions(db, with_champions(data, clash))
    assert report.skipped and "already used by id" in report.skipped[0]
    assert db.get(Champion, NEW_ID + 1) is None


def test_dry_run_changes_nothing(db):
    data = with_champions(load_seed_data(), new_champion())
    report = sync_champions(db, data, commit=False)
    assert report.added == ["Testchamp"]
    db.rollback()
    assert db.get(Champion, NEW_ID) is None


# ------------------------------------------------------------------ from real CSV files
def copy_seed(tmp_path: Path) -> Path:
    target = tmp_path / "seed"
    shutil.copytree(SEED_DIR, target)
    return target


def test_csv_row_becomes_a_champion_with_its_statistics(db, tmp_path):
    seed = copy_seed(tmp_path)
    with open(seed / "Champions.csv", "a", encoding="utf-8", newline="") as fh:
        fh.write(f"\n{NEW_ID},Zephyra,Mage-Support,6,2,M,3,1,2,2,3")
    with open(seed / "ChampionStatistics.csv", "a", encoding="utf-8", newline="") as fh:
        fh.write("\nZephyra,52.3,7.1")
    report = sync_champions(db, load_seed_data(seed))
    assert report.added == ["Zephyra"]
    row = db.get(Champion, NEW_ID)
    assert (row.champ_class, row.utility, row.win_rate, row.pick_rate) == ("Mage-Support", 3, 52.3, 7.1)


# --------------------------------------------------------------- every backend start
def test_backend_start_adds_new_champions_and_updates_stats(client, monkeypatch):
    data = load_seed_data()
    ahri = next(c for c in data.champions if c.name == "Ahri")
    edited = dataclasses.replace(data, champions=[
        dataclasses.replace(c, win_rate=44.0) if c.id == ahri.id else c for c in data.champions] + [new_champion()])
    monkeypatch.setattr(seed_db, "load_seed_data", lambda: edited)
    with TestClient(app):                                 # entering the client runs the startup sync
        pass
    with SessionLocal() as session:
        assert session.get(Champion, NEW_ID).name == "Testchamp"
        assert session.get(Champion, ahri.id).win_rate == 44.0


def test_new_champion_is_usable_in_the_game_after_a_restart(client, alice, monkeypatch):
    data = with_champions(load_seed_data(), new_champion())
    monkeypatch.setattr(seed_db, "load_seed_data", lambda: data)
    with TestClient(app):
        pass
    champs = {c["name"]: c["id"] for c in alice.get("/champions").json()}
    assert champs["Testchamp"] == NEW_ID
    pool = [NEW_ID, 1, 2, 3, 4]
    res = alice.post("/players", {"name": "P", "role": "MID", "aggr": 5, "aware": 5, "pos": 5, "dmg": 5, "cs": 5,
                                  "pool": pool})
    assert res.status_code == 201 and res.json()["pool"] == pool


def test_a_broken_csv_does_not_stop_the_backend_starting(client, monkeypatch):
    def broken():
        raise ValueError("bad number in Champions.csv")

    monkeypatch.setattr(seed_db, "load_seed_data", broken)
    with TestClient(app):                                   # must start, keeping the champions already stored
        pass
    with SessionLocal() as session:
        assert session.query(Champion).count() == TOTAL


def test_script_dry_run_and_apply(client, monkeypatch, capsys):
    data = with_champions(load_seed_data(), new_champion())
    monkeypatch.setattr(script, "load_seed_data", lambda: data)
    assert script.main(["--dry-run"]) == 0
    assert "[dry run] champions: 1 added" in capsys.readouterr().out
    with SessionLocal() as session:
        assert session.get(Champion, NEW_ID) is None
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert "1 added" in out and "+ Testchamp" in out
    with SessionLocal() as session:
        assert session.get(Champion, NEW_ID) is not None


# ----------------------------------------------------------- an id changed in the CSV (renumbering)
def renumbered(data, name, new_id):
    return dataclasses.replace(data, champions=[
        dataclasses.replace(c, id=new_id) if c.name == name else c for c in data.champions])


def test_changed_id_is_moved_when_nothing_uses_it(db):
    data = load_seed_data()
    senna = next(c for c in data.champions if c.name == "Senna")
    report = sync_champions(db, renumbered(data, "Senna", NEW_ID + 40))
    assert report.renumbered == [f"Senna: {senna.id} -> {NEW_ID + 40}"] and report.skipped == []
    assert db.get(Champion, senna.id) is None
    assert db.get(Champion, NEW_ID + 40).name == "Senna"
    assert db.query(Champion).count() == TOTAL                  # moved, not duplicated
    again = sync_champions(db, renumbered(data, "Senna", NEW_ID + 40))
    assert not again.changed


def test_win_rate_matrix_cells_follow_a_renumbered_champion(db):
    data = load_seed_data()
    senna = next(c for c in data.champions if c.name == "Senna")
    other = next(c for c in data.champions if c.id > senna.id)
    cell = db.query(ChampionMatchup).filter_by(kind="enemy", champion_a_id=senna.id, champion_b_id=other.id).one()
    cell.win_rate, cell.games, cell.wins = 60.0, 10, 6
    db.commit()
    total = db.query(ChampionMatchup).filter_by(kind="enemy").count()
    sync_champions(db, renumbered(data, "Senna", NEW_ID + 40))
    moved = db.query(ChampionMatchup).filter_by(kind="enemy", champion_a_id=other.id, champion_b_id=NEW_ID + 40).one()
    assert (moved.win_rate, moved.wins) == (40.0, 4)                 # now from the other champion's side
    assert db.query(ChampionMatchup).filter_by(kind="enemy").count() == total
    assert db.query(ChampionMatchup).filter_by(champion_a_id=senna.id).count() == 0
    assert db.query(ChampionMatchup).filter_by(kind="ally", champion_b_id=NEW_ID + 40).count() > 0


def test_changed_id_is_refused_when_players_use_it(db, alice):
    data = load_seed_data()
    senna = next(c for c in data.champions if c.name == "Senna")
    alice.post("/players", {"name": "P", "role": "BOT", "aggr": 5, "aware": 5, "pos": 5, "dmg": 5, "cs": 5,
                            "pool": [senna.id, 1, 2, 3, 4]})
    report = sync_champions(db, renumbered(data, "Senna", NEW_ID + 40))
    assert not report.renumbered
    assert report.skipped and "is in use" in report.skipped[0] and f"Keep id {senna.id}" in report.skipped[0]
    assert db.get(Champion, senna.id).name == "Senna"           # untouched


def test_swapped_ids_are_not_treated_as_renumbering(db):
    data = load_seed_data()
    a, b = data.champions[0], data.champions[1]
    swapped = dataclasses.replace(data, champions=[dataclasses.replace(a, id=b.id), dataclasses.replace(b, id=a.id)]
                                  + data.champions[2:])
    report = sync_champions(db, swapped)
    assert not report.renumbered                                # ambiguous, so left alone
    assert db.get(Champion, a.id).name == a.name

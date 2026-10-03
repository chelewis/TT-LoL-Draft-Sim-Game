"""Placeholder champions: a CSV row with only Id and Name reserves the champion without adding it to the game."""
import shutil

import pytest

from app.core.database import SessionLocal
from app.data.champion_sync import sync_champions
from app.data.loader import SEED_DIR, SeedDataError, load_seed_data
from app.models import Champion

BLANK = "," * 9          # the nine empty columns after Id and Name


@pytest.fixture
def seed(tmp_path):
    target = tmp_path / "seed"
    shutil.copytree(SEED_DIR, target)
    return target


def append(path, text):
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(text)


def next_id():
    return max(c.id for c in load_seed_data().champions) + 100


def test_placeholder_row_is_skipped_with_a_warning_not_an_error(seed):
    before = len(load_seed_data(seed).champions)
    pid = next_id()
    append(seed / "Champions.csv", f"\n{pid},Placeholdia{BLANK}\n")
    data = load_seed_data(seed)
    assert len(data.champions) == before                      # not part of the game yet
    assert any("Placeholdia" in w and "only Id and Name" in w for w in data.warnings)


def test_filling_in_the_row_later_makes_it_a_real_champion(seed):
    pid = next_id()
    append(seed / "Champions.csv", f"\n{pid},Placeholdia{BLANK}\n")
    before = len(load_seed_data(seed).champions)
    text = (seed / "Champions.csv").read_text(encoding="utf-8")
    (seed / "Champions.csv").write_text(
        text.replace(f"{pid},Placeholdia{BLANK}", f"{pid},Placeholdia,Mage,5,2,M,3,1,1,1,1"), encoding="utf-8")
    data = load_seed_data(seed)
    assert len(data.champions) == before + 1
    assert next(c for c in data.champions if c.id == pid).damage == 3


def test_half_filled_row_is_still_an_error_that_says_what_is_missing(seed):
    pid = next_id()
    append(seed / "Champions.csv", f"\n{pid},Halfway,Mage,,,,,,,,\n")
    with pytest.raises(SeedDataError, match=r"Champions.csv line \d+ \('Halfway'\)"):
        load_seed_data(seed)


def test_placeholder_needs_an_id_and_cannot_reuse_one(seed):
    pid = next_id()
    append(seed / "Champions.csv", f"\n,NoId{BLANK}\n")
    with pytest.raises(SeedDataError, match="placeholder rows still need a numeric Id"):
        load_seed_data(seed)
    seed2 = seed.parent / "seed2"
    shutil.copytree(SEED_DIR, seed2)
    append(seed2 / "Champions.csv", f"\n{pid},One{BLANK}\n{pid},Two{BLANK}\n")
    with pytest.raises(SeedDataError, match="already used by the placeholder 'One'"):
        load_seed_data(seed2)
    seed3 = seed.parent / "seed3"
    shutil.copytree(SEED_DIR, seed3)
    first = load_seed_data(seed3).champions[0]
    append(seed3 / "Champions.csv", f"\n{first.id},Clash{BLANK}\n")
    with pytest.raises(SeedDataError, match="and the placeholder 'Clash'"):
        load_seed_data(seed3)


def test_sync_ignores_placeholders(client, seed):
    append(seed / "Champions.csv", f"\n{next_id()},Placeholdia{BLANK}\n")
    with SessionLocal() as db:
        total = db.query(Champion).count()
        report = sync_champions(db, load_seed_data(seed))
        assert not report.added and db.query(Champion).count() == total


def test_the_shipped_csv_placeholders_are_for_champions_that_have_statistics():
    """The reserved names (Akshan, Zeri, ...) come from ChampionStatistics.csv and are not in the game until filled in."""
    data = load_seed_data()
    reserved = [w for w in data.warnings if "only Id and Name" in w]
    for w in reserved:
        assert "not in the game yet" in w

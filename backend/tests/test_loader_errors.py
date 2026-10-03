"""Hand-edited CSVs: stray blank lines are tolerated and real mistakes get a clear, located error."""
import shutil

import pytest

from app.data.loader import SEED_DIR, SeedDataError, load_seed_data


@pytest.fixture
def seed(tmp_path):
    target = tmp_path / "seed"
    shutil.copytree(SEED_DIR, target)
    return target


def append(path, text):
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(text)


def test_blank_and_whitespace_only_lines_are_ignored(seed):
    before = len(load_seed_data(seed).champions)
    append(seed / "Champions.csv", "\n\n    \n,,,,,,,,,,\n")        # what an editor leaves behind
    append(seed / "ChampionStatistics.csv", "\n   \n")
    assert len(load_seed_data(seed).champions) == before


def test_blank_id_names_the_file_line_and_champion(seed):
    append(seed / "Champions.csv", "\n,Nobody,Mage,5,2,M,3,1,1,1,1")
    with pytest.raises(SeedDataError, match=r"Champions.csv line \d+ \('Nobody'\).*blank or not a number"):
        load_seed_data(seed)


def test_bad_damage_type_is_reported(seed):
    append(seed / "Champions.csv", "\n900,Oddball,Mage,5,2,X,3,1,1,1,1")
    with pytest.raises(SeedDataError, match="DamageType must be P, M or PM"):
        load_seed_data(seed)


def test_missing_name_is_reported(seed):
    append(seed / "Champions.csv", "\n901,,Mage,5,2,M,3,1,1,1,1")
    with pytest.raises(SeedDataError, match="Name is empty"):
        load_seed_data(seed)


def test_duplicate_ids_say_which_champions_clash(seed):
    append(seed / "Champions.csv", "\n1,Imposter,Mage,5,2,M,3,1,1,1,1")
    with pytest.raises(SeedDataError, match=r"id 1 is used by both 'Aatrox' and 'Imposter'"):
        load_seed_data(seed)


def test_bad_statistics_number_is_reported(seed):
    append(seed / "ChampionStatistics.csv", "\nSenna,fifty,3.0")
    with pytest.raises(SeedDataError, match=r"ChampionStatistics.csv line \d+ \('Senna'\)"):
        load_seed_data(seed)


def test_duplicate_statistics_rows_are_warned_about(seed):
    append(seed / "ChampionStatistics.csv", "\nAhri,40.0,1.0")
    data = load_seed_data(seed)
    assert any("two rows for 'Ahri'" in w for w in data.warnings)
    assert next(c for c in data.champions if c.name == "Ahri").win_rate == 40.0     # the later row wins

from app.data.loader import load_seed_data


def test_seed_counts(seed):
    assert len(seed.champions) >= 155
    assert len(seed.players) == 12
    assert set(seed.rosters) == {1, 2}
    assert len(seed.teams) == 10


def test_champion_ids_unique_and_class_normalised(seed):
    assert len({c.id for c in seed.champions}) == len(seed.champions)
    assert not any("Assasin" in c.champ_class for c in seed.champions)
    assert any("Assassin" in c.champ_class for c in seed.champions)


def test_every_champion_has_win_rate(seed):
    assert all(0 < c.win_rate < 100 for c in seed.champions)


def test_missing_data_is_reported_not_fatal(tmp_path):
    """A blank attribute and a missing statistics row load with defaults and are reported."""
    import shutil
    from app.data.loader import SEED_DIR
    seed_copy = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed_copy)
    text = (seed_copy / "Champions.csv").read_text(encoding="utf-8")
    lines = text.splitlines()
    cells = lines[1].split(",")
    cells[lines[0].split(",").index("Utility")] = ""                # blank Utility on the first champion
    lines[1] = ",".join(cells)
    lines.append("999,Brandnew,Mage,5,2,M,3,1,1,1,1,2,3")         # no ChampionStatistics.csv row
    (seed_copy / "Champions.csv").write_text(chr(10).join(lines), encoding="utf-8")
    data = load_seed_data(seed_copy)
    assert any("has no Utility" in w for w in data.warnings)
    assert any("No statistics row" in w and "Brandnew" in w for w in data.warnings)
    brandnew = next(c for c in data.champions if c.name == "Brandnew")
    assert brandnew.win_rate == 50.0
    assert any("No scaling row" in w and "Brandnew" in w for w in data.warnings)
    assert brandnew.scaling == 2
    assert (brandnew.attack_range, brandnew.waveclear) == (2, 3)


def test_range_and_waveclear_are_loaded(seed):
    by_name = {c.name: (c.attack_range, c.waveclear) for c in seed.champions}
    assert by_name["Darius"][0] == 1 and by_name["Xerath"] == (3, 3)
    assert all(c.attack_range in (1, 2, 3) and c.waveclear in (1, 2, 3) for c in seed.champions)


def test_every_champion_has_range_and_waveclear():
    """A blank Range or Waveclear cell would silently fall back to the default."""
    warnings = [w for w in load_seed_data().warnings if "Range" in w or "Waveclear" in w]
    assert not warnings, warnings


def test_bad_range_value_is_an_error(tmp_path):
    import shutil
    import pytest
    from app.data.loader import SEED_DIR, SeedDataError
    seed_copy = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed_copy)
    path = seed_copy / "Champions.csv"
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n999,Brandnew,Mage,5,2,M,3,1,1,1,1,4,2\n",
                    encoding="utf-8")
    with pytest.raises(SeedDataError, match="Brandnew.*Range must be 1, 2 or 3"):
        load_seed_data(seed_copy)


def test_bad_scaling_value_is_an_error(tmp_path):
    import shutil
    import pytest
    from app.data.loader import SEED_DIR, SeedDataError
    seed_copy = tmp_path / "seed"
    shutil.copytree(SEED_DIR, seed_copy)
    path = seed_copy / "champion_scaling.csv"
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\nBrandnew,4\n", encoding="utf-8")
    with pytest.raises(SeedDataError, match="scaling must be 1, 2 or 3"):
        load_seed_data(seed_copy)


def test_every_champion_has_a_scaling_row():
    """A champion without a champion_scaling.csv row would silently be treated as neutral (2)."""
    warnings = [w for w in load_seed_data().warnings if "scaling" in w]
    assert not warnings, warnings


def test_scaling_scores_are_loaded(seed):
    by_name = {c.name: c.scaling for c in seed.champions}
    assert by_name["Blitzcrank"] == 1 and by_name["Ahri"] == 2 and by_name["Azir"] == 3


def test_pools_have_five_distinct_champions(seed):
    for pool in seed.pools.values():
        assert len(pool) == 5 and len(set(pool)) == 5


def test_loading_twice_is_independent():
    assert load_seed_data().champions == load_seed_data().champions


# ------------------------------------------------------------------ data quality
def _stats_names():
    import csv
    from app.data.loader import SEED_DIR, _norm
    with open(SEED_DIR / "ChampionStatistics.csv", newline="", encoding="utf-8-sig") as fh:
        return [_norm(r["Champion"]) for r in csv.DictReader(fh)]


def test_every_champion_has_a_statistics_row():
    """A champion without a ChampionStatistics.csv row would silently get a 50% win rate."""
    from app.data.loader import _norm
    stats = set(_stats_names())
    missing = [c.name for c in load_seed_data().champions if _norm(c.name) not in stats]
    assert not missing, f"Champions.csv rows with no ChampionStatistics.csv row: {missing}"


def test_statistics_rows_are_unique():
    names = _stats_names()
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"duplicate rows in ChampionStatistics.csv: {duplicates}"


def test_no_champion_attribute_is_blank():
    """A blank cell is silently replaced by a default at load time; make the data fix it instead."""
    warnings = [w for w in load_seed_data().warnings if w.startswith("Champion ") or w.startswith("No statistics row")]
    assert not warnings, warnings

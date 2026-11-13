"""Season formats: round robin schedules and standings tiebreakers."""
from collections import Counter
from itertools import combinations

import pytest

from app.game.competition import Result, round_robin, standings, wins_needed


@pytest.mark.parametrize("n", [2, 3, 4, 5, 8, 10, 16])
def test_round_robin_pairs_every_team_once(n):
    teams = list(range(1, n + 1))
    rounds = round_robin(teams)
    assert len(rounds) == (n - 1 if n % 2 == 0 else n)
    met = Counter(frozenset(p) for r in rounds for p in r)
    assert set(met) == {frozenset(p) for p in combinations(teams, 2)}
    assert all(c == 1 for c in met.values())
    for r in rounds:                                    # nobody plays twice in a round
        playing = [t for p in r for t in p]
        assert len(playing) == len(set(playing))


@pytest.mark.parametrize("n", [4, 6, 8, 10])
def test_round_robin_balances_home_and_away(n):
    rounds = round_robin(list(range(n)))
    home = Counter(h for r in rounds for h, _ in r)
    away = Counter(a for r in rounds for _, a in r)
    for t in range(n):
        assert abs(home[t] - away[t]) <= 1


def test_double_round_robin_swaps_home_and_away():
    rounds = round_robin([1, 2, 3, 4], double=True)
    assert len(rounds) == 6
    first, second = rounds[:3], rounds[3:]
    assert [[(a, h) for h, a in r] for r in first] == second
    met = Counter(frozenset(p) for r in rounds for p in r)
    assert all(c == 2 for c in met.values())


def test_round_robin_needs_two_teams():
    assert round_robin([1]) == []


def test_standings_rank_by_wins_then_head_to_head():
    seeds = {"A": 1, "B": 2, "C": 3}
    results = [Result("A", "B", 0, 1), Result("B", "C", 0, 1), Result("C", "A", 1, 0), Result("A", "B", 1, 0)]
    table = standings(seeds, results)
    # C 2-0; A and B are both 1-2 and split their meetings, so game diff (equal) then seed decides
    assert [r.team for r in table] == ["C", "A", "B"]
    assert table[0].wins == 2 and table[0].losses == 0 and table[0].rank == 1


def test_head_to_head_beats_game_differential():
    seeds = {"A": 1, "B": 2, "C": 3, "D": 4}
    results = [
        Result("B", "A", 1, 0),       # B beat A head to head
        Result("A", "C", 2, 0), Result("A", "D", 2, 0),
        Result("B", "C", 2, 1), Result("D", "B", 2, 1),
    ]
    table = standings(seeds, results)
    a, b = next(r for r in table if r.team == "A"), next(r for r in table if r.team == "B")
    assert a.wins == b.wins == 2 and a.game_diff > b.game_diff
    assert [r.team for r in table][:2] == ["B", "A"]


def test_seed_breaks_a_complete_tie():
    table = standings({"A": 2, "B": 1}, [])
    assert [r.team for r in table] == ["B", "A"]


def test_streak_and_form():
    results = [Result("A", "B", 1, 0), Result("A", "B", 0, 1), Result("A", "B", 0, 1)]
    rows = {r.team: r for r in standings({"A": 1, "B": 2}, results)}
    assert rows["A"].form == ["W", "L", "L"] and rows["A"].streak == "L2"
    assert rows["B"].streak == "W2"


def test_wins_needed():
    assert [wins_needed(f) for f in ("BO1", "BO3", "BO5")] == [1, 2, 3]


# ------------------------------------------------------------------ Swiss
import random  # noqa: E402

from app.game.competition import (  # noqa: E402
    bracket_first_round, bracket_order, bracket_round_name, bracket_rounds, swiss_pairings, swiss_records,
    swiss_rounds,
)


def play_swiss(n, wins, losses, rng):
    """Run a whole Swiss stage with random winners; returns (records, rounds played)."""
    seeds = {t: t for t in range(1, n + 1)}
    results = []
    rounds = 0
    while True:
        records = swiss_records(seeds, results, wins, losses)
        pairs = swiss_pairings(records)
        if not pairs:
            return records, rounds, results
        rounds += 1
        for home, away in pairs:
            assert records[home].status is None and records[away].status is None
            results.append(Result(home, away, *((1, 0) if rng.random() < 0.5 else (0, 1))))


@pytest.mark.parametrize("n,wins", [(8, 2), (16, 3)])
@pytest.mark.parametrize("rng_seed", range(20))
def test_swiss_stage_qualifies_half_the_field(n, wins, rng_seed):
    records, rounds, results = play_swiss(n, wins, wins, random.Random(rng_seed))
    statuses = Counter(r.status for r in records.values())
    assert statuses == {"QUALIFIED": n // 2, "ELIMINATED": n // 2}
    assert rounds <= swiss_rounds(wins, wins)
    for r in records.values():                       # nobody plays past their decision
        assert r.wins <= wins and r.losses <= wins
    # the first two rounds can always avoid a rematch
    early = results[: n // 2 + n // 2]
    met = Counter(frozenset((x.home, x.away)) for x in early)
    assert all(c == 1 for c in met.values())


@pytest.mark.parametrize("rng_seed", range(10))
def test_swiss_only_pairs_equal_records(rng_seed):
    rng = random.Random(rng_seed)
    seeds = {t: t for t in range(1, 17)}
    results = []
    while True:
        records = swiss_records(seeds, results, 3, 3)
        pairs = swiss_pairings(records)
        if not pairs:
            break
        for home, away in pairs:
            assert (records[home].wins, records[home].losses) == (records[away].wins, records[away].losses)
            results.append(Result(home, away, *((1, 0) if rng.random() < 0.5 else (0, 1))))


def test_swiss_first_round_is_top_half_against_bottom_half():
    records = swiss_records({t: t for t in range(1, 9)}, [], 2, 2)
    pairs = swiss_pairings(records)
    assert sorted(tuple(sorted(p)) for p in pairs) == [(1, 5), (2, 6), (3, 7), (4, 8)]


def test_swiss_pairs_same_records_and_balances_home():
    seeds = {t: t for t in range(1, 9)}
    results = [Result(1, 5, 1, 0), Result(2, 6, 1, 0), Result(3, 7, 1, 0), Result(4, 8, 1, 0)]
    records = swiss_records(seeds, results, 2, 2)
    for home, away in swiss_pairings(records):
        assert (records[home].wins, records[home].losses) == (records[away].wins, records[away].losses)
        assert records[home].home <= records[away].home


def test_bracket_seeding():
    assert bracket_order(2) == [1, 2]
    assert bracket_order(4) == [1, 4, 2, 3]
    assert bracket_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    assert bracket_first_round(["a", "b", "c", "d"]) == [("a", "d"), ("b", "c")]
    with pytest.raises(ValueError):
        bracket_order(6)


def test_bracket_round_names():
    assert [bracket_round_name(r, 8) for r in (1, 2, 3)] == ["Quarterfinals", "Semifinals", "Final"]
    assert bracket_round_name(1, 16) == "Round of 16"
    assert [bracket_rounds(s) for s in (0, 2, 4, 8)] == [0, 1, 2, 3]

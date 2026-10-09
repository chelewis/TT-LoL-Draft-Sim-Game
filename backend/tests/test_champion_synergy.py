"""Same-team champion pair win rates: match reduction, aggregation, the two output files and the crawl loop."""
import csv

import pytest

from app.integrations.riot import synergy
from app.integrations.riot.errors import RiotNotFound, RiotRateLimited
from scripts.champion_synergy import MatchCache, crawl

NAMES = {1: "Ahri", 2: "Braum", 3: "Corki", 4: "Darius", 5: "Ekko", 6: "Fizz", 7: "Garen", 8: "Hecarim", 9: "Irelia",
         10: "Jax", 11: "Karma"}


def match(match_id, blue, red, blue_wins=True, minutes=30, queue=420, version="15.19.712.1234"):
    people = [{"teamId": 100, "championId": c, "win": blue_wins} for c in blue]
    people += [{"teamId": 200, "championId": c, "win": not blue_wins} for c in red]
    return {"metadata": {"matchId": match_id},
            "info": {"queueId": queue, "gameDuration": minutes * 60, "gameVersion": version, "participants": people}}


def record(blue, red, blue_wins=True):
    return synergy.reduce_match(match("X", blue, red, blue_wins))


BLUE, RED = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10]


# ------------------------------------------------------------------ reduce
def test_reduce_match_keeps_teams_winner_and_patch():
    r = synergy.reduce_match(match("EUW1_1", BLUE, RED, blue_wins=False))
    assert r == {"id": "EUW1_1", "version": "15.19", "duration": 1800,
                 "teams": [{"champions": BLUE, "win": False}, {"champions": RED, "win": True}]}


def test_reduce_match_rejects_remakes_other_queues_and_broken_games():
    assert synergy.reduce_match(match("a", BLUE, RED, minutes=3)) is None          # remake
    assert synergy.reduce_match(match("a", BLUE, RED, queue=450)) is None          # ARAM
    assert synergy.reduce_match(match("a", BLUE[:4], RED)) is None                 # a player is missing
    both_win = match("a", BLUE, RED)
    for p in both_win["info"]["participants"]:
        p["win"] = True
    assert synergy.reduce_match(both_win) is None
    assert synergy.reduce_match({}) is None


# --------------------------------------------------------------- aggregate
def test_aggregate_counts_pairs_and_wins_in_either_order():
    records = [record(BLUE, RED, True), record([2, 1, 6, 7, 8], [3, 4, 5, 9, 10], False), record(BLUE, RED, False)]
    table = synergy.aggregate(records, NAMES.get)
    assert table.matches == 3 and table.versions == {"15.19": 3}
    assert table.pairs[("Ahri", "Braum")] == [3, 1]             # together in all three, won only the first
    assert table.pairs[("Ahri", "Fizz")] == [1, 0]              # same team once
    assert ("Braum", "Ahri") not in table.pairs                 # one key per pair, names in order
    assert table.champions["Ahri"] == [3, 1] and table.champions["Fizz"] == [3, 1]        # Fizz only wins the third
    assert ("Ahri", "Jax") not in table.pairs                   # never on the same team


def test_each_match_adds_ten_pairs_per_team():
    table = synergy.aggregate([record(BLUE, RED)], NAMES.get)
    assert len(table.pairs) == 20 and sum(games for games, _ in table.pairs.values()) == 20


def test_champions_not_in_our_game_are_left_out_and_reported():
    table = synergy.aggregate([record([1, 2, 3, 4, 99], RED)], NAMES.get)
    assert table.unmapped == {99}
    assert len([p for p in table.pairs if "Ahri" in p]) == 3    # Ahri still pairs with her three known teammates


def test_smoothing_pulls_small_samples_towards_the_expected_rate():
    # Ahri + Braum win 4 of 4 together; then they play 4 games apart, which Braum's side wins
    records = [record(BLUE, RED, True)] * 4 + [record([1, 6, 7, 8, 9], [2, 3, 4, 5, 10], False)] * 4
    table = synergy.aggregate(records, NAMES.get)
    assert table.win_rate("Ahri") == 0.5 and table.win_rate("Braum") == 1.0
    assert table.expected("Ahri", "Braum") == pytest.approx(0.75)
    assert table.smoothed("Braum", "Ahri", prior_games=20) == pytest.approx((4 + 20 * 0.75) / 24)
    assert table.smoothed("Ahri", "Braum", prior_games=0) == 1.0                    # no smoothing: the raw rate
    assert 0.75 < table.smoothed("Ahri", "Braum") < 1.0


def test_aggregate_counts_opponents_from_the_first_named_champions_side():
    records = [record(BLUE, RED, True)] * 3 + [record(RED, BLUE, True)]
    table = synergy.aggregate(records, NAMES.get)
    assert len(table.versus) == 25                               # every blue champion met every red one
    assert table.versus[("Ahri", "Fizz")] == [4, 3]              # Ahri beat Fizz three times out of four
    assert table.versus[("Braum", "Jax")] == [4, 3]
    assert ("Fizz", "Ahri") not in table.versus and ("Ahri", "Braum") not in table.versus     # teammates never face
    assert table.expected_versus("Ahri", "Fizz") == pytest.approx(0.75)
    assert table.smoothed_versus("Ahri", "Fizz", prior_games=0) == 0.75
    assert table.smoothed_versus("Fizz", "Ahri") == pytest.approx(1 - table.smoothed_versus("Ahri", "Fizz"))


# ------------------------------------------------------------------ output
def test_counter_csv_gives_the_first_champions_numbers(tmp_path):
    table = synergy.aggregate([record(BLUE, RED, True)] * 3 + [record(BLUE, RED, False)], NAMES.get)
    assert synergy.write_counter_csv(table, tmp_path / "counter.csv") == 25
    rows = list(csv.DictReader((tmp_path / "counter.csv").open(encoding="utf-8")))
    assert list(rows[0]) == synergy.PAIR_COLUMNS
    row = next(r for r in rows if (r["champion_a"], r["champion_b"]) == ("Ahri", "Fizz"))
    assert (row["games"], row["wins"], row["win_rate"], row["smoothed_win_rate"]) == ("4", "3", "75.0", "75.0")


def test_pairs_csv_lists_every_seen_pair_with_its_numbers(tmp_path):
    records = [record(BLUE, RED, True)] * 3 + [record(BLUE, RED, False)]
    table = synergy.aggregate(records, NAMES.get)
    assert synergy.write_pairs_csv(table, tmp_path / "pairs.csv") == 20
    rows = list(csv.DictReader((tmp_path / "pairs.csv").open(encoding="utf-8")))
    assert list(rows[0]) == synergy.PAIR_COLUMNS
    row = next(r for r in rows if (r["champion_a"], r["champion_b"]) == ("Ahri", "Braum"))
    assert (row["games"], row["wins"], row["win_rate"], row["expected_win_rate"]) == ("4", "3", "75.0", "75.0")
    assert row["smoothed_win_rate"] == "75.0" and row["synergy"] == "+0.0"


def test_matrix_is_symmetric_and_blank_below_the_minimum(tmp_path):
    records = [record(BLUE, RED, True)] * 5 + [record([1, 6, 7, 8, 9], [2, 3, 4, 5, 10], True)] * 2
    table = synergy.aggregate(records, NAMES.get)
    filled = synergy.write_matrix_csv(table, tmp_path / "matrix.csv", min_games=5)
    grid = list(csv.reader((tmp_path / "matrix.csv").open(encoding="utf-8")))
    names = grid[0][1:]
    assert names == sorted(names) and [r[0] for r in grid[1:]] == names

    def cell(a, b):
        return grid[1 + names.index(a)][1 + names.index(b)]

    assert cell("Ahri", "Ahri") == ""                                   # diagonal
    assert cell("Ahri", "Braum") == cell("Braum", "Ahri") != ""         # 5 games together
    assert cell("Ahri", "Fizz") == cell("Fizz", "Ahri") == ""           # only 2 games together
    assert cell("Braum", "Corki") != ""                                 # 7 games together
    assert filled == sum(1 for i, a in enumerate(names) for b in names[i + 1:] if cell(a, b))


# ------------------------------------------------------------------- crawl
class FakeClient:
    """Three players per page with four match ids each; neighbouring players share one id, like real teammates.
    Ids ending in _1 are gone from Riot's history and ids ending in _2 are remakes."""

    def __init__(self, players=3, per_player=4, pages=1, limited_once=False):
        self.players, self.per_player, self.pages = players, per_player, pages
        self.calls = []
        self.limited = limited_once

    def league_entries_page(self, region, tier, division, page):
        self.calls.append(f"page:{page}")
        if page > self.pages:
            return []
        return [{"puuid": f"p{page}_{i}"} for i in range(self.players)] + [{"summonerId": "no puuid"}]

    def match_ids(self, region, puuid, count, **filters):
        self.calls.append(f"ids:{puuid}")
        assert filters == {"queue": 420, "startTime": 1000}
        page, n = puuid.split("_")
        return [f"M{page}_{int(n) * (self.per_player - 1) + i}" for i in range(self.per_player)]

    def match(self, region, match_id):
        self.calls.append(f"match:{match_id}")
        if self.limited:
            self.limited = False
            raise RiotRateLimited("slow down")
        if match_id.endswith("_1"):
            raise RiotNotFound("gone")
        if match_id.endswith("_2"):
            return match(match_id, BLUE, RED, minutes=2)
        return match(match_id, BLUE, RED)


def run(client, cache, target):
    return crawl(client, cache, region="EUW1", tier="EMERALD", division="I", target=target, start_time=1000,
                 log=lambda *_: None, sleep=lambda s: None)


def test_crawl_stops_at_the_target_and_never_downloads_a_match_twice(tmp_path):
    cache = MatchCache(tmp_path / "cache" / "m.jsonl")
    client = FakeClient()
    assert run(client, cache, 5) == 5 and len(cache.records) == 5
    fetched = [c for c in client.calls if c.startswith("match:")]
    assert len(fetched) == len(set(fetched))                        # shared ids are fetched once
    assert "Mp1_1" in cache.seen and "Mp1_2" in cache.seen          # the missing match and the remake are remembered
    assert all(r["id"] not in ("Mp1_1", "Mp1_2") for r in cache.records)


def test_crawl_resumes_from_the_cache_file(tmp_path):
    path = tmp_path / "m.jsonl"
    first = FakeClient()
    run(first, MatchCache(path), 4)
    reopened = MatchCache(path)
    assert len(reopened.records) == 4 and len(reopened.seen) == 6   # 4 usable + the missing one + the remake
    second = FakeClient()
    assert run(second, reopened, 100) == 4                          # only the 4 it had not seen; then no more pages
    already = {c for c in first.calls if c.startswith("match:")}
    assert not already & {c for c in second.calls if c.startswith("match:")}
    assert len(MatchCache(path).records) == 8
    assert second.calls[-1] == "page:2"                             # ran out of players and stopped


def test_crawl_waits_and_retries_when_rate_limited(tmp_path):
    waits = []
    client = FakeClient(limited_once=True)
    added = crawl(client, MatchCache(tmp_path / "m.jsonl"), region="EUW1", tier="EMERALD", division="I", target=2,
                  start_time=1000, log=lambda *_: None, sleep=waits.append)
    assert added == 2 and waits == [30]

"""Champion pair win rates from sampled matches, for pairs on the same team and for pairs on opposite teams.
Pure functions: no network, no database.

A match is first reduced to a small record (`reduce_match`), records are aggregated into a `SynergyTable`
(`aggregate`), and the table is written as a list of same-team pairs, a list of opposing pairs and a
champion x champion matrix.
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Callable, Iterable

from .config import MIN_GAME_SECONDS

SOLO_QUEUE = 420
PRIOR_GAMES = 20        # weight of the expected win rate when smoothing, in games


def reduce_match(match: dict, queue_id: int = SOLO_QUEUE) -> dict | None:
    """The parts of a match-v5 document this analysis needs, or None for remakes, other queues and odd games."""
    info = match.get("info", {})
    if info.get("queueId") != queue_id:
        return None
    seconds = info.get("gameDuration") or 0
    if seconds > 100_000:      # old matches report milliseconds
        seconds /= 1000
    if seconds < MIN_GAME_SECONDS:
        return None
    teams: dict[int, dict] = {}
    for p in info.get("participants", []):
        team = teams.setdefault(p.get("teamId"), {"champions": [], "win": bool(p.get("win"))})
        team["champions"].append(int(p.get("championId", 0)))
    sides = list(teams.values())
    if len(sides) != 2 or any(len(t["champions"]) != 5 for t in sides) or sides[0]["win"] == sides[1]["win"]:
        return None
    version = ".".join(str(info.get("gameVersion", "")).split(".")[:2])
    return {"id": match.get("metadata", {}).get("matchId"), "version": version, "duration": int(seconds), "teams": sides}


@dataclass
class SynergyTable:
    matches: int = 0
    champions: dict[str, list[int]] = field(default_factory=dict)             # name -> [games, wins]
    pairs: dict[tuple[str, str], list[int]] = field(default_factory=dict)     # (a, b) with a < b -> [games, wins]
    versus: dict[tuple[str, str], list[int]] = field(default_factory=dict)    # opponents, a < b -> [games, a's wins]
    versions: Counter = field(default_factory=Counter)                        # patch -> matches
    unmapped: set[int] = field(default_factory=set)                           # Riot champion keys not in our game

    def win_rate(self, name: str) -> float:
        games, wins = self.champions[name]
        return wins / games

    def expected(self, a: str, b: str) -> float:
        """What the two champions' own win rates predict for the pair: their average."""
        return (self.win_rate(a) + self.win_rate(b)) / 2

    def smoothed(self, a: str, b: str, prior_games: float = PRIOR_GAMES) -> float:
        """The pair's win rate pulled towards the expected one; the fewer the games, the stronger the pull."""
        games, wins = self.pairs[tuple(sorted((a, b)))]
        return (wins + prior_games * self.expected(a, b)) / (games + prior_games)

    def expected_versus(self, a: str, b: str) -> float:
        """What the two champions' own win rates predict for a against b: even, shifted by half their difference."""
        return 0.5 + (self.win_rate(a) - self.win_rate(b)) / 2

    def smoothed_versus(self, a: str, b: str, prior_games: float = PRIOR_GAMES) -> float:
        """a's win rate against b, pulled towards the expected one. b against a is one minus it."""
        first, second = sorted((a, b))
        games, wins = self.versus[(first, second)]
        rate = (wins + prior_games * self.expected_versus(first, second)) / (games + prior_games)
        return rate if a == first else 1 - rate


def aggregate(records: Iterable[dict], to_name: Callable[[int], str | None]) -> SynergyTable:
    """Count games and wins for every champion, every same-team pair and every pair of opponents. `to_name` maps a
    Riot champion key to our champion name, or None for a champion our game does not have (those are left out of
    the pairs)."""
    table = SynergyTable()
    for record in records:
        table.matches += 1
        table.versions[record.get("version", "")] += 1
        sides = []
        for team in record["teams"]:
            won = 1 if team["win"] else 0
            names = []
            for key in team["champions"]:
                name = to_name(key)
                if name is None:
                    table.unmapped.add(key)
                else:
                    names.append(name)
            for name in names:
                entry = table.champions.setdefault(name, [0, 0])
                entry[0] += 1
                entry[1] += won
            for pair in combinations(sorted(set(names)), 2):
                entry = table.pairs.setdefault(pair, [0, 0])
                entry[0] += 1
                entry[1] += won
            sides.append((set(names), won))
        (ours, our_win), (theirs, their_win) = sides
        for a in ours:
            for b in theirs:
                if a == b:
                    continue
                entry = table.versus.setdefault(tuple(sorted((a, b))), [0, 0])
                entry[0] += 1
                entry[1] += our_win if a < b else their_win
    return table


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}"


PAIR_COLUMNS = ["champion_a", "champion_b", "games", "wins", "win_rate", "expected_win_rate", "smoothed_win_rate", "synergy"]


def write_pairs_csv(table: SynergyTable, path: Path, prior_games: float = PRIOR_GAMES) -> int:
    """One row per pair that was seen, most games first. Rates are percentages; synergy is in percentage points."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(table.pairs.items(), key=lambda item: (-item[1][0], item[0]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PAIR_COLUMNS)
        for (a, b), (games, wins) in rows:
            expected = table.expected(a, b)
            smoothed = table.smoothed(a, b, prior_games)
            writer.writerow([a, b, games, wins, _pct(wins / games), _pct(expected), _pct(smoothed),
                             f"{(smoothed - expected) * 100:+.1f}"])
    return len(rows)


def write_counter_csv(table: SynergyTable, path: Path, prior_games: float = PRIOR_GAMES) -> int:
    """One row per pair of opponents that was seen, most games first, with the same columns as the pairs file.
    Every number is champion_a's against champion_b; the last column is how far a beats the expected rate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(table.versus.items(), key=lambda item: (-item[1][0], item[0]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PAIR_COLUMNS)
        for (a, b), (games, wins) in rows:
            expected = table.expected_versus(a, b)
            smoothed = table.smoothed_versus(a, b, prior_games)
            writer.writerow([a, b, games, wins, _pct(wins / games), _pct(expected), _pct(smoothed),
                             f"{(smoothed - expected) * 100:+.1f}"])
    return len(rows)


def write_matrix_csv(table: SynergyTable, path: Path, min_games: int = 5, prior_games: float = PRIOR_GAMES) -> int:
    """Champion x champion grid of smoothed win rates (percent). Blank on the diagonal and for pairs with fewer
    than `min_games` games. Returns the number of pairs that were filled in."""
    path.parent.mkdir(parents=True, exist_ok=True)
    names = sorted(table.champions)
    filled = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["champion"] + names)
        for a in names:
            row = [a]
            for b in names:
                entry = table.pairs.get(tuple(sorted((a, b)))) if a != b else None
                if entry is None or entry[0] < min_games:
                    row.append("")
                else:
                    row.append(_pct(table.smoothed(a, b, prior_games)))
                    filled += a < b
            writer.writerow(row)
    return filled

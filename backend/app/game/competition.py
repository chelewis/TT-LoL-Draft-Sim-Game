"""Competition formats for seasons: fixture schedules and standings. Pure Python, no framework or database imports.

Teams are identified by any hashable id (the service uses SeasonTeam ids).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Iterable, Sequence

TeamId = Hashable


def round_robin(team_ids: Sequence[TeamId], double: bool = False) -> list[list[tuple[TeamId, TeamId]]]:
    """Every team plays every other team once (twice when `double`, with home and away swapped the second time).

    Returns rounds of (home, away) pairs using the circle method: with an odd number of teams one team sits out
    each round. Home and away alternate, so no team is home more than once more than it is away (per half)."""
    teams: list[TeamId | None] = list(team_ids)
    if len(teams) < 2:
        return []
    if len(teams) % 2:
        teams.append(None)                       # the bye
    n = len(teams)
    rounds: list[list[tuple[TeamId, TeamId]]] = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = teams[i], teams[n - 1 - i]
            if a is None or b is None:
                continue
            # the fixed team alternates home and away; the rest alternate by position and round
            home_first = (r % 2 == 0) if i == 0 else (i % 2 == 1)
            pairs.append((a, b) if home_first else (b, a))
        rounds.append(pairs)
        teams = [teams[0], teams[-1], *teams[1:-1]]   # rotate every team but the first
    if double:
        rounds += [[(away, home) for home, away in pairs] for pairs in rounds]
    return rounds


@dataclass(frozen=True)
class Result:
    """A decided fixture: the series score and the winner."""
    home: TeamId
    away: TeamId
    home_score: int
    away_score: int

    @property
    def winner(self) -> TeamId:
        return self.home if self.home_score > self.away_score else self.away

    @property
    def loser(self) -> TeamId:
        return self.away if self.home_score > self.away_score else self.home


@dataclass
class StandingRow:
    team: TeamId
    seed: int
    played: int = 0
    wins: int = 0
    losses: int = 0
    game_wins: int = 0
    game_losses: int = 0
    streak: str = ""                                    # "W3", "L1": the current run of results
    form: list[str] = field(default_factory=list)       # last results, oldest first ("W" / "L")
    rank: int = 0

    @property
    def game_diff(self) -> int:
        return self.game_wins - self.game_losses

    def to_dict(self) -> dict:
        return {"team": self.team, "seed": self.seed, "rank": self.rank, "played": self.played,
                "wins": self.wins, "losses": self.losses, "game_wins": self.game_wins,
                "game_losses": self.game_losses, "game_diff": self.game_diff,
                "streak": self.streak, "form": self.form[-5:]}


def _head_to_head(group: set[TeamId], results: Iterable[Result]) -> dict[TeamId, int]:
    wins = {t: 0 for t in group}
    for r in results:
        if r.home in group and r.away in group:
            wins[r.winner] += 1
    return wins


def standings(seeds: dict[TeamId, int], results: Sequence[Result]) -> list[StandingRow]:
    """The table, best first. Ties on match wins are broken by head-to-head wins among the tied teams, then
    game differential, then game wins, then seed (lower is better). `results` are in the order they were played."""
    rows = {t: StandingRow(team=t, seed=s) for t, s in seeds.items()}
    for r in results:
        for team, won, gw, gl in ((r.home, r.winner == r.home, r.home_score, r.away_score),
                                  (r.away, r.winner == r.away, r.away_score, r.home_score)):
            row = rows.get(team)
            if row is None:
                continue
            row.played += 1
            row.wins += won
            row.losses += not won
            row.game_wins += gw
            row.game_losses += gl
            row.form.append("W" if won else "L")
    for row in rows.values():
        if row.form:
            last = row.form[-1]
            run = next((i for i, f in enumerate(reversed(row.form)) if f != last), len(row.form))
            row.streak = f"{last}{run}"

    by_wins: dict[int, list[StandingRow]] = {}
    for row in rows.values():
        by_wins.setdefault(row.wins, []).append(row)
    ordered: list[StandingRow] = []
    for wins in sorted(by_wins, reverse=True):
        group = by_wins[wins]
        h2h = _head_to_head({r.team for r in group}, results) if len(group) > 1 else {}
        group.sort(key=lambda r: (-h2h.get(r.team, 0), -r.game_diff, -r.game_wins, r.seed))
        ordered += group
    for i, row in enumerate(ordered):
        row.rank = i + 1
    return ordered


def wins_needed(series_format: str) -> int:
    """Games needed to take a best-of series ("BO1" -> 1, "BO3" -> 2, "BO5" -> 3)."""
    return int(series_format[2:]) // 2 + 1


# ------------------------------------------------------------------ Swiss
@dataclass
class SwissRecord:
    team: TeamId
    seed: int
    wins: int = 0
    losses: int = 0
    game_diff: int = 0
    home: int = 0                                         # matches played as the home team
    opponents: set = field(default_factory=set)
    status: str | None = None                             # "QUALIFIED" / "ELIMINATED" once decided

    def to_dict(self) -> dict:
        return {"team": self.team, "wins": self.wins, "losses": self.losses, "status": self.status}


def swiss_records(seeds: dict[TeamId, int], results: Sequence[Result], wins_to_qualify: int,
                  losses_to_exit: int) -> dict[TeamId, SwissRecord]:
    """Every team's Swiss record and whether it has qualified (enough wins) or been eliminated (enough losses)."""
    records = {t: SwissRecord(team=t, seed=s) for t, s in seeds.items()}
    for r in results:
        home, away = records.get(r.home), records.get(r.away)
        if home is None or away is None:
            continue
        home.home += 1
        home.opponents.add(r.away)
        away.opponents.add(r.home)
        records[r.winner].wins += 1
        records[r.loser].losses += 1
        diff = r.home_score - r.away_score
        home.game_diff += diff
        away.game_diff -= diff
    for rec in records.values():
        if rec.wins >= wins_to_qualify:
            rec.status = "QUALIFIED"
        elif rec.losses >= losses_to_exit:
            rec.status = "ELIMINATED"
    return records


def swiss_pairings(records: dict[TeamId, SwissRecord]) -> list[tuple[TeamId, TeamId]]:
    """The next Swiss round: teams still in it play someone with the same record, and not an opponent they've
    already met unless every pairing of that record group needs a rematch. The first round pairs the top half of the seeds with the bottom half.
    The home team is whichever has played fewer home matches (the better seed on a tie)."""
    alive = [r for r in records.values() if r.status is None]
    if len(alive) < 2:
        return []
    if all(r.wins == r.losses == 0 for r in alive):
        ordered = sorted(alive, key=lambda r: r.seed)
        half = len(ordered) // 2
        pairs = list(zip(ordered[:half], ordered[half:]))
    else:
        pairs = []
        groups: dict[tuple[int, int], list[SwissRecord]] = {}
        for r in alive:
            groups.setdefault((r.wins, r.losses), []).append(r)
        carry: list[SwissRecord] = []           # a team left over from an odd group plays down a group
        for key in sorted(groups, key=lambda k: (-k[0], k[1])):
            group = carry + sorted(groups[key], key=lambda r: (-r.game_diff, r.seed))
            carry = [group.pop()] if len(group) % 2 else []
            pairs += _pair_up(group, avoid_rematches=True) or _pair_up(group, avoid_rematches=False) or []
    out = []
    for a, b in pairs:
        home, away = (a, b) if (a.home, a.seed) <= (b.home, b.seed) else (b, a)
        out.append((home.team, away.team))
    return out


def _pair_up(ordered: list[SwissRecord], avoid_rematches: bool) -> list[tuple[SwissRecord, SwissRecord]] | None:
    """Pair the first unpaired team with the next team it can play, backtracking when a choice leaves the rest
    unpairable. None when there's no way to pair them all (without a rematch, when `avoid_rematches`)."""
    if len(ordered) < 2:
        return []
    first, rest = ordered[0], ordered[1:]
    for partner in rest:
        if avoid_rematches and partner.team in first.opponents:
            continue
        remaining = [r for r in rest if r is not partner]
        tail = _pair_up(remaining, avoid_rematches)
        if tail is not None:
            return [(first, partner), *tail]
    return None


def swiss_rounds(wins_to_qualify: int, losses_to_exit: int) -> int:
    """The most rounds a Swiss stage can take (a team going wins-1 / losses-1 plays the decider)."""
    return wins_to_qualify + losses_to_exit - 1


# --------------------------------------------------------------- brackets
def bracket_order(size: int) -> list[int]:
    """Seed numbers in bracket position order, so the top seeds can only meet late: 4 -> [1, 4, 2, 3],
    8 -> [1, 8, 4, 5, 2, 7, 3, 6]. Neighbouring positions play each other in the first round."""
    if size < 2 or size & (size - 1):
        raise ValueError("A bracket needs a power of two teams")
    order = [1, 2]
    while len(order) < size:
        n = len(order) * 2
        order = [s for seed in order for s in (seed, n + 1 - seed)]
    return order


def bracket_first_round(seeded: Sequence[TeamId]) -> list[tuple[TeamId, TeamId]]:
    """First-round (home, away) pairs for teams listed best seed first; the better seed is home."""
    order = bracket_order(len(seeded))
    return [(seeded[order[i] - 1], seeded[order[i + 1] - 1]) for i in range(0, len(order), 2)]


def bracket_rounds(size: int) -> int:
    return max(0, size.bit_length() - 1)


def bracket_round_name(round_: int, size: int) -> str:
    """"Final", "Semifinals", "Quarterfinals", or "Round of 16"."""
    left = size >> (round_ - 1)                              # teams still in when the round starts
    return {2: "Final", 4: "Semifinals", 8: "Quarterfinals"}.get(left, f"Round of {left}")

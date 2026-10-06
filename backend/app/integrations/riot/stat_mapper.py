"""Turn real match history into game player stats. Pure functions: no network, no database.

Input is a list of Riot `match-v5` match documents (the full JSON) plus the player's `puuid`.
Missing optional fields are tolerated: every metric falls back to values computed from the
basic participant fields.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from .config import (APEX_TIERS, BENCHMARKS, METRIC_INFO, MIN_GAME_SECONDS, RANK_FOR_SOURCE, RANK_QUEUE_TYPES,
                     RANK_TIERS, STAT_METRICS, TEAM_POSITION_TO_LANE)
from .errors import NotEnoughData, RiotNotFound

STATS = ("aggr", "aware", "pos", "dmg", "cs")


@dataclass
class GameSample:
    lane: str | None
    champion_key: int
    metrics: dict[str, float]


@dataclass
class Analysis:
    games: int
    lane: str
    lane_counts: dict[str, int]
    raw_stats: dict[str, float]            # unrounded 1-10 values before fitting to the budget
    stats: dict[str, int]                  # final integer stats
    fitted_to_budget: bool
    champion_games: Counter = field(default_factory=Counter)   # Riot champion key -> games played
    # per stat: the metrics behind it, with the player's average, the role benchmark and the resulting 1-10 score
    breakdown: dict[str, list[dict]] = field(default_factory=dict)
    total_before_fit: int = 0                                  # sum of the rounded stats before fitting to the budget
    budget: int = 0
    floor: int = 0
    raised_to_floor: bool = False


def scale(value: float, low: float, high: float, lower_is_better: bool = False) -> float:
    """Linearly map value in [low, high] to [1, 10], clamped."""
    if high == low:
        return 1.0
    t = max(0.0, min(1.0, (value - low) / (high - low)))
    if lower_is_better:
        t = 1.0 - t
    return 1.0 + 9.0 * t


def _participant(match: dict, puuid: str) -> dict | None:
    for p in match.get("info", {}).get("participants", []):
        if p.get("puuid") == puuid:
            return p
    return None


def sample_game(match: dict, puuid: str, queue_ids=None) -> GameSample | None:
    """Per-game metrics for one player, or None for remakes, games the player is not in, or games outside `queue_ids`."""
    info = match.get("info", {})
    if queue_ids is not None and info.get("queueId") not in queue_ids:
        return None
    seconds = info.get("gameDuration") or 0
    if seconds > 100_000:      # old matches report milliseconds
        seconds /= 1000
    p = _participant(match, puuid)
    if p is None or seconds < MIN_GAME_SECONDS:
        return None
    minutes = seconds / 60
    team = [q for q in info["participants"] if q.get("teamId") == p.get("teamId")]
    team_kills = sum(q.get("kills", 0) for q in team) or 1
    team_damage = sum(q.get("totalDamageDealtToChampions", 0) for q in team) or 1
    kills, deaths, assists = p.get("kills", 0), p.get("deaths", 0), p.get("assists", 0)
    ch = p.get("challenges") or {}

    objectives = ch.get("dragonTakedowns", p.get("dragonKills", 0)) + ch.get("baronTakedowns", p.get("baronKills", 0))
    metrics = {
        "kill_participation": ch.get("killParticipation", (kills + assists) / team_kills),
        "kills_per_min": kills / minutes,
        "vision_per_min": ch.get("visionScorePerMinute", p.get("visionScore", 0) / minutes),
        "objectives_per_game": float(objectives),
        "deaths_per_min": deaths / minutes,
        "kda": (kills + assists) / max(1, deaths),
        "damage_per_min": ch.get("damagePerMinute", p.get("totalDamageDealtToChampions", 0) / minutes),
        "damage_share": ch.get("teamDamagePercentage", p.get("totalDamageDealtToChampions", 0) / team_damage),
        "cs_per_min": (p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)) / minutes,
    }
    lane = TEAM_POSITION_TO_LANE.get(p.get("teamPosition") or p.get("individualPosition") or "")
    return GameSample(lane, int(p.get("championId", 0)), metrics)


def fit_to_budget(stats: dict[str, float], budget: int) -> tuple[dict[str, int], bool]:
    """Round to whole stats in 1-10; if the total exceeds `budget`, shrink proportionally."""
    rounded = {k: max(1, min(10, round(v))) for k, v in stats.items()}
    total = sum(rounded.values())
    if total <= budget:
        return rounded, False
    factor = budget / total
    fitted = {k: max(1, round(v * factor)) for k, v in rounded.items()}
    # rounding can leave us a point or two over: trim the largest stats first
    while sum(fitted.values()) > budget:
        biggest = max(fitted, key=lambda k: (fitted[k], k))
        if fitted[biggest] <= 1:
            break
        fitted[biggest] -= 1
    return fitted, True


def raise_to_floor(stats: dict[str, int], floor: int) -> tuple[dict[str, int], bool]:
    """If the whole stats total less than `floor`, grow them proportionally (each still at most 10) to exactly `floor`."""
    total = sum(stats.values())
    if total >= floor:
        return stats, False
    ideal = {k: min(10.0, v * floor / total) for k, v in stats.items()}
    raised = {k: int(v) for k, v in ideal.items()}
    # hand out the points lost to rounding down, to the stats furthest below their share first
    while sum(raised.values()) < floor:
        room = [k for k in raised if raised[k] < 10]
        if not room:
            break
        raised[max(room, key=lambda k: (ideal[k] - raised[k], k))] += 1
    return raised, True


def pick_rank(entries: list[dict], source_key: str) -> dict | None:
    """The rank that belongs to the queue the stats came from, or None when the player has none.

    `entries` is the league-v4 response; `source_key` is the queue tier key (SOLO / FLEX / NORMAL).
    """
    by_type = {e.get("queueType"): e for e in entries}
    for queue in RANK_FOR_SOURCE.get(source_key, []):
        entry = by_type.get(RANK_QUEUE_TYPES[queue])
        if entry is None or entry.get("tier") not in RANK_TIERS:
            continue
        tier = entry["tier"]
        return {"queue": queue, "tier": tier, "division": None if tier in APEX_TIERS else entry.get("rank"),
                "lp": entry.get("leaguePoints", 0), "wins": entry.get("wins", 0), "losses": entry.get("losses", 0)}
    return None


def analyse(matches: list[dict], puuid: str, budget: int, role: str | None = None, min_games: int = 10,
            queue_ids=None, floor: int = 0) -> Analysis:
    samples = [s for s in (sample_game(m, puuid, queue_ids) for m in matches) if s is not None]
    if len(samples) < min_games:
        raise NotEnoughData(
            f"Only {len(samples)} recent games were found; at least {min_games} are needed to build a player.")
    lane_counts = Counter(s.lane for s in samples if s.lane)
    lane = role or (lane_counts.most_common(1)[0][0] if lane_counts else "MID")
    # use games in the chosen lane when there are enough of them, otherwise all games
    in_lane = [s for s in samples if s.lane == lane]
    used = in_lane if len(in_lane) >= max(3, min_games // 2) else samples

    averaged = {name: mean(s.metrics[name] for s in used) for name in used[0].metrics}
    raw: dict[str, float] = {}
    breakdown: dict[str, list[dict]] = {}
    for stat in STATS:
        parts = []
        breakdown[stat] = []
        for metric in STAT_METRICS[stat]:
            lower = metric.startswith("-")
            name = metric.lstrip("-")
            low, high = BENCHMARKS[name][lane]
            score = scale(averaged[name], low, high, lower_is_better=lower)
            parts.append(score)
            info = METRIC_INFO[name]
            breakdown[stat].append({"metric": name, "label": info["label"], "unit": info["unit"], "how": info["how"],
                                    "value": round(averaged[name], 3), "low": low, "high": high,
                                    "lower_is_better": lower, "score": round(score, 2)})
        raw[stat] = mean(parts)
    stats, fitted = fit_to_budget(raw, budget)
    stats, raised = raise_to_floor(stats, floor)
    before = sum(max(1, min(10, round(v))) for v in raw.values())
    return Analysis(len(samples), lane, dict(lane_counts), {k: round(v, 2) for k, v in raw.items()}, stats, fitted,
                    Counter(s.champion_key for s in samples), breakdown, before, budget, floor, raised)


@dataclass
class SourceChoice:
    tier: dict
    matches: list[dict]
    tried: dict[str, int]       # tier key -> usable games found (for every tier looked at)


def select_source(tiers: list[dict], get_ids, get_match, puuid: str, min_games: int) -> SourceChoice:
    """Pick the first queue tier with at least `min_games` usable games; never mix queues.

    `get_ids(tier)` returns match ids and `get_match(id)` a match document, so this stays free of network code.
    Matches are only downloaded for a tier whose id list is long enough to qualify.
    """
    tried: dict[str, int] = {}
    for tier in tiers:
        ids = get_ids(tier)
        tried[tier["key"]] = len(ids)
        if len(ids) < min_games:
            continue
        usable = []
        for match_id in ids:
            try:
                match = get_match(match_id)
            except RiotNotFound:
                continue          # aged out of Riot's history
            if sample_game(match, puuid, tier["queue_ids"]) is not None:
                usable.append(match)
        tried[tier["key"]] = len(usable)
        if len(usable) >= min_games:
            return SourceChoice(tier, usable, tried)
    counts = ", ".join(f"{t['label'].lower()} {tried.get(t['key'], 0)}" for t in tiers)
    raise NotEnoughData(f"Not enough recent games in a single queue ({counts}); at least {min_games} in one queue are needed.")


def build_pool(analysis: Analysis, mastery: list[dict[str, Any]], to_ours, size: int = 5) -> tuple[list[int], list[int]]:
    """Top champions by ranked games, topped up by mastery. Returns (our champion ids, unmapped Riot keys)."""
    pool: list[int] = []
    unmapped: list[int] = []

    def add(riot_key: int) -> None:
        ours = to_ours(riot_key)
        if ours is None:
            if riot_key not in unmapped:
                unmapped.append(riot_key)
        elif ours not in pool and len(pool) < size:
            pool.append(ours)

    for riot_key, _ in analysis.champion_games.most_common():
        add(riot_key)
    for entry in sorted(mastery, key=lambda e: -e.get("championPoints", 0)):
        add(int(entry["championId"]))
    return pool, unmapped

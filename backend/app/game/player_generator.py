"""Random players, coaches and teams for CPU-managed season teams. Pure Python, no framework or database imports.

Generated teams are sized to the season's rules: each player's stat total stays within the ruleset's player cap
and the five players' sum within its team cap, so a CPU team never breaks the restrictions human teams play under.
`strength` moves the CPU teams below or up to those caps.
"""
from __future__ import annotations

import random
from typing import Iterable, Sequence

from .config import LANES, MANAGEMENT_CONFIG
from .models import Champion

STATS = ("aggr", "aware", "pos", "dmg", "cs")
TEAM_STYLES = ("early", "scaling", "teamfight", "skirmish")
STRENGTHS = ("WEAKER", "EVEN", "STRONGER")

# how much each lane leans on each stat when points are handed out (higher: more points on average)
ROLE_WEIGHTS = {
    "TOP": {"aggr": 1.2, "aware": 1.0, "pos": 1.0, "dmg": 1.0, "cs": 1.1},
    "JUNGLE": {"aggr": 1.2, "aware": 1.3, "pos": 1.0, "dmg": 0.9, "cs": 0.7},
    "MID": {"aggr": 1.0, "aware": 1.0, "pos": 1.1, "dmg": 1.3, "cs": 1.1},
    "BOT": {"aggr": 0.9, "aware": 0.8, "pos": 1.1, "dmg": 1.3, "cs": 1.3},
    "SUPPORT": {"aggr": 1.0, "aware": 1.4, "pos": 1.1, "dmg": 0.7, "cs": 0.5},
}
# share of the ruleset's per-player cap an average CPU player gets
STRENGTH_FACTORS = {"WEAKER": 0.80, "EVEN": 0.90, "STRONGER": 0.98}
COACH_TOTALS = {"WEAKER": 8, "EVEN": 10, "STRONGER": 12}
NO_CAP_REFERENCE = 36           # the per-player reference total when the ruleset sets no cap at all
TOTAL_RANGE = (8, 50)           # a generated player's stat total is kept inside this

NAME_STARTS = ("Ka", "Ze", "Ri", "Vo", "Ny", "Sha", "Dra", "Mi", "Lu", "Fa", "Ky", "Ro", "Xe", "Ta", "Bo", "Je",
               "Qi", "Ar", "El", "Gu", "Sol", "Vex", "Tor", "Hel", "Zy", "Cro", "Pyx", "Ori", "Bel", "Kor")
NAME_ENDS = ("zen", "rox", "mi", "ven", "lo", "ra", "kai", "dex", "nyx", "rin", "vo", "sky", "fang", "ion", "tor",
             "mar", "lis", "bo", "ze", "gon", "ryn", "ka", "dra", "vin", "sa", "x", "th", "ko", "ne", "lux")
TEAM_ADJECTIVES = ("Crimson", "Iron", "Silver", "Shadow", "Storm", "Golden", "Night", "Frost", "Solar", "Ember",
                   "Void", "Thunder", "Jade", "Obsidian", "Royal", "Phantom", "Azure", "Scarlet", "Lunar", "Savage")
TEAM_NOUNS = ("Wolves", "Dragons", "Titans", "Ravens", "Lions", "Vipers", "Knights", "Phoenix", "Sentinels",
              "Tigers", "Hawks", "Kraken", "Spartans", "Reapers", "Bears", "Foxes", "Golems", "Wyverns", "Owls",
              "Serpents")
COACH_TITLES = ("Coach", "Coach", "Coach", "Analyst", "Head Coach")


def distribute(total: int, weights: dict[str, float], rng: random.Random, lo: int = 1, hi: int = 10) -> dict[str, int]:
    """Split `total` points over the stats (each between lo and hi), favouring the higher weights."""
    keys = list(weights)
    total = max(lo * len(keys), min(hi * len(keys), total))
    stats = {k: lo for k in keys}
    for _ in range(total - lo * len(keys)):
        open_keys = [k for k in keys if stats[k] < hi]
        k = rng.choices(open_keys, weights=[weights[k] for k in open_keys])[0]
        stats[k] += 1
    return stats


def champion_pool(lane: str, champions: Sequence[Champion], rng: random.Random, size: int = 5) -> list[int]:
    """`size` different champions usually played in this lane (more popular ones more likely), best first.
    Topped up from any champion when too few list the lane."""
    lane_champs = [c for c in champions if lane in c.roles]
    pool: list[int] = []
    candidates = list(lane_champs)
    while candidates and len(pool) < size:
        pick = rng.choices(candidates, weights=[c.pick_rate + 1.0 for c in candidates])[0]
        pool.append(pick.id)
        candidates.remove(pick)
    rest = [c.id for c in champions if c.id not in pool]
    rng.shuffle(rest)
    return pool + rest[:size - len(pool)]


def _unique(make, taken: set[str], rng: random.Random) -> str:
    for _ in range(50):
        name = make()
        if name.lower() not in taken:
            taken.add(name.lower())
            return name
    name = f"{make()} {rng.randint(2, 99)}"
    taken.add(name.lower())
    return name


def player_name(rng: random.Random, taken: set[str]) -> str:
    return _unique(lambda: rng.choice(NAME_STARTS) + rng.choice(NAME_ENDS), taken, rng)


def generate_player(lane: str, total: int, champions: Sequence[Champion], rng: random.Random,
                    taken_names: set[str] | None = None) -> dict:
    """A player for `lane` whose five stats sum to `total` (kept within 1-10 each)."""
    lo, hi = MANAGEMENT_CONFIG["stat_range"]
    weights = {k: w * rng.uniform(0.7, 1.3) for k, w in ROLE_WEIGHTS[lane].items()}   # no two players alike
    stats = distribute(total, weights, rng, lo, hi)
    return {"name": player_name(rng, taken_names if taken_names is not None else set()), "role": lane,
            "age": rng.randint(17, 28), "region": "TT", **stats,
            "pool": champion_pool(lane, champions, rng, MANAGEMENT_CONFIG["champion_pool_size"])}


def generate_coach(strength: str, rng: random.Random, taken_names: set[str] | None = None) -> dict:
    budget = MANAGEMENT_CONFIG["coach_stat_budget"]
    total = max(2, min(budget, COACH_TOTALS[strength] + rng.randint(-1, 1)))
    stats = distribute(total, {"draft": 1.0, "synergy": 1.0}, rng)
    name = _unique(lambda: f"{rng.choice(COACH_TITLES)} {rng.choice(NAME_STARTS)}{rng.choice(NAME_ENDS)}",
                   taken_names if taken_names is not None else set(), rng)
    return {"name": name, **stats}


def team_identity(rng: random.Random, taken_names: set[str] | None = None) -> dict:
    taken = taken_names if taken_names is not None else set()
    name = _unique(lambda: f"{rng.choice(TEAM_ADJECTIVES)} {rng.choice(TEAM_NOUNS)}", taken, rng)
    logo = "".join(w[0] for w in name.split() if w[0].isalpha()).upper()[:4]
    style1, style2 = rng.sample(TEAM_STYLES, 2)
    focus1, focus2 = rng.sample(LANES, 2)
    return {"name": name, "logo": logo, "region": "TT", "style1": style1, "style2": style2,
            "focus1": focus1, "focus2": focus2}


def reference_total(rules: dict) -> int:
    """The per-player stat total the ruleset allows: its player cap, else the budget of its rank limit."""
    if rules.get("max_player_total") is not None:
        return int(rules["max_player_total"])
    if rules.get("max_rank"):
        return MANAGEMENT_CONFIG["rank_stat_budgets"].get(rules["max_rank"], NO_CAP_REFERENCE)
    return NO_CAP_REFERENCE


def player_totals(rules: dict, strength: str, rng: random.Random) -> list[int]:
    """Stat totals for a team's five players: around the strength's share of the ruleset's cap, never above the
    player cap, and trimmed (strongest first) until the five fit the team cap."""
    lo, hi = TOTAL_RANGE
    cap = min(hi, int(rules["max_player_total"])) if rules.get("max_player_total") is not None else hi
    mean = reference_total(rules) * STRENGTH_FACTORS[strength] * rng.uniform(0.95, 1.05)
    team_cap = rules.get("max_team_total")
    if team_cap is not None:
        mean = min(mean, int(team_cap) / len(LANES))
    totals = [max(lo, min(cap, round(rng.gauss(mean, 2.0)))) for _ in LANES]
    if team_cap is not None:
        while sum(totals) > int(team_cap) and max(totals) > lo:
            totals[totals.index(max(totals))] -= 1
    return totals


def generate_team(rules: dict, strength: str, champions: Sequence[Champion], rng: random.Random,
                  taken_names: Iterable[str] = (), taken_team_names: Iterable[str] = ()) -> dict:
    """A complete team (identity, coach and a player for every lane) that fits the season's rules.
    `taken_names` / `taken_team_names`: names already used in the season (lowercase), so none repeat."""
    if strength not in STRENGTHS:
        raise ValueError(f"strength must be one of {', '.join(STRENGTHS)}")
    names = {n.lower() for n in taken_names}
    team_names = {n.lower() for n in taken_team_names}
    totals = player_totals(rules, strength, rng)
    return {**team_identity(rng, team_names),
            "coach": generate_coach(strength, rng, names),
            "roster": {lane: generate_player(lane, total, champions, rng, names) for lane, total in zip(LANES, totals)}}

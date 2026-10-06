"""Write EXAMPLE champion synergy files so the rest of the project has something to work with.

    python -m scripts.example_synergy

These numbers are estimates, not measurements. They are built from the champion data the game already has
(win rate, damage type and the 1-3 attribute ratings in the seed CSVs) plus a short list of champion pairs that are
widely known to work well together. Every pair gets `games = 0` in champion_synergy.csv, which is how to tell an
estimate from a measured row.

`python -m scripts.champion_synergy` writes the same two files from real ranked games and replaces these.
"""
from __future__ import annotations

import csv
import sys
import zlib
from itertools import combinations
from pathlib import Path

from app.data.loader import load_seed_data
from app.game.models import Champion
from app.integrations.riot.synergy import PAIR_COLUMNS

DATA_DIR = Path(__file__).resolve().parents[2] / "Data"

# Pairs with a well-known combo, in percentage points of win rate above what the two champions manage apart.
KNOWN_PAIRS: dict[tuple[str, str], float] = {
    ("Xayah", "Rakan"): 4.0, ("Master Yi", "Taric"): 4.0, ("Kog Maw", "Lulu"): 3.5, ("Nilah", "Taric"): 3.5,
    ("Lucian", "Nami"): 3.0, ("Yasuo", "Malphite"): 3.0, ("Yasuo", "Diana"): 3.0, ("Twitch", "Lulu"): 3.0,
    ("Samira", "Nautilus"): 3.0, ("Samira", "Rell"): 3.0, ("Caitlyn", "Lux"): 3.0, ("Miss Fortune", "Leona"): 3.0,
    ("Miss Fortune", "Amumu"): 3.0, ("Orianna", "Jarvan IV"): 3.0, ("Senna", "Tahm Kench"): 3.0,
    ("Zeri", "Yuumi"): 3.0, ("Zeri", "Lulu"): 3.0, ("Rengar", "Ivern"): 3.0, ("Jinx", "Lulu"): 2.5,
    ("Kalista", "Thresh"): 2.5, ("Caitlyn", "Morgana"): 2.5, ("Orianna", "Malphite"): 2.5, ("Galio", "Camille"): 2.5,
    ("Ezreal", "Karma"): 2.5, ("Yasuo", "Gragas"): 2.5, ("Yasuo", "Alistar"): 2.5, ("Yone", "Diana"): 2.5,
    ("Twitch", "Yuumi"): 2.5, ("Vayne", "Lulu"): 2.5, ("Samira", "Alistar"): 2.5, ("Draven", "Thresh"): 2.0,
    ("Kai Sa", "Nautilus"): 2.0, ("Aphelios", "Thresh"): 2.0, ("Orianna", "Nocturne"): 2.0, ("Senna", "Seraphine"): 2.0,
    ("Ashe", "Seraphine"): 2.0, ("Jhin", "Xerath"): 2.0, ("Tristana", "Leona"): 2.0, ("Hecarim", "Zilean"): 2.0,
    ("Galio", "Jarvan IV"): 2.0, ("Sivir", "Yuumi"): 2.0, ("Wukong", "Orianna"): 2.0, ("Kennen", "Jarvan IV"): 2.0,
    ("Miss Fortune", "Sejuani"): 2.0, ("Yasuo", "Yone"): -1.5, ("Lux", "Xerath"): -1.0, ("Teemo", "Yuumi"): -1.5,
}
LIMITS = (-3.0, 5.0)


def _fit(a: Champion, b: Champion) -> float:
    """How well two champions cover for each other, from their 1-3 attribute ratings and damage types."""
    score = 0.0
    for x, y in ((a, b), (b, a)):
        if x.sturdiness == 3 and y.damage == 3 and y.sturdiness == 1:
            score += 1.0        # a front line for a fragile carry
        if x.cc == 3 and y.damage == 3:
            score += 0.8        # lockdown for a damage dealer to follow up on
        if x.utility == 3 and y.damage == 3:
            score += 0.8        # shields, heals or buffs on a carry
    if a.sturdiness == 1 and b.sturdiness == 1:
        score -= 0.5            # nobody to stand in front
    if a.damage <= 2 and b.damage <= 2 and a.sturdiness == 3 and b.sturdiness == 3:
        score -= 0.5            # durable, but who deals the damage?
    types = {a.damage_type, b.damage_type}
    if types == {"P", "M"}:
        score += 0.4            # mixed damage is harder to itemise against
    elif len(types) == 1 and "PM" not in types:
        score -= 0.3
    return score


def _jitter(a: str, b: str) -> float:
    """A small fixed offset per pair (-0.3 to +0.3) so the table is not flat. Same every run."""
    return (zlib.crc32(f"{a}|{b}".encode()) % 61 - 30) / 100


def estimate(a: Champion, b: Champion) -> float:
    """Estimated synergy of a pair in percentage points."""
    known = KNOWN_PAIRS.get((a.name, b.name), KNOWN_PAIRS.get((b.name, a.name), 0.0))
    value = known + _fit(a, b) + _jitter(*sorted((a.name, b.name)))
    return max(LIMITS[0], min(LIMITS[1], round(value, 1)))


def build(champions: list[Champion]) -> list[dict]:
    rows = []
    for a, b in combinations(sorted(champions, key=lambda c: c.name), 2):
        expected = (a.win_rate + b.win_rate) / 2
        synergy = estimate(a, b)
        rows.append({"champion_a": a.name, "champion_b": b.name, "games": 0, "wins": 0, "win_rate": "",
                     "expected_win_rate": f"{expected:.1f}", "smoothed_win_rate": f"{expected + synergy:.1f}",
                     "synergy": f"{synergy:+.1f}"})
    return rows


def write(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "champion_synergy.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    names = sorted({r["champion_a"] for r in rows} | {r["champion_b"] for r in rows})
    cell = {}
    for r in rows:
        cell[r["champion_a"], r["champion_b"]] = cell[r["champion_b"], r["champion_a"]] = r["smoothed_win_rate"]
    with (out_dir / "champion_synergy_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["champion"] + names)
        for a in names:
            writer.writerow([a] + [cell.get((a, b), "") for b in names])


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0]) if argv else DATA_DIR
    champions = load_seed_data().champions
    known = {c.name for c in champions}
    missing = sorted({n for pair in KNOWN_PAIRS for n in pair} - known)
    rows = build(champions)
    write(rows, out_dir)
    print(f"EXAMPLE data (estimates, not measured): {len(champions)} champions, {len(rows)} pairs.")
    if missing:
        print("Named in the known-pairs list but not in the game, so ignored: " + ", ".join(missing))
    print(f"Wrote {out_dir / 'champion_synergy.csv'} and {out_dir / 'champion_synergy_matrix.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

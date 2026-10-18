"""Write an estimated against-team win rate file until real matchup data has been sampled.

    python -m scripts.estimate_counters

Every pair of champions gets the rate that `scripts.champion_synergy` uses as its prior when it has no games for a
pair: even, shifted by half the difference of the two champions' overall win rates (ChampionStatistics.csv).
games = 0 marks every row as an estimate. The file goes to backend/app/data/seed/champion_counter.csv, the
against-team matrix's seed file: an empty matrix is filled from it when the server starts, or press
"Reset to seed data" on the Against team tab. A real file from `scripts.champion_synergy` replaces it the same way.
"""
from __future__ import annotations

import csv
from itertools import combinations
from pathlib import Path

from app.data.loader import SEED_DIR, load_seed_data
from app.data.matchup_seed import SEED_FILES
from app.integrations.riot.synergy import PAIR_COLUMNS


def expected_versus(rate_a: float, rate_b: float) -> float:
    """Champion a's estimated win rate (percent) against b, from their overall win rates (percent)."""
    return 50.0 + (rate_a - rate_b) / 2


def write_estimates(path: Path = SEED_DIR / SEED_FILES["enemy"]) -> int:
    champions = sorted(load_seed_data().champions, key=lambda c: c.name)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PAIR_COLUMNS)
        rows = 0
        for a, b in combinations(champions, 2):
            rate = f"{expected_versus(a.win_rate, b.win_rate):.1f}"
            writer.writerow([a.name, b.name, 0, 0, "", rate, rate, "+0.0"])
            rows += 1
    return rows


if __name__ == "__main__":
    target = SEED_DIR / SEED_FILES["enemy"]
    count = write_estimates(target)
    print(f"Wrote {count} estimated pairs to {target}")
    print("Restart the server to seed an empty Against team matrix from it, or press 'Reset to seed data' there.")

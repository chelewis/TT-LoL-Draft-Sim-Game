"""Balance suite (spec section 14): run many seeded simulations and print summary statistics.

    python -m scripts.balance [N]
"""
from __future__ import annotations

import random
import statistics
import sys

from app.data.loader import load_seed_data, seed_team_setup
from app.game.config import LANES, simulation_config
from app.game.simulation_engine import simulate_match


def _pct(n, d):
    return f"{100.0 * n / d:5.1f}%" if d else "  n/a"


def run(n: int = 1000, overrides: dict | None = None, quiet: bool = False) -> dict:
    seed = load_seed_data()
    champs = {c.id: c for c in seed.champions}
    cfg = simulation_config(overrides)
    rng = random.Random(2024)
    ids = list(champs)

    def lineup(exclude=()):
        return dict(zip(LANES, rng.sample([i for i in ids if i not in exclude], 5)))

    # ---- scenario 1: random drafts, team 1 (blue) vs team 2 (red) and sides swapped
    durations, nexus, blue_wins, t1_wins, kills, towers = [], 0, 0, 0, [], []
    min_duration = 10**9
    for i in range(n):
        bl = lineup(); rl = lineup(bl.values())
        swap = i % 2 == 1
        a, b = (2, 1) if swap else (1, 2)
        res = simulate_match(seed_team_setup(seed, a, bl), seed_team_setup(seed, b, rl), champs, 1000 + i, cfg)
        durations.append(res.duration_seconds / 60)
        nexus += res.win_condition == "NEXUS"
        blue_wins += res.winner == "BLUE"
        t1_winner = (res.winner == "BLUE") != swap
        t1_wins += t1_winner
        kills.append(res.teams["BLUE"]["kills"] + res.teams["RED"]["kills"])
        towers.append(res.teams["BLUE"]["towers"] + res.teams["RED"]["towers"])
        min_duration = min(min_duration, res.duration_seconds)
    out = {
        "nexus_rate": nexus / n, "median_min": statistics.median(durations),
        "p10": sorted(durations)[n // 10], "p90": sorted(durations)[9 * n // 10],
        "blue_rate": blue_wins / n, "team1_rate": t1_wins / n,
    }

    # ---- scenario 2: comfort. team1 on best-pool picks vs team1 off-pool, same opponent lineups
    comfort_wins = 0
    m = max(n // 2, 100)
    for i in range(m):
        bl = lineup()
        pools = {lane: seed.pools[seed.rosters[1][lane]] for lane in LANES}
        good = {lane: pools[lane][0] for lane in LANES}
        if len(set(good.values())) < 5:
            continue
        rl = lineup(good.values())
        off = dict(zip(LANES, rng.sample([c for c in ids if c not in set(rl.values()) and all(c not in p for p in pools.values())], 5)))
        r1 = simulate_match(seed_team_setup(seed, 1, good), seed_team_setup(seed, 2, rl), champs, 5000 + i, cfg)
        r2 = simulate_match(seed_team_setup(seed, 1, off), seed_team_setup(seed, 2, rl), champs, 5000 + i, cfg)
        comfort_wins += (r1.winner == "BLUE") - (r2.winner == "BLUE")
    out["comfort_edge"] = comfort_wins / m

    if not quiet:
        print(f"games={n}  nexus endings={_pct(nexus, n)}  duration min/median/p10/p90 = "
              f"{min_duration/60:.1f}/{out['median_min']:.1f}/{out['p10']:.1f}/{out['p90']:.1f}")
        print(f"blue side win={_pct(blue_wins, n)}  team1 win={_pct(t1_wins, n)}  "
              f"avg kills={statistics.mean(kills):.1f}  avg towers={statistics.mean(towers):.1f}")
        print(f"comfort: win-rate difference best-pool vs off-pool lineups (same opponent & seed) = {out['comfort_edge']:+.2f}")
    return out


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)

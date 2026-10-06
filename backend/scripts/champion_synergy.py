"""Build a matrix of champion win rates when paired on the same team, from real ranked solo games.

    python -m scripts.champion_synergy                    # fetch 3000 new matches (about an hour), then write the files
    python -m scripts.champion_synergy --matches 50       # a short run
    python -m scripts.champion_synergy --aggregate-only   # rebuild the files from the cache, no Riot calls

Riot has no aggregate statistics, so this samples: it lists the players of one tier and division, reads their
recent games through match-v5 and counts same-team pairs. Matches are cached in Data/cache/, so every run adds to
the earlier ones; a pair needs many games before its number means anything, so run it several times.

Uses the server's Riot key (LDM_RIOT_API_KEY). While it runs it takes the key's whole rate limit, so Riot imports
in the app will be refused. Stop it with Ctrl+C at any time: what was fetched is kept and the files are written.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.data.loader import load_seed_data
from app.integrations.riot import ddragon
from app.integrations.riot.client import RiotClient
from app.integrations.riot.config import PLATFORM_CLUSTER
from app.integrations.riot.errors import RiotError, RiotNotFound, RiotRateLimited
from app.integrations.riot.limiter import RateLimiter
from app.integrations.riot.synergy import SOLO_QUEUE, aggregate, reduce_match, write_matrix_csv, write_pairs_csv

DATA_DIR = Path(__file__).resolve().parents[2] / "Data"
TIERS = ("IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND")     # league-v4 pages stop at Diamond
DIVISIONS = ("I", "II", "III", "IV")
IDS_PER_PLAYER = 20


class MatchCache:
    """Reduced matches in a JSON-lines file. Match ids that were looked at and rejected are remembered too,
    so a later run does not download them again."""

    def __init__(self, path: Path):
        self.path = path
        self.seen: set[str] = set()
        self.records: list[dict] = []
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        self._remember(json.loads(line))

    def _remember(self, entry: dict) -> None:
        self.seen.add(entry["id"])
        if not entry.get("skip"):
            self.records.append(entry)

    def add(self, match_id: str, record: dict | None) -> None:
        entry = {**record, "id": match_id} if record else {"id": match_id, "skip": True}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
        self._remember(entry)


def _patiently(call, *args, sleep=time.sleep, attempts: int = 10, **kwargs):
    """Riot's own limiter can still say no (the key may be in use elsewhere): wait and try again."""
    for attempt in range(attempts):
        try:
            return call(*args, **kwargs)
        except RiotRateLimited:
            if attempt == attempts - 1:
                raise
            sleep(30)


def crawl(client, cache: MatchCache, *, region: str, tier: str, division: str, target: int, start_time: int,
          log=print, sleep=time.sleep) -> int:
    """Fetch up to `target` matches that are not in the cache yet. Returns how many usable ones were added."""
    added = 0
    page = 1
    while added < target:
        entries = _patiently(client.league_entries_page, region, tier, division, page, sleep=sleep)
        if not entries:
            log(f"No more players in {tier} {division}; stopping at {added} new matches.")
            break
        for entry in entries:
            puuid = entry.get("puuid")
            if not puuid:
                continue
            ids = _patiently(client.match_ids, region, puuid, IDS_PER_PLAYER, sleep=sleep,
                             queue=SOLO_QUEUE, startTime=start_time)
            for match_id in ids:
                if match_id in cache.seen:
                    continue
                try:
                    record = reduce_match(_patiently(client.match, region, match_id, sleep=sleep))
                except RiotNotFound:
                    record = None
                cache.add(match_id, record)
                if record is None:
                    continue
                added += 1
                if added % 100 == 0:
                    log(f"  {added} / {target} new matches ({len(cache.records)} in the cache)")
                if added >= target:
                    return added
        page += 1
    return added


def _ddragon_json(url: str):
    """Data Dragon is a static CDN: no key and no rate limit, so --aggregate-only works without a key."""
    res = httpx.get(url, timeout=20.0)
    res.raise_for_status()
    return res.json()


def champion_namer(fetch_json) -> tuple:
    """Returns (riot key -> our champion name or None, riot key -> Riot's display name)."""
    ours = {c.id: c.name for c in load_seed_data().champions}
    mapper = ddragon.ChampionMapper(ddragon.load_riot_champions(fetch_json),
                                    {ddragon.normalise(name): cid for cid, name in ours.items()})
    return (lambda key: ours.get(mapper.to_ours(key))), mapper.riot_name


def write_outputs(cache: MatchCache, to_name, riot_name, out_dir: Path, min_games: int, log=print) -> None:
    if not cache.records:
        log("No matches in the cache, so no files were written.")
        return
    table = aggregate(cache.records, to_name)
    pairs = write_pairs_csv(table, out_dir / "champion_synergy.csv")
    filled = write_matrix_csv(table, out_dir / "champion_synergy_matrix.csv", min_games)
    possible = len(table.champions) * (len(table.champions) - 1) // 2
    patches = ", ".join(f"{v} ({n})" for v, n in sorted(table.versions.items(), key=lambda item: -item[1]))
    log(f"{table.matches} matches, patches: {patches}")
    log(f"{len(table.champions)} champions, {pairs} of {possible} pairs seen at least once, "
        f"{filled} with {min_games}+ games (the rest are blank in the matrix)")
    if table.unmapped:
        log("Not in this game, so left out: " + ", ".join(sorted(riot_name(k) for k in table.unmapped)))
    log(f"Wrote {out_dir / 'champion_synergy.csv'} and {out_dir / 'champion_synergy_matrix.csv'}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Sample ranked games and write same-team champion pair win rates.")
    parser.add_argument("--region", default="EUW1", type=str.upper, choices=sorted(PLATFORM_CLUSTER))
    parser.add_argument("--tier", default="EMERALD", type=str.upper, choices=TIERS)
    parser.add_argument("--division", default="I", type=str.upper, choices=DIVISIONS)
    parser.add_argument("--matches", default=3000, type=int, help="new matches to fetch in this run")
    parser.add_argument("--days", default=30, type=int, help="only games newer than this many days")
    parser.add_argument("--min-games", default=5, type=int, help="pairs with fewer games are blank in the matrix")
    parser.add_argument("--aggregate-only", action="store_true", help="rebuild the files from the cache without calling Riot")
    parser.add_argument("--out", default=DATA_DIR, type=Path, help="folder for the two CSV files and the cache")
    args = parser.parse_args(argv)

    cache = MatchCache(args.out / "cache" / "synergy_matches.jsonl")
    print(f"{len(cache.records)} matches already in the cache.")
    status = 0
    if not args.aggregate_only and args.matches > 0:
        if not settings.riot_api_key:
            print("LDM_RIOT_API_KEY is not set. Put a Riot API key in backend/.env.")
            return 1
        # wait out the two-minute window instead of failing fast like the web app does
        client = RiotClient(settings.riot_api_key, limiter=RateLimiter(max_wait=130.0), timeout=20.0)
        print(f"Fetching up to {args.matches} new matches from {args.region} {args.tier} {args.division} "
              f"(about {max(1, round(args.matches * 1.1 / 50))} minutes). Ctrl+C stops and keeps what was fetched.")
        try:
            added = crawl(client, cache, region=args.region, tier=args.tier, division=args.division,
                          target=args.matches, start_time=int(time.time()) - args.days * 86400)
            print(f"Added {added} matches.")
        except KeyboardInterrupt:
            print("\nStopped. Writing the files from what is in the cache.")
        except RiotError as exc:
            print(f"Stopped early: {exc.message}")
            status = 1
        finally:
            client.close()
    try:
        to_name, riot_name = champion_namer(_ddragon_json)
    except httpx.HTTPError as exc:
        print(f"Could not load champion names from Riot's Data Dragon: {exc}")
        return 1
    write_outputs(cache, to_name, riot_name, args.out, args.min_games)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

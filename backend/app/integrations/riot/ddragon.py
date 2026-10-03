"""Riot champion identity (Data Dragon) -> our champion ids."""
from __future__ import annotations

import threading
import time

from .config import CHAMPION_ALIASES

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPIONS_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"


def normalise(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


class ChampionMapper:
    """Maps Riot champion keys (the numeric `championId` in matches) to our champion ids."""

    def __init__(self, riot_champions: dict[str, dict], our_champions: dict[str, int]):
        """riot_champions: Data Dragon `data` (id, key, name). our_champions: normalised name -> our id."""
        self._by_key: dict[int, int] = {}
        self._riot_names: dict[int, str] = {}
        for entry in riot_champions.values():
            riot_key = int(entry["key"])
            self._riot_names[riot_key] = entry["name"]
            for candidate in (normalise(entry["name"]), normalise(entry["id"])):
                candidate = CHAMPION_ALIASES.get(candidate, candidate)
                if candidate in our_champions:
                    self._by_key[riot_key] = our_champions[candidate]
                    break

    def to_ours(self, riot_key: int) -> int | None:
        return self._by_key.get(riot_key)

    def riot_name(self, riot_key: int) -> str:
        return self._riot_names.get(riot_key, f"champion {riot_key}")


_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
CACHE_SECONDS = 6 * 3600


def load_riot_champions(fetch_json) -> dict[str, dict]:
    """Latest Data Dragon champion table, cached in memory for a few hours."""
    with _lock:
        hit = _cache.get("champions")
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        version = fetch_json(VERSIONS_URL)[0]
        data = fetch_json(CHAMPIONS_URL.format(version=version))["data"]
        _cache["champions"] = (time.monotonic(), data)
        return data


def clear_cache() -> None:
    with _lock:
        _cache.clear()

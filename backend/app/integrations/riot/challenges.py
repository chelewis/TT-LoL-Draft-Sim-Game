"""The Riot challenge catalogue (names, descriptions, levels), cached in memory. Used by the admin tag editor."""
from __future__ import annotations

import threading
import time

from .config import CHALLENGE_LEVELS

CACHE_SECONDS = 24 * 3600
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def _name(entry: dict) -> tuple[str, str]:
    names = entry.get("localizedNames") or {}
    loc = names.get("en_US") or next(iter(names.values()), {})
    return loc.get("name") or f"Challenge {entry.get('id')}", loc.get("description") or loc.get("shortDescription") or ""


def simplify(config: list[dict]) -> list[dict]:
    """Riot's challenges/config -> [{id, name, description, levels}] for challenges that can be progressed,
    sorted by name. `levels` are the levels that exist for that challenge, lowest first."""
    out = []
    for entry in config:
        if entry.get("state") not in (None, "ENABLED"):
            continue
        name, description = _name(entry)
        thresholds = entry.get("thresholds") or {}
        out.append({"id": int(entry["id"]), "name": name, "description": description,
                    "levels": [lvl for lvl in CHALLENGE_LEVELS if lvl in thresholds]})
    out.sort(key=lambda c: (c["name"].lower(), c["id"]))
    return out


def load(fetch_config) -> list[dict]:
    """The simplified catalogue. `fetch_config()` returns Riot's challenges/config; called at most once a day."""
    with _lock:
        hit = _cache.get("config")
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    data = simplify(fetch_config())
    with _lock:
        _cache["config"] = (time.monotonic(), data)
    return data


def clear_cache() -> None:
    with _lock:
        _cache.clear()

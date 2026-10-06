"""Thin Riot API client: routing, rate limiting, retries and error mapping."""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx

from .config import PLATFORM_CLUSTER
from .errors import RiotAuthError, RiotNotConfigured, RiotNotFound, RiotRateLimited, RiotUnavailable
from .limiter import RateLimiter

# one limiter per process: the key's limits are shared by every request
_shared_limiter = RateLimiter()


class RiotClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None,
                 limiter: RateLimiter | None = None, sleep=time.sleep, timeout: float = 10.0):
        if not api_key:
            raise RiotNotConfigured("Riot import is not configured on this server.")
        self._http = httpx.Client(headers={"X-Riot-Token": api_key}, transport=transport, timeout=timeout)
        self._limiter = limiter or _shared_limiter
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    # ---------------------------------------------------------------- core
    def _get(self, url: str, params: dict | None = None) -> Any:
        for attempt in (1, 2):
            self._limiter.acquire()
            try:
                res = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                raise RiotUnavailable("Could not reach Riot's servers. Please try again shortly.") from exc
            if res.status_code == 200:
                return res.json()
            if res.status_code == 404:
                raise RiotNotFound("Riot has no record of that.")
            if res.status_code in (401, 403):
                raise RiotAuthError("The server's Riot API key is missing, invalid or expired.")
            if res.status_code == 429:
                retry_after = float(res.headers.get("Retry-After", "1") or 1)
                if attempt == 1 and retry_after <= 5:
                    self._sleep(retry_after)
                    continue
                raise RiotRateLimited(f"Riot is rate limiting us. Try again in about {int(retry_after) + 1} seconds.")
            if res.status_code >= 500:
                raise RiotUnavailable("Riot's servers are having problems. Please try again later.")
            raise RiotUnavailable(f"Unexpected response from Riot ({res.status_code}).")
        raise RiotRateLimited("Riot is rate limiting us. Please try again shortly.")

    @staticmethod
    def cluster(platform: str) -> str:
        try:
            return PLATFORM_CLUSTER[platform]
        except KeyError as exc:
            raise RiotNotFound(f"Unknown region {platform!r}.") from exc

    # ----------------------------------------------------------- endpoints
    def account_by_riot_id(self, platform: str, game_name: str, tag_line: str) -> dict:
        host = self.cluster(platform)
        return self._get(f"https://{host}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
                         f"{quote(game_name, safe='')}/{quote(tag_line, safe='')}")

    def account_by_puuid(self, platform: str, puuid: str) -> dict:
        host = self.cluster(platform)
        return self._get(f"https://{host}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{quote(puuid, safe='')}")

    def match_ids(self, platform: str, puuid: str, count: int, **filters) -> list[str]:
        """Recent match ids, newest first. `filters` are match-v5 query filters such as queue=420 or type='normal'."""
        host = self.cluster(platform)
        return self._get(f"https://{host}.api.riotgames.com/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids",
                         params={**filters, "start": 0, "count": count})

    def match(self, platform: str, match_id: str) -> dict:
        host = self.cluster(platform)
        return self._get(f"https://{host}.api.riotgames.com/lol/match/v5/matches/{quote(match_id, safe='')}")

    def top_mastery(self, platform: str, puuid: str, count: int = 10) -> list[dict]:
        return self._get(f"https://{platform.lower()}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/"
                         f"by-puuid/{quote(puuid, safe='')}/top", params={"count": count})

    def league_entries(self, platform: str, puuid: str) -> list[dict]:
        """Current ranked standing, one entry per ranked queue. An unranked account gives an empty list."""
        return self._get(f"https://{platform.lower()}.api.riotgames.com/lol/league/v4/entries/by-puuid/"
                         f"{quote(puuid, safe='')}")

    def league_entries_page(self, platform: str, tier: str, division: str, page: int = 1,
                            queue: str = "RANKED_SOLO_5x5") -> list[dict]:
        """One page of the players in a tier and division (Iron to Diamond). An empty list means no more pages."""
        return self._get(f"https://{platform.lower()}.api.riotgames.com/lol/league/v4/entries/"
                         f"{quote(queue, safe='')}/{quote(tier, safe='')}/{quote(division, safe='')}",
                         params={"page": page})

    def ddragon_json(self, url: str) -> Any:
        """Data Dragon is a static CDN: no key and no rate limit."""
        try:
            res = httpx.get(url, timeout=10.0)
            res.raise_for_status()
            return res.json()
        except httpx.HTTPError as exc:
            raise RiotUnavailable("Could not load champion data from Riot.") from exc

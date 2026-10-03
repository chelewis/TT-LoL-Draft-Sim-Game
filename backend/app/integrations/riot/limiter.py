"""Sliding-window rate limiter matching Riot's personal key limits (20 / 1 s and 100 / 2 min)."""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from .errors import RiotRateLimited


class RateLimiter:
    def __init__(self, windows: tuple[tuple[int, float], ...] = ((20, 1.0), (100, 120.0)),
                 max_wait: float = 8.0, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.windows = windows
        self.max_wait = max_wait
        self._clock = clock
        self._sleep = sleep
        self._hits: list[deque[float]] = [deque() for _ in windows]
        self._lock = threading.Lock()

    def _wait_needed(self, now: float) -> float:
        wait = 0.0
        for (limit, span), hits in zip(self.windows, self._hits):
            while hits and now - hits[0] >= span:
                hits.popleft()
            if len(hits) >= limit:
                wait = max(wait, span - (now - hits[0]))
        return wait

    def acquire(self) -> None:
        """Block until a request may be sent. Raises RiotRateLimited if that would take too long,
        so a burst of imports fails fast instead of tying up worker threads."""
        with self._lock:
            wait = self._wait_needed(self._clock())
            if wait > self.max_wait:
                raise RiotRateLimited(
                    f"Riot's rate limit has been reached. Please try again in about {int(wait) + 1} seconds.")
            if wait > 0:
                self._sleep(wait)
            now = self._clock()
            for hits in self._hits:
                hits.append(now)

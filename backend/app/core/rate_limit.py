"""Tiny in-memory sliding-window rate limiter for the auth endpoints.

Good enough for a single process; swap for Redis when the API is scaled out.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def auth_rate_limit(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = settings.auth_rate_window_seconds
    hits = _hits[key]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= settings.auth_rate_limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    hits.append(now)

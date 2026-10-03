"""Single source of 'now' (naive UTC) so tests can control time."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    """Format a naive-UTC datetime as an ISO-8601 string with a trailing Z."""
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"

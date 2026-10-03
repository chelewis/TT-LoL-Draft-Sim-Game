"""Gameplay analytics events (spec section 38).

Events are written as structured log lines so they can later be shipped to an analytics system.
Analytics never affects gameplay: failures are swallowed.
"""
from __future__ import annotations

import logging

_log = logging.getLogger("analytics")


def track(event: str, **fields) -> None:
    try:
        detail = " ".join(f"{k}={v}" for k, v in fields.items())
        _log.info("event=%s %s", event, detail)
    except Exception:  # pragma: no cover - analytics must never break a request
        pass

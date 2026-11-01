"""The import seal: a signed record of what a Riot import produced, kept on the player (spec 19.2).

Comparing a player with its seal tells whether it is a genuine import and whether anything that affects its
strength was changed since. The seal binds the Riot account and the imported values, not the player row, so a
copy of the player (e.g. a future share feature) stays verifiable as long as the seal is copied with it.

Free to change: name, age, region, secondary role (and any flavour text). An edit is a different primary role or
stat, changing or reordering an imported pool champion (filling slots the import left empty is fine), or dropping
a suggested weakness tag.
"""
from __future__ import annotations

import jwt

from app.core.config import settings
from app.models import Player

STATS = ("aggr", "aware", "pos", "dmg", "cs")
VERSION = 1


def _key() -> str:
    return settings.riot_seal_key or settings.secret_key


def make_seal(ref: dict) -> str | None:
    """Seal a decoded `riot_ref` token. None for tokens from before baselines existed."""
    base = ref.get("baseline")
    if not base:
        return None
    rank = ref.get("rank") or {}
    payload = {"typ": "riot_seal", "v": VERSION, "puuid": ref["puuid"], "region": ref["region"],
               "source": ref.get("source"), "games": ref.get("games"), "rank_tier": rank.get("tier"),
               "role": base["role"], **{s: int(base[s]) for s in STATS}, "pool": [int(c) for c in base["pool"]],
               "suggested_tags": list(base.get("suggested_tags") or []),
               "negative_tags": list(base.get("negative_tags") or [])}
    return jwt.encode(payload, _key(), algorithm="HS256")


def read_seal(token: str | None) -> dict | None:
    """The seal's contents, or None when there is none or it does not verify."""
    if not token:
        return None
    try:
        data = jwt.decode(token, _key(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return data if data.get("typ") == "riot_seal" and data.get("v") == VERSION else None


def check(player: Player) -> dict:
    """{status, edited_fields, original} for a player view.

    status: "none" (not imported from Riot), "unverified" (imported, but there is no valid seal for this account:
    an import from before seals, a tampered record or a changed signing key; a refresh from Riot fixes it),
    "edited" or "unedited".
    """
    if not player.riot_puuid:
        return {"status": "none", "edited_fields": [], "original": None}
    seal = read_seal(player.riot_seal)
    if seal is None or seal["puuid"] != player.riot_puuid or seal.get("rank_tier") != player.riot_rank_tier:
        return {"status": "unverified", "edited_fields": [], "original": None}

    edited = []
    if player.role != seal["role"]:
        edited.append("role")
    edited += [s for s in STATS if getattr(player, s) != seal[s]]
    if player.pool[:len(seal["pool"])] != seal["pool"]:
        edited.append("pool")
    kept = set(player.playstyle_tags or [])
    if any(k not in kept for k in seal["negative_tags"]):
        edited.append("tags")
    original = {"role": seal["role"], **{s: seal[s] for s in STATS}, "pool": seal["pool"],
                "negative_tags": seal["negative_tags"]}
    return {"status": "edited" if edited else "unedited", "edited_fields": edited, "original": original}

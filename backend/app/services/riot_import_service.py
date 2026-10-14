"""Build a draft player from a real Riot account (preview only: nothing is saved here).

The user reviews and edits the preview, then saves through the normal player endpoints. The preview
carries a signed `riot_ref` token so the server never has to trust a puuid sent by the browser.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request
from app.game.config import LANES, MANAGEMENT_CONFIG
from app.integrations.riot import ddragon, stat_mapper
from app.integrations.riot.client import RiotClient
from app.integrations.riot.config import MATCH_COUNT, MIN_GAMES, PLATFORM_CLUSTER, QUEUE_TIERS
from app.integrations.riot.errors import RiotError, RiotNotFound, RiotRateLimited
from app.models import Champion, Player
from app.services.team_management_service import stat_budget, stat_floor

_cache: dict[tuple, tuple[float, dict]] = {}
_last_import: dict[int, float] = {}
_lock = threading.Lock()


def reset_state() -> None:
    """Clear caches and cooldowns (used by tests)."""
    with _lock:
        _cache.clear()
        _last_import.clear()
    ddragon.clear_cache()


# ------------------------------------------------------------ signed token
def make_riot_ref(user_id: int, puuid: str, game_name: str, tag_line: str, region: str,
                  source: str | None = None, games: int | None = None, rank: dict | None = None) -> str:
    payload = {"typ": "riot_ref", "uid": user_id, "puuid": puuid, "game_name": game_name, "tag_line": tag_line,
               "region": region, "source": source, "games": games, "rank": rank,
               "exp": datetime.now(timezone.utc) + timedelta(hours=2)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_riot_ref(token: str, user_id: int) -> dict:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise bad_request("The Riot import has expired. Please import the account again.") from exc
    if data.get("typ") != "riot_ref" or data.get("uid") != user_id:
        raise bad_request("That Riot import does not belong to you.")
    return data


# ---------------------------------------------------------------- preview
def parse_riot_id(text: str) -> tuple[str, str]:
    name, sep, tag = text.strip().rpartition("#")
    if not sep or not name.strip() or not tag.strip():
        raise bad_request("Enter a Riot ID like GameName#TAG.")
    return name.strip(), tag.strip().lstrip("#")


def _our_champions(db: Session) -> dict[str, int]:
    return {ddragon.normalise(c.name): c.id for c in db.scalars(select(Champion).where(Champion.enabled.is_(True)))}


def _cooldown(user_id: int) -> None:
    wait = settings.riot_user_cooldown_seconds
    with _lock:
        last = _last_import.get(user_id)
        now = time.monotonic()
        if last is not None and now - last < wait:
            raise RiotRateLimited(f"Please wait {int(wait - (now - last)) + 1} seconds before importing again.")
        _last_import[user_id] = now


def preview(db: Session, client: RiotClient, user_id: int, riot_id: str | None = None, region: str = "NA1",
            role: str | None = None, puuid: str | None = None) -> dict:
    """Analyse a Riot account. Give either `riot_id` ("Name#TAG") or a known `puuid` (for refreshes)."""
    region = region.upper()
    if region not in PLATFORM_CLUSTER:
        raise bad_request(f"Unknown region {region!r}.")
    if role is not None and role not in LANES:
        raise bad_request(f"Role must be one of {', '.join(LANES)}.")
    game_name = tag_line = ""
    if puuid is None:
        game_name, tag_line = parse_riot_id(riot_id or "")

    cache_key = (region, puuid or f"{game_name.lower()}#{tag_line.lower()}", role)
    with _lock:
        hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < settings.riot_cache_seconds:
            return _with_fresh_ref(hit[1], user_id)

    _cooldown(user_id)
    if puuid is None:
        account = client.account_by_riot_id(region, game_name, tag_line)
    else:
        account = client.account_by_puuid(region, puuid)
    puuid = account["puuid"]
    game_name, tag_line = account.get("gameName", game_name), account.get("tagLine", tag_line)

    # solo queue first, then flex, then normals: the first queue with enough games is used on its own
    choice = stat_mapper.select_source(
        QUEUE_TIERS, lambda tier: client.match_ids(region, puuid, MATCH_COUNT, **tier["params"]),
        lambda match_id: client.match(region, match_id), puuid, MIN_GAMES)
    tier = choice.tier
    try:
        mastery = client.top_mastery(region, puuid)
    except RiotNotFound:
        mastery = []

    try:
        rank = stat_mapper.pick_rank(client.league_entries(region, puuid), tier["key"])
    except RiotNotFound:
        rank = None
    # the rank sets the stat ceiling and floor; an unranked account gets the default ceiling and no floor
    budget = stat_budget(rank["tier"] if rank else None)
    floor = stat_floor(rank["tier"] if rank else None)
    rank_name = " ".join(filter(None, [rank["tier"].title(), rank["division"]])) if rank else "unranked players"

    analysis = stat_mapper.analyse(choice.matches, puuid, budget, role=role,
                                   min_games=MIN_GAMES, queue_ids=tier["queue_ids"], floor=floor)
    riot_champions = ddragon.load_riot_champions(client.ddragon_json)
    mapper = ddragon.ChampionMapper(riot_champions, _our_champions(db))
    pool, unmapped = stat_mapper.build_pool(analysis, mastery, mapper.to_ours, MANAGEMENT_CONFIG["champion_pool_size"])

    source = {"queue": tier["key"], "label": tier["label"], "games": analysis.games, "is_solo": tier["key"] == "SOLO",
              "tried": choice.tried}
    notes = []
    if not source["is_solo"]:
        skipped = ", ".join(f"{t['label'].lower()} ({choice.tried.get(t['key'], 0)} usable games)"
                            for t in QUEUE_TIERS[:QUEUE_TIERS.index(tier)])
        notes.append(f"Not enough {skipped} to build a player, so these stats come from {analysis.games} "
                     f"{tier['noun']}. Treat them as less reliable.")
    if rank is None:
        notes.append(f"No rank was found for this account, so the standard {budget}-point stat ceiling applies "
                     "and there is no stat floor.")
    if analysis.raised_to_floor:
        notes.append(f"Stats were scaled up to the {floor}-point floor for {rank_name} "
                     "(your raw performance was lower).")
    if analysis.fitted_to_budget:
        notes.append(f"Stats were scaled down to fit the {budget}-point ceiling for {rank_name} "
                     "(your raw performance was higher). You can raise them in the editor; the team will then be flagged.")
    if len(pool) < MANAGEMENT_CONFIG["champion_pool_size"]:
        notes.append(f"Only {len(pool)} of this player's champions exist in the game; pick the rest in the editor.")
    if unmapped:
        names = ", ".join(sorted({mapper.riot_name(k) for k in unmapped}))
        notes.append(f"Not in this game, so skipped: {names}.")
    existing = db.scalar(select(Player).where(Player.owner_user_id == user_id, Player.riot_puuid == puuid))
    if existing:
        notes.append(f"You already imported this account as \"{existing.name}\".")

    # suggest the most-played other lane as the secondary role
    others = sorted(((n, l) for l, n in analysis.lane_counts.items() if l != analysis.lane), reverse=True)
    secondary_lane = others[0][1] if others else None

    result = {
        "player": {"name": game_name[:40], "role": analysis.lane, "secondary_role": secondary_lane,
                   "age": 20, "region": region,
                   **analysis.stats, "pool": pool},
        "riot": {"game_name": game_name, "tag_line": tag_line, "region": region},
        "analysis": {"games": analysis.games, "lane_counts": analysis.lane_counts, "raw_stats": analysis.raw_stats,
                     "rank": {**(rank or dict.fromkeys(("queue", "tier", "division", "lp", "wins", "losses"))),
                              "budget": budget, "floor": floor},
                     "fitted_to_budget": analysis.fitted_to_budget, "raised_to_floor": analysis.raised_to_floor,
                     "source": source, "breakdown": analysis.breakdown,
                     "fit": {"budget": analysis.budget, "floor": analysis.floor, "total_before": analysis.total_before_fit,
                             "total_after": sum(analysis.stats.values())},
                     "missing_pool_slots":
                         MANAGEMENT_CONFIG["champion_pool_size"] - len(pool), "notes": notes},
        "_puuid": puuid,
        "_source": source["queue"],
        "_games": analysis.games,
        "_rank": rank,
    }
    with _lock:
        _cache[cache_key] = (time.monotonic(), result)
    return _with_fresh_ref(result, user_id)


def _with_fresh_ref(result: dict, user_id: int) -> dict:
    """Return the preview without internals, with a signed token bound to this user."""
    out = {k: v for k, v in result.items() if not k.startswith("_")}
    r = result["riot"]
    out["riot_ref"] = make_riot_ref(user_id, result["_puuid"], r["game_name"], r["tag_line"], r["region"],
                                    result["_source"], result["_games"], result["_rank"])
    return out


def refresh(db: Session, client: RiotClient, user_id: int, player: Player, role: str | None = None) -> dict:
    if not player.riot_puuid:
        raise bad_request("That player was not imported from Riot.")
    return preview(db, client, user_id, region=player.riot_region or "NA1", role=role or player.role,
                   puuid=player.riot_puuid)


__all__ = ["preview", "refresh", "decode_riot_ref", "RiotError"]

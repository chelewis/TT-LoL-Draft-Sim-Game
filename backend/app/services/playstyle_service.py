"""Playstyle tags: the admin-managed catalogue, rule validation, and the tags shown on players."""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, not_found
from app.data.playstyle_seed import STARTER_TAGS
from app.game.config import LANES, PLAYSTYLE_HOOKS, PLAYSTYLE_MAX_TAGS
from app.integrations.riot import stat_mapper
from app.integrations.riot.config import BENCHMARKS, CHALLENGE_LEVELS, METRIC_INFO, TAG_METRIC_INFO
from app.models import PlaystyleTag, Player
from app.schemas.admin import PlaystyleTagIn

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_CACHE_KEY = "playstyle_catalog"
MATCH_METRICS = {**METRIC_INFO, **TAG_METRIC_INFO}


# ---------------------------------------------------------------- catalogue
def tag_dict(t: PlaystyleTag) -> dict:
    return {"id": t.id, "key": t.key, "label": t.label, "description": t.description, "polarity": t.polarity,
            "source": t.source, "rule": t.rule or {}, "effects": t.effects or [], "enabled": t.enabled,
            "sort_order": t.sort_order}


def catalog(db: Session) -> dict[str, dict]:
    """key -> tag, every tag (enabled or not), in display order. Cached for the life of the session."""
    hit = db.info.get(_CACHE_KEY)
    if hit is None:
        rows = db.scalars(select(PlaystyleTag).order_by(PlaystyleTag.sort_order, PlaystyleTag.id))
        hit = db.info[_CACHE_KEY] = {t.key: tag_dict(t) for t in rows}
    return hit


def enabled_tags(db: Session) -> list[dict]:
    return [t for t in catalog(db).values() if t["enabled"]]


def _forget(db: Session) -> None:
    db.info.pop(_CACHE_KEY, None)


def public_tag(t: dict) -> dict:
    """What players and games see of a tag. The effects travel into game snapshots, so editing a tag later
    never changes a game that has already started."""
    return {"key": t["key"], "label": t["label"], "description": t["description"], "polarity": t["polarity"],
            "effects": [dict(e) for e in t["effects"]]}


def seed_tags(db: Session) -> None:
    """Add the starter tags to an empty table (an admin may since have edited or deleted any of them)."""
    if db.scalar(select(func.count()).select_from(PlaystyleTag)):
        return
    for order, t in enumerate(STARTER_TAGS):
        db.add(PlaystyleTag(**t, enabled=True, sort_order=order * 10))
    db.commit()
    _forget(db)


# ------------------------------------------------------------- player tags
def player_tags(db: Session | None, player: Player) -> tuple[list[dict], list[dict]]:
    """(kept tags, earned tags) for a player view. Disabled or deleted tags are left out of both."""
    if db is None or not player.riot_puuid:
        return [], []
    cat = catalog(db)
    kept = [public_tag(cat[k]) for k in (player.playstyle_tags or []) if k in cat and cat[k]["enabled"]]
    earned = [{**public_tag(cat[e["key"]]), "evidence": e.get("evidence")}
              for e in (player.riot_earned_tags or []) if e.get("key") in cat and cat[e["key"]]["enabled"]]
    return kept, earned


def check_player_tags(db: Session, keys: list[str], earned: list[dict] | None) -> list[str]:
    """Validate the tags a user keeps on a player: at most PLAYSTYLE_MAX_TAGS, no repeats, each one earned
    by the linked Riot account and currently enabled."""
    if len(set(keys)) != len(keys):
        raise bad_request("A playstyle tag can only be added once.")
    if len(keys) > PLAYSTYLE_MAX_TAGS:
        raise bad_request(f"A player can have at most {PLAYSTYLE_MAX_TAGS} playstyle tags.")
    if keys and not earned:
        raise bad_request("Only players imported from Riot can have playstyle tags.")
    cat = catalog(db)
    earned_keys = {e.get("key") for e in earned or []}
    for key in keys:
        if key not in cat or not cat[key]["enabled"]:
            raise bad_request(f"Unknown playstyle tag {key!r}.")
        if key not in earned_keys:
            raise bad_request(f"This Riot account has not earned the \"{cat[key]['label']}\" tag.")
    return keys


def suggest(earned: list[dict]) -> list[str]:
    return stat_mapper.suggest_tags(earned, PLAYSTYLE_MAX_TAGS)


# --------------------------------------------------------------- validation
def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise bad_request(f"{what} must be a number.")
    return float(value)


def _validate_rule(source: str, rule: dict) -> dict:
    if source == "challenge":
        challenges = rule.get("challenges")
        if not isinstance(challenges, list) or not challenges:
            raise bad_request("Pick at least one challenge.")
        clean = []
        for ch in challenges:
            if not isinstance(ch, dict) or isinstance(ch.get("id"), bool) or not isinstance(ch.get("id"), int):
                raise bad_request("Each challenge needs a numeric id.")
            clean.append({"id": ch["id"], "name": str(ch.get("name") or f"Challenge {ch['id']}")[:80]})
        if len({c["id"] for c in clean}) != len(clean):
            raise bad_request("A challenge is listed twice.")
        level = rule.get("min_level")
        if level not in CHALLENGE_LEVELS[1:]:
            raise bad_request(f"Minimum level must be one of {', '.join(CHALLENGE_LEVELS[1:])}.")
        return {"challenges": clean, "min_level": level}
    if source == "match":
        metric = rule.get("metric")
        if metric not in MATCH_METRICS:
            raise bad_request(f"Unknown match stat {metric!r}.")
        op = rule.get("op")
        if op not in (">=", "<="):
            raise bad_request("The comparison must be >= or <=.")
        value = rule.get("value")
        value = None if value is None else _number(value, "The threshold")
        lanes = rule.get("lanes") or {}
        if not isinstance(lanes, dict) or any(lane not in LANES for lane in lanes):
            raise bad_request(f"Lane thresholds must use the lanes {', '.join(LANES)}.")
        lanes = {lane: None if v is None else _number(v, f"The {lane} threshold") for lane, v in lanes.items()}
        if value is None and not any(v is not None for v in lanes.values()):
            raise bad_request("Give a threshold for at least one lane.")
        return {"metric": metric, "op": op, "value": value, "lanes": lanes}
    raise bad_request("Source must be challenge or match.")


def _validate_effects(effects: list[dict]) -> list[dict]:
    if not effects:
        raise bad_request("A tag needs at least one effect.")
    clean, seen = [], set()
    for e in effects:
        hook = e.get("hook")
        if hook not in PLAYSTYLE_HOOKS:
            raise bad_request(f"Unknown effect {hook!r}.")
        if hook in seen:
            raise bad_request("Each effect can only be used once per tag.")
        seen.add(hook)
        value = _number(e.get("value"), "An effect value")
        lo, hi = PLAYSTYLE_HOOKS[hook]["range"]
        if not lo <= value <= hi or value == 0:
            raise bad_request(f"{PLAYSTYLE_HOOKS[hook]['label']} must be between {lo} and {hi}, and not 0.")
        clean.append({"hook": hook, "value": value})
    return clean


def _apply(db: Session, tag: PlaystyleTag, body: PlaystyleTagIn, user_id: int) -> None:
    if not KEY_RE.match(body.key):
        raise bad_request("The key must be 2-32 lower-case letters, digits or _, starting with a letter.")
    clash = db.scalar(select(PlaystyleTag).where(PlaystyleTag.key == body.key))
    if clash is not None and clash.id != tag.id:
        raise bad_request(f"Another tag already uses the key {body.key!r}.")
    if body.polarity not in ("positive", "negative"):
        raise bad_request("Polarity must be positive or negative.")
    tag.key, tag.label, tag.description = body.key, body.label.strip(), body.description.strip()
    tag.polarity, tag.source = body.polarity, body.source
    tag.rule = _validate_rule(body.source, body.rule)
    tag.effects = _validate_effects([e.model_dump() for e in body.effects])
    tag.enabled, tag.sort_order, tag.updated_by_user_id = body.enabled, body.sort_order, user_id


# ------------------------------------------------------------------- admin
def list_all(db: Session) -> list[dict]:
    used = _usage(db)
    return [{**t, "players": used.get(t["key"], 0)} for t in catalog(db).values()]


def _usage(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tags in db.scalars(select(Player.playstyle_tags).where(Player.playstyle_tags.is_not(None))):
        for key in tags or []:
            counts[key] = counts.get(key, 0) + 1
    return counts


def create(db: Session, body: PlaystyleTagIn, user_id: int) -> dict:
    tag = PlaystyleTag()
    _apply(db, tag, body, user_id)
    db.add(tag)
    db.commit()
    _forget(db)
    return tag_dict(tag)


def update(db: Session, tag_id: int, body: PlaystyleTagIn, user_id: int) -> dict:
    tag = db.get(PlaystyleTag, tag_id)
    if tag is None:
        raise not_found()
    old_key = tag.key
    _apply(db, tag, body, user_id)
    if tag.key != old_key:
        _rename_on_players(db, old_key, tag.key)
    db.commit()
    _forget(db)
    return tag_dict(tag)


def _rename_on_players(db: Session, old: str, new: str) -> None:
    for p in db.scalars(select(Player).where(Player.riot_earned_tags.is_not(None))):
        if old in (p.playstyle_tags or []):
            p.playstyle_tags = [new if k == old else k for k in p.playstyle_tags]
        if any(e.get("key") == old for e in p.riot_earned_tags or []):
            p.riot_earned_tags = [{**e, "key": new} if e.get("key") == old else e for e in p.riot_earned_tags]


def delete(db: Session, tag_id: int) -> dict:
    """Delete a tag nobody keeps; a tag kept on players is disabled instead (so it can be turned back on)."""
    tag = db.get(PlaystyleTag, tag_id)
    if tag is None:
        raise not_found()
    in_use = _usage(db).get(tag.key, 0)
    if in_use:
        tag.enabled = False
        db.commit()
        _forget(db)
        return {"deleted": False, "disabled": True, "players": in_use}
    db.delete(tag)
    db.commit()
    _forget(db)
    return {"deleted": True, "disabled": False, "players": 0}


def options(challenge_list: list[dict] | None, challenge_error: str | None = None) -> dict:
    """Everything the admin tag editor offers in its pickers."""
    return {
        "hooks": [{"hook": k, **v} for k, v in PLAYSTYLE_HOOKS.items()],
        "metrics": [{"metric": k, **v, "benchmarks": BENCHMARKS.get(k)} for k, v in MATCH_METRICS.items()],
        "levels": list(CHALLENGE_LEVELS[1:]),
        "lanes": LANES,
        "max_tags": PLAYSTYLE_MAX_TAGS,
        "challenges": challenge_list or [],
        "challenges_error": challenge_error,
    }

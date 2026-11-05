"""Lobby rulesets and the team restrictions they set (max rank, player and team stat totals)."""
from __future__ import annotations

from app.game.config import DEFAULT_RULESET, LANES, LOBBY_RULESETS, LOBBY_RULESETS_BY_KEY
from app.integrations.riot.config import RANK_TIERS

RULE_FIELDS = ("max_rank", "max_player_total", "max_team_total")


def ruleset(key: str | None) -> dict:
    return LOBBY_RULESETS_BY_KEY.get(key or DEFAULT_RULESET, LOBBY_RULESETS_BY_KEY[DEFAULT_RULESET])


def rulesets_view() -> dict:
    return {"rulesets": LOBBY_RULESETS, "rank_tiers": list(RANK_TIERS), "default": DEFAULT_RULESET}


def is_modified(settings: dict, ignore: tuple[str, ...] = ()) -> bool:
    """Whether the lobby's options differ from its ruleset's preset (`ignore`: options the mode overrides)."""
    preset = ruleset(settings.get("ruleset"))["settings"]
    return any(settings.get(k) != v for k, v in preset.items() if k not in ignore)


def rules_of(settings: dict) -> dict:
    """The team restrictions in a lobby's stored options (lobbies from before rulesets have none)."""
    return {k: settings.get(k) for k in RULE_FIELDS}


def _tier_name(tier: str) -> str:
    return tier.title()


def team_rule_issues(team_view: dict, settings: dict) -> list[str]:
    """Why this team (a team_management_service.team_view, or a snapshot with the same roster shape) breaks the
    lobby's restrictions. Empty when it's allowed."""
    rules = rules_of(settings)
    issues: list[str] = []
    players = [p for lane in LANES if (p := (team_view.get("roster") or {}).get(lane))]
    max_rank = rules["max_rank"]
    if max_rank:
        limit = RANK_TIERS.index(max_rank)
        for p in players:
            tier = ((p.get("riot") or {}).get("rank") or {}).get("tier")
            if tier not in RANK_TIERS:
                issues.append(f"{p['name']} has no rank (this lobby only allows ranked players)")
            elif RANK_TIERS.index(tier) > limit:
                issues.append(f"{p['name']} is {_tier_name(tier)}, above the {_tier_name(max_rank)} limit")
    cap = rules["max_player_total"]
    if cap is not None:
        for p in players:
            if p["stat_total"] > cap:
                issues.append(f"{p['name']}'s stats total {p['stat_total']} (limit {cap})")
    team_cap = rules["max_team_total"]
    if team_cap is not None:
        total = sum(p["stat_total"] for p in players)
        if total > team_cap:
            issues.append(f"Team stats total {total} (limit {team_cap})")
    return issues

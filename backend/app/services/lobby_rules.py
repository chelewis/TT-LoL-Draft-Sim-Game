"""Lobby rulesets and the team restrictions they set (max rank, stat totals, duplicate and mirror clauses)."""
from __future__ import annotations

from app.game.config import DEFAULT_RULESET, LANES, LOBBY_RULESETS, LOBBY_RULESETS_BY_KEY
from app.integrations.riot.config import RANK_TIERS

RULE_FIELDS = ("max_rank", "max_player_total", "max_team_total", "duplicate_clause", "mirror_clause")
CLAUSES = ("duplicate_clause", "mirror_clause")


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
    return {k: bool(settings.get(k)) if k in CLAUSES else settings.get(k) for k in RULE_FIELDS}


def player_identity(p: dict) -> tuple[str, str]:
    """Who a rostered player really is: their Riot ID for imports (copies of one account match), else their name."""
    riot = p.get("riot") or {}
    if riot.get("game_name"):
        return ("riot", f"{riot['game_name']}#{riot.get('tag_line') or ''}".lower())
    return ("name", p["name"].strip().lower())


def _describe(identity: tuple[str, str], p: dict) -> str:
    if identity[0] == "riot":
        riot = p["riot"]
        return f"{riot['game_name']}#{riot.get('tag_line') or ''}"
    return p["name"]


def _roster(view: dict | None) -> list[dict]:
    return [p for lane in LANES if (p := ((view or {}).get("roster") or {}).get(lane))]


def mirror_issues(team_view: dict, other_view: dict | None, settings: dict) -> list[str]:
    """With the mirror clause on: the players this team shares with the other side's team."""
    if not rules_of(settings)["mirror_clause"] or not other_view:
        return []
    theirs = {player_identity(p) for p in _roster(other_view)}
    shared = [p for p in _roster(team_view) if player_identity(p) in theirs]
    return [f"{_describe(player_identity(p), p)} is already on the other team (no mirror players)" for p in shared]


def _tier_name(tier: str) -> str:
    return tier.title()


def team_rule_issues(team_view: dict, settings: dict) -> list[str]:
    """Why this team (a team_management_service.team_view, or a snapshot with the same roster shape) breaks the
    lobby's restrictions. Empty when it's allowed."""
    rules = rules_of(settings)
    issues: list[str] = []
    players = _roster(team_view)
    if rules["duplicate_clause"]:
        seen: dict[tuple[str, str], int] = {}
        for p in players:
            seen[player_identity(p)] = seen.get(player_identity(p), 0) + 1
        for p in players:
            ident = player_identity(p)
            if seen.get(ident, 0) > 1:
                what = "Riot account" if ident[0] == "riot" else "player name"
                issues.append(f"{_describe(ident, p)} is on the team {seen[ident]} times (same {what})")
                seen[ident] = 0   # report each duplicate once
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

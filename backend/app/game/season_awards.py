"""Season stats and awards, from the box scores of a season's games. Pure: no database.

Every finished game of a season gives a GameLine; `aggregate` sums them per player, `leaders` ranks the players in
each stat, and `awards` picks the season MVP, the finals MVP and the all-pro team (the best player of each lane).
A player's rating is their average rank score: the same lane-and-KDA score that picks each game's MVP.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

LANES = ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT")
TOTALS = ("kills", "deaths", "assists", "cs", "gold", "damage_dealt")

# (key, label, how many decimals): per-game averages, except the counts
LEADER_CATEGORIES = (
    ("rating", "Rating", 1),
    ("kda", "KDA", 2),
    ("kills_pg", "Kills per game", 1),
    ("assists_pg", "Assists per game", 1),
    ("cs_pg", "CS per game", 0),
    ("damage_pg", "Damage per game", 0),
    ("mvps", "Game MVPs", 0),
)


@dataclass(frozen=True)
class GameLine:
    """One finished game. `sides` maps BLUE/RED to the season team that played there; each player dict is a box
    score line from the match result (player_id, name, team, lane, champion, kills ..., rank_score)."""
    game_id: int
    stage: str                     # REGULAR | SWISS | PLAYOFF
    final: bool                    # a game of the season's final
    winner: str                    # BLUE | RED
    mvp_player_id: int | None
    sides: dict[str, int]
    players: tuple[dict, ...]


@dataclass
class PlayerLine:
    player_id: int
    name: str
    team_id: int                   # the season team they played for most recently
    games: int = 0
    wins: int = 0
    mvps: int = 0
    rating_total: float = 0.0
    totals: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOTALS, 0))
    lanes: Counter = field(default_factory=Counter)
    champions: Counter = field(default_factory=Counter)

    @property
    def lane(self) -> str:
        """The lane they played most (ties: the earlier lane on the map)."""
        if not self.lanes:
            return ""
        return max(LANES, key=lambda l: (self.lanes[l], -LANES.index(l)))

    def per_game(self, key: str) -> float:
        return self.totals[key] / self.games if self.games else 0.0

    @property
    def rating(self) -> float:
        return self.rating_total / self.games if self.games else 0.0

    @property
    def kda(self) -> float:
        return (self.totals["kills"] + self.totals["assists"]) / max(1, self.totals["deaths"])

    def value(self, key: str) -> float:
        return {"rating": self.rating, "kda": self.kda, "kills_pg": self.per_game("kills"),
                "assists_pg": self.per_game("assists"), "cs_pg": self.per_game("cs"),
                "damage_pg": self.per_game("damage_dealt"), "mvps": float(self.mvps)}[key]

    def to_dict(self) -> dict:
        top_champs = [name for name, _ in sorted(self.champions.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
        return {"player_id": self.player_id, "name": self.name, "team_id": self.team_id, "lane": self.lane,
                "games": self.games, "wins": self.wins, "mvps": self.mvps, **self.totals,
                "kda": round(self.kda, 2), "rating": round(self.rating, 1),
                "kills_pg": round(self.per_game("kills"), 1), "assists_pg": round(self.per_game("assists"), 1),
                "deaths_pg": round(self.per_game("deaths"), 1), "cs_pg": round(self.per_game("cs"), 1),
                "damage_pg": round(self.per_game("damage_dealt")), "champions": top_champs}


def aggregate(games: list[GameLine]) -> dict[int, PlayerLine]:
    """Season totals per player id. Games are taken in the order given (oldest first), so a player's team is the
    one they played their latest game for."""
    out: dict[int, PlayerLine] = {}
    for g in games:
        for p in g.players:
            pid = p.get("player_id")
            team_id = g.sides.get(p.get("team"))
            if pid is None or team_id is None:
                continue
            line = out.get(pid)
            if line is None:
                line = out[pid] = PlayerLine(pid, p.get("name") or "?", team_id)
            line.name, line.team_id = p.get("name") or line.name, team_id
            line.games += 1
            line.wins += p.get("team") == g.winner
            line.mvps += g.mvp_player_id == pid
            line.rating_total += float(p.get("rank_score") or 0)
            for k in TOTALS:
                line.totals[k] += int(p.get(k) or 0)
            if p.get("lane"):
                line.lanes[p["lane"]] += 1
            if p.get("champion"):
                line.champions[p["champion"]] += 1
    return out


def min_games(stats: dict[int, PlayerLine]) -> int:
    """To lead a per-game stat or win an award a player must have played half as many games as the most anyone has
    (so a substitute's one big game doesn't top the table)."""
    most = max((s.games for s in stats.values()), default=0)
    return max(1, math.ceil(most / 2)) if most else 0


def _qualified(stats: dict[int, PlayerLine]) -> list[PlayerLine]:
    floor = min_games(stats)
    return [s for s in stats.values() if s.games >= floor and s.games > 0]


def _ranked(players: list[PlayerLine], key: str) -> list[PlayerLine]:
    # ties: more games, then the better rating, then the id (stable)
    return sorted(players, key=lambda s: (-s.value(key), -s.games, -s.rating, s.player_id))


def leaders(stats: dict[int, PlayerLine], top: int = 5) -> list[dict]:
    """The top `top` players in each category, among players with enough games."""
    pool = _qualified(stats)
    out = []
    for key, label, decimals in LEADER_CATEGORIES:
        rows = [s for s in _ranked(pool, key) if key != "mvps" or s.mvps > 0][:top]
        out.append({"key": key, "label": label, "decimals": decimals,
                    "rows": [{"player_id": s.player_id, "name": s.name, "team_id": s.team_id, "lane": s.lane,
                              "games": s.games, "value": round(s.value(key), decimals)} for s in rows]})
    return out


def season_mvp(stats: dict[int, PlayerLine]) -> PlayerLine | None:
    """The best rating among players with enough games; ties: more game MVPs, then more wins."""
    pool = _qualified(stats)
    if not pool:
        return None
    return min(pool, key=lambda s: (-round(s.rating, 3), -s.mvps, -s.wins, s.player_id))


def all_pro(stats: dict[int, PlayerLine]) -> dict[str, PlayerLine | None]:
    """The best-rated player in each lane (by the lane they played most), among players with enough games."""
    pool = _qualified(stats)
    team = {}
    for lane in LANES:
        candidates = [s for s in pool if s.lane == lane]
        team[lane] = min(candidates, key=lambda s: (-round(s.rating, 3), -s.mvps, s.player_id)) if candidates else None
    return team


def finals_mvp(games: list[GameLine], champion_team_id: int | None) -> PlayerLine | None:
    """The champions' best player across the games of the final: most game MVPs there, then the best rating."""
    finals = [g for g in games if g.final]
    if not finals or champion_team_id is None:
        return None
    lines = [s for s in aggregate(finals).values() if s.team_id == champion_team_id]
    if not lines:
        return None
    return min(lines, key=lambda s: (-s.mvps, -round(s.rating, 3), s.player_id))


def awards(games: list[GameLine], champion_team_id: int | None) -> dict:
    stats = aggregate(games)
    mvp = season_mvp(stats)
    fmvp = finals_mvp(games, champion_team_id)
    return {"season_mvp": mvp.to_dict() if mvp else None,
            "finals_mvp": fmvp.to_dict() if fmvp else None,
            "all_pro": [{"lane": lane, "player": p.to_dict() if p else None} for lane, p in all_pro(stats).items()]}

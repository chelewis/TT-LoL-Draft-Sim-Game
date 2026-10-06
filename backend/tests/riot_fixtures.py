"""Synthetic Riot payloads for tests (shaped like match-v5, account-v1 and Data Dragon responses)."""
from __future__ import annotations

# a few real Data Dragon entries: id (internal), key (numeric), name (display)
DDRAGON_CHAMPIONS = {
    "Aatrox": {"id": "Aatrox", "key": "266", "name": "Aatrox"},
    "Ahri": {"id": "Ahri", "key": "103", "name": "Ahri"},
    "Akali": {"id": "Akali", "key": "84", "name": "Akali"},
    "Alistar": {"id": "Alistar", "key": "12", "name": "Alistar"},
    "Amumu": {"id": "Amumu", "key": "32", "name": "Amumu"},
    "Anivia": {"id": "Anivia", "key": "34", "name": "Anivia"},
    "MonkeyKing": {"id": "MonkeyKing", "key": "62", "name": "Wukong"},
    "Nunu": {"id": "Nunu", "key": "20", "name": "Nunu & Willump"},
    "Chogath": {"id": "Chogath", "key": "31", "name": "Cho'Gath"},
    "Zzzfake": {"id": "Zzzfake", "key": "9999", "name": "Brand New Champion"},   # not in our game
}


def participant(puuid: str, team: int, lane: str = "MIDDLE", champion: int = 103, *, kills=5, deaths=3, assists=7,
                cs=190, jungle_cs=10, vision=25, damage=21000, dragons=1, barons=0) -> dict:
    return {"puuid": puuid, "teamId": team, "teamPosition": lane, "individualPosition": lane, "championId": champion,
            "kills": kills, "deaths": deaths, "assists": assists, "totalMinionsKilled": cs,
            "neutralMinionsKilled": jungle_cs, "visionScore": vision, "totalDamageDealtToChampions": damage,
            "dragonKills": dragons, "baronKills": barons}


def make_match(puuid: str, *, lane="MIDDLE", champion=103, minutes=30, mine: dict | None = None, queue=420) -> dict:
    """A 10-player match in which `puuid` plays `lane`; `mine` overrides that player's numbers."""
    me = participant(puuid, 100, lane, champion, **(mine or {}))
    others = [participant(f"other{i}", 100 if i < 4 else 200, "TOP", 266, kills=3, deaths=4, assists=5,
                          damage=15000) for i in range(9)]
    return {"metadata": {"matchId": "NA1_1"},
            "info": {"gameDuration": minutes * 60, "queueId": queue, "participants": [me] + others}}


STRONG = dict(kills=11, deaths=1, assists=9, cs=290, jungle_cs=12, vision=35, damage=34000, dragons=2, barons=1)
WEAK = dict(kills=1, deaths=9, assists=2, cs=110, jungle_cs=4, vision=8, damage=8000, dragons=0, barons=0)


class FakeRiotClient:
    """Stands in for RiotClient in API tests. Records every call so queue fallback and caching can be asserted.

    Game counts per queue: `games` is solo (420), `flex` is 440, `normal` is the `type=normal` list (400/430 games,
    plus `aram` ARAM games mixed in). `remakes` is how many of each queue's newest games are remakes.
    `rank` is the tier in both ranked queues, a {"SOLO": tier, "FLEX": tier} dict, or None for unranked. The default
    is Gold, whose stat ceiling is the standard 32.
    """

    def __init__(self, games=14, champion_cycle=(103, 266, 84, 12, 32, 34, 62, 9999), mine=None, lane="MIDDLE",
                 flex=0, normal=0, aram=0, remakes=None, rank="GOLD"):
        self.calls: list[str] = []
        self.ranks = rank if isinstance(rank, dict) else {"SOLO": rank, "FLEX": rank}
        self.accounts = {("faker", "kr1"): {"puuid": "puuid-faker", "gameName": "Faker", "tagLine": "KR1"}}
        self.queue_games = {"420": games, "440": flex, "normal": normal}
        self.aram = aram
        self.remakes = remakes or {}
        self.champion_cycle = champion_cycle
        self.mine = mine
        self.lane = lane

    @property
    def games(self):
        return self.queue_games["420"]

    @games.setter
    def games(self, value):
        self.queue_games["420"] = value

    def _log(self, name):
        self.calls.append(name)

    def account_by_riot_id(self, platform, game_name, tag_line):
        self._log("account")
        from app.integrations.riot.errors import RiotNotFound
        found = self.accounts.get((game_name.lower(), tag_line.lower()))
        if not found:
            raise RiotNotFound("Riot has no record of that.")
        return found

    def account_by_puuid(self, platform, puuid):
        self._log("account")
        return next(a for a in self.accounts.values() if a["puuid"] == puuid)

    def match_ids(self, platform, puuid, count, queue=None, type=None):
        key = str(queue) if queue else "normal"
        self._log(f"match_ids:{key}")
        ids = [f"{key}_{i}" for i in range(self.queue_games[key])]
        if key == "normal":
            ids += [f"aram_{i}" for i in range(self.aram)]
        return ids[:count]

    def match(self, platform, match_id):
        key, index = match_id.rsplit("_", 1)
        self._log(f"match:{key}")
        index = int(index)
        queue = {"420": 420, "440": 440, "aram": 450}.get(key, 400 if index % 2 == 0 else 430)
        minutes = 3 if index < self.remakes.get(key, 0) else 30
        champion = self.champion_cycle[index % len(self.champion_cycle)]
        return make_match("puuid-faker", lane=self.lane, champion=champion, mine=self.mine, minutes=minutes, queue=queue)

    def top_mastery(self, platform, puuid, count=10):
        self._log("mastery")
        return [{"championId": 266, "championPoints": 900000}, {"championId": 62, "championPoints": 500000}]

    def league_entries(self, platform, puuid):
        self._log("league")
        types = {"SOLO": "RANKED_SOLO_5x5", "FLEX": "RANKED_FLEX_SR"}
        return [{"queueType": types[q], "tier": tier, "rank": "II", "leaguePoints": 45, "wins": 60, "losses": 40}
                for q, tier in self.ranks.items() if tier]

    def ddragon_json(self, url):
        if url.endswith("versions.json"):
            return ["14.1.1"]
        return {"data": DDRAGON_CHAMPIONS}

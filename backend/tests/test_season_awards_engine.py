"""Season stats and awards from box scores (app.game.season_awards)."""
from app.game.season_awards import GameLine, aggregate, all_pro, awards, leaders, min_games, season_mvp

LANES = ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT")


def line(pid, team, lane, kills=2, deaths=2, assists=4, score=50.0, name=None):
    return {"player_id": pid, "name": name or f"P{pid}", "team": team, "lane": lane, "champion": f"C{pid}",
            "kills": kills, "deaths": deaths, "assists": assists, "cs": 200, "gold": 10000, "damage_dealt": 15000,
            "rank_score": score}


def game(gid, players, winner="BLUE", mvp=None, final=False, sides=None):
    return GameLine(game_id=gid, stage="PLAYOFF" if final else "REGULAR", final=final, winner=winner,
                    mvp_player_id=mvp, sides=sides or {"BLUE": 1, "RED": 2}, players=tuple(players))


def full_game(gid, blue_scores, red_scores, winner="BLUE", mvp=None, final=False):
    """Players 1-5 on Blue (team 1) and 6-10 on Red (team 2), one per lane."""
    players = [line(i + 1, "BLUE", lane, score=s) for i, (lane, s) in enumerate(zip(LANES, blue_scores))]
    players += [line(i + 6, "RED", lane, score=s) for i, (lane, s) in enumerate(zip(LANES, red_scores))]
    return game(gid, players, winner, mvp, final)


def test_aggregate_sums_each_player():
    games = [full_game(1, [60] * 5, [40] * 5, mvp=1), full_game(2, [50] * 5, [70] * 5, winner="RED", mvp=6)]
    stats = aggregate(games)
    p1, p6 = stats[1], stats[6]
    assert p1.games == 2 and p1.wins == 1 and p1.mvps == 1 and p1.rating == 55
    assert p6.wins == 1 and p6.mvps == 1 and p6.rating == 55 and p6.team_id == 2
    assert p1.totals["kills"] == 4 and p1.kda == 3.0 and p1.lane == "TOP"
    assert p1.to_dict()["cs_pg"] == 200


def test_a_player_belongs_to_their_latest_team():
    games = [game(1, [line(1, "BLUE", "MID")]), game(2, [line(1, "RED", "MID")], sides={"BLUE": 3, "RED": 4})]
    assert aggregate(games)[1].team_id == 4


def test_leaders_need_enough_games():
    # player 99 plays one great game; the others play four
    games = [full_game(i, [50] * 5, [45] * 5) for i in range(4)]
    games.append(game(9, [line(99, "BLUE", "MID", kills=20, score=99)]))
    stats = aggregate(games)
    assert min_games(stats) == 2
    rating = next(c for c in leaders(stats) if c["key"] == "rating")
    assert 99 not in [r["player_id"] for r in rating["rows"]] and len(rating["rows"]) == 5
    assert next(c for c in leaders(stats) if c["key"] == "mvps")["rows"] == []        # nobody was an MVP


def test_season_mvp_and_all_pro():
    games = [full_game(i, [50, 60, 70, 55, 45], [40, 65, 50, 52, 48], mvp=3) for i in range(3)]
    stats = aggregate(games)
    assert season_mvp(stats).player_id == 3
    team = all_pro(stats)
    assert {lane: p.player_id for lane, p in team.items()} == {"TOP": 1, "JUNGLE": 7, "MID": 3, "BOT": 4, "SUPPORT": 10}


def test_finals_mvp_is_from_the_champions():
    games = [full_game(1, [50] * 5, [60] * 5, winner="BLUE", mvp=2, final=True),
             full_game(2, [50] * 5, [60] * 5, winner="BLUE", mvp=2, final=True),
             full_game(3, [90] * 5, [10] * 5, mvp=1)]                        # not the final
    out = awards(games, champion_team_id=1)
    assert out["finals_mvp"]["player_id"] == 2
    assert awards(games, champion_team_id=None)["finals_mvp"] is None
    assert awards([], None) == {"season_mvp": None, "finals_mvp": None,
                                "all_pro": [{"lane": lane, "player": None} for lane in LANES]}

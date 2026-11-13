"""The pure Player Draft helpers: snake order, pool feasibility and the automatic pick."""
from app.game.season_draft import PoolPlayer, auto_pick, lane_shortfall, pick_problem, snake_order

ALL = ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT")


def p(id_, *lanes, total=30):
    return PoolPlayer(id_, frozenset(lanes), total, lanes[0])


def test_snake_order():
    order = [7, 8, 9]
    assert [snake_order(order, n) for n in range(1, 10)] == [7, 8, 9, 9, 8, 7, 7, 8, 9]


def test_shortfall_counts_each_player_once():
    pool = [p(1, "TOP", "MID"), p(2, "MID")]
    assert lane_shortfall({"TOP": 1, "MID": 1}, pool) == {}
    assert sum(lane_shortfall({"TOP": 1, "MID": 2}, pool).values()) == 1
    assert lane_shortfall({"SUPPORT": 2}, pool) == {"SUPPORT": 2}
    assert lane_shortfall({}, pool) == {}


def test_a_pick_cannot_strand_another_team():
    # the only flexible player is needed at SUPPORT by someone: taking them for BOT would leave a support short
    pool = [p(1, "SUPPORT", "BOT"), p(2, "BOT"), p(3, "SUPPORT")]
    open_lanes = [["BOT"], ["SUPPORT"], ["SUPPORT"]]
    assert "SUPPORT" in pick_problem(pool, open_lanes, 0, 1, "BOT")
    assert pick_problem(pool, open_lanes, 0, 2, "BOT") is None
    assert pick_problem(pool, open_lanes, 0, 3, "SUPPORT") == "Your SUPPORT spot is already filled."
    assert pick_problem(pool, open_lanes, 1, 2, "SUPPORT") == "That player can't play SUPPORT."
    assert pick_problem(pool, open_lanes, 1, 99, "SUPPORT") == "That player isn't available."


def test_auto_pick_takes_the_best_player_that_keeps_the_draft_possible():
    pool = [p(1, "SUPPORT", "BOT", total=40), p(2, "BOT", total=20), p(3, "SUPPORT", total=25)]
    assert auto_pick(pool, [["BOT"], ["SUPPORT"], ["SUPPORT"]], 0) == (2, "BOT")
    # with the lanes free, the best player goes to their main lane
    assert auto_pick(pool, [["BOT", "SUPPORT"]], 0) == (1, "SUPPORT")
    assert auto_pick([p(1, "TOP")], [["MID"]], 0) is None

"""The "Show Matchup Data" panel: comp damage, totals and win rates once the draft is complete."""
import pytest
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.data.matchup_seed import canonical
from app.game.config import LANES
from app.models import Champion, ChampionMatchup
from tests.conftest import play_draft, start_draft
from tests.test_solo_mode import choose, draft_all, solo


@pytest.fixture
def no_counters(client):
    """An empty against-team matrix (it is seeded with estimates), so only the rates a test sets exist."""
    with SessionLocal() as db:
        db.execute(delete(ChampionMatchup).where(ChampionMatchup.kind == "enemy"))
        db.commit()


def set_enemy_rate(a, b, rate):
    """Champion a's win rate against champion b in the against-team matrix."""
    a, b, rate, _ = canonical("enemy", a, b, rate)
    with SessionLocal() as db:
        db.add(ChampionMatchup(kind="enemy", champion_a_id=a, champion_b_id=b, win_rate=rate, games=0, wins=0))
        db.commit()


def solo_after_draft(alice, team_ids):
    lobby = solo(alice)
    gid = lobby["game_id"]
    choose(alice, lobby, team_ids[0], team_ids[1])
    alice.post(f"/games/{gid}/ready")
    return gid, draft_all(alice, gid)


def test_not_available_during_the_draft(alice, default_team_ids):
    lobby = solo(alice)
    gid = lobby["game_id"]
    choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    alice.post(f"/games/{gid}/ready")
    assert alice.get(f"/games/{gid}/matchups").status_code == 409


def test_solo_shows_lane_vs_lane_and_follows_swaps(no_counters, alice, default_team_ids):
    gid, draft = solo_after_draft(alice, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    blue, red = state["lineup"]["blue"], state["lineup"]["red"]
    assert alice.get(f"/games/{gid}/matchups").json()["counter_data"] is False     # nothing seeded
    set_enemy_rate(blue["MID"], red["MID"], 57.5)

    data = alice.get(f"/games/{gid}/matchups").json()
    assert data["counter_data"] is True
    assert isinstance(data["notes"], list) and all(isinstance(n, str) for n in data["notes"])
    mid = data["lanes"]["MID"]
    assert (mid["blue"], mid["red"], mid["blue_win_rate"]) == (blue["MID"], red["MID"], 57.5)
    assert (mid["players"]["BLUE"]["counter_rate"], mid["players"]["RED"]["counter_rate"]) == (57.5, 42.5)
    assert data["lanes"]["TOP"]["blue_win_rate"] is None
    for side, picks in (("BLUE", draft["blue_picks"]), ("RED", draft["red_picks"])):
        team = data["teams"][side]
        assert sorted(team["champions"]) == sorted(picks)
        assert set(team["totals"]) == {"damage", "sturdiness", "cc", "mobility", "utility", "range", "waveclear"}
        with SessionLocal() as db:
            members = [db.get(Champion, cid) for cid in picks]
        assert team["totals"]["range"] == sum(c.attack_range for c in members)
        assert team["totals"]["waveclear"] == sum(c.waveclear for c in members)
        assert team["damage_profile"]["physical"] + team["damage_profile"]["magic"] == team["totals"]["damage"]
        assert 0 <= team["damage_penalty"] <= data["settings"]["max_damage_penalty"]

    # swapping blue's top and mid champions moves the matchup to top
    swapped = {**blue, "TOP": blue["MID"], "MID": blue["TOP"]}
    res = alice.put(f"/games/{gid}/lineup", {"side": "BLUE", "assignments": [
        {"lane": lane, "champion_id": swapped[lane]} for lane in LANES]})
    assert res.status_code == 200, res.text
    data = alice.get(f"/games/{gid}/matchups").json()
    assert data["lanes"]["TOP"]["blue"] == blue["MID"] and data["lanes"]["TOP"]["blue_win_rate"] is None
    assert data["lanes"]["MID"]["blue"] == blue["TOP"]


def test_multiplayer_shows_the_opponents_lanes_during_swaps(no_counters, alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    play_draft(alice, bob, gid, range(1, 80))
    red = bob.get(f"/games/{gid}/state").json()["lineup"]["yours"]
    set_enemy_rate(alice.get(f"/games/{gid}/state").json()["lineup"]["yours"]["TOP"], red["TOP"], 61.0)
    for api in (alice, bob):
        data = api.get(f"/games/{gid}/matchups").json()
        assert set(data["lineups"]["BLUE"]) == set(LANES) and data["lineups"]["RED"] == red
        assert data["lanes"]["TOP"]["red"] == red["TOP"] and data["lanes"]["TOP"]["blue_win_rate"] == 61.0

    # the opponent sees a swap straight away
    swapped = {**red, "TOP": red["MID"], "MID": red["TOP"]}
    assert bob.put(f"/games/{gid}/lineup", {"assignments": [
        {"lane": lane, "champion_id": swapped[lane]} for lane in LANES]}).status_code == 200
    assert alice.get(f"/games/{gid}/matchups").json()["lanes"]["TOP"]["red"] == red["MID"]
    # the game state itself still keeps the opponent's lineup to the end
    assert alice.get(f"/games/{gid}/state").json()["lineup"].get("opponent") is None


GRADES = {"S", "A", "B", "C", "D", "F"}
ROLE_STATUSES = {"MAIN", "SECONDARY", "OFF_ROLE", "OFF_ROLE_EXEMPT", None}


def test_solo_grades_both_sides_with_the_wheel_and_role_status(alice, default_team_ids):
    gid, _ = solo_after_draft(alice, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    data = alice.get(f"/games/{gid}/matchups").json()
    assert data["settings"]["off_role_penalty"] > 0
    for lane in LANES:
        entry = data["lanes"][lane]
        wheel = entry["wheel"]
        assert wheel["blue"]["strength"] in ("Offence", "Defence", "Control")
        assert wheel["winner"] in ("BLUE", "RED", None) and wheel["kind"] in ("STRONG", "SLIGHT", None)
        for side in ("BLUE", "RED"):
            info = entry["players"][side]
            assert info["player_id"] == state["lineup"]["players"][side][lane]
            assert info["grade"] in GRADES and 0 <= info["percentile"] <= 1 and info["expected"] > 0
            assert info["role_status"] in ROLE_STATUSES and info["off_role_penalty"] >= 0
            assert {"comfort", "wheel", "counter", "range", "off_role"} <= set(info["factors"])


def test_a_position_swap_grades_the_player_who_moved(alice, default_team_ids):
    gid, _ = solo_after_draft(alice, default_team_ids)
    state = alice.get(f"/games/{gid}/state").json()
    blue, players = state["lineup"]["blue"], state["lineup"]["players"]["BLUE"]
    res = alice.put(f"/games/{gid}/lineup", {"side": "BLUE", "assignments": [
        {"lane": lane, "champion_id": blue[lane],
         "player_id": players["MID" if lane == "TOP" else "TOP" if lane == "MID" else lane]} for lane in LANES]})
    assert res.status_code == 200, res.text
    data = alice.get(f"/games/{gid}/matchups").json()
    assert data["lanes"]["TOP"]["players"]["BLUE"]["player_id"] == players["MID"]


def test_hidden_player_data_hides_the_opponents_grades(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids, hide=True)
    play_draft(alice, bob, gid, range(1, 80))
    data = alice.get(f"/games/{gid}/matchups").json()
    for lane in LANES:
        mine, theirs = data["lanes"][lane]["players"]["BLUE"], data["lanes"][lane]["players"]["RED"]
        assert mine["grade"] in GRADES
        assert theirs["grade"] is None and theirs["factors"] is None and theirs["off_role_penalty"] is None
        assert theirs["role_status"] != "OFF_ROLE_EXEMPT"     # the exemption would reveal their pool


def test_outsiders_cannot_read_it(client, alice, default_team_ids):
    from tests.conftest import Api
    gid, _ = solo_after_draft(alice, default_team_ids)
    assert Api(client, "mallory").get(f"/games/{gid}/matchups").status_code in (403, 404)


def test_seeded_estimates_fill_every_lane(alice, default_team_ids):
    gid, _ = solo_after_draft(alice, default_team_ids)
    data = alice.get(f"/games/{gid}/matchups").json()
    assert data["counter_data"] is True
    assert all(lane["blue_win_rate"] is not None for lane in data["lanes"].values())

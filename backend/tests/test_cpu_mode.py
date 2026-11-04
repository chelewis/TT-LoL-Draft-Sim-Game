"""vs CPU: the user holds one seat and the CPU plays the other, after a short "thinking" delay."""
from datetime import timedelta

from tests.conftest import Api

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.game.config import DRAFT_CONFIG
from app.models import Game
from app.services import game_service


def cpu_lobby(alice, **settings):
    settings.setdefault("timers_enabled", False)
    res = alice.post("/lobbies", {"mode": "CPU", "settings": settings})
    assert res.status_code == 201, res.text
    return res.json()


def choose(alice, lobby, blue, red):
    assert alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": blue, "side": "BLUE"}).status_code == 200
    res = alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": red, "side": "RED"})
    assert res.status_code == 200, res.text
    return res.json()


def let_cpu_think(gid, seconds=3600):
    """Run the timer processing as if `seconds` had passed (what the background loop does every second)."""
    with SessionLocal() as db:
        game = db.get(Game, gid)
        return game_service.advance_timeouts(db, game, now=utcnow() + timedelta(seconds=seconds))


def free_champion(draft, start=1):
    used = {b["champion_id"] for b in draft["bans"]} | set(draft["blue_picks"]) | set(draft["red_picks"])
    used |= set(draft["fearless_locked"])
    return next(c for c in range(start, 500) if c not in used)


def play_my_turns(alice, gid, me):
    """Act on every one of the user's turns and let the CPU play its own, until the draft is done."""
    while True:
        draft = alice.get(f"/games/{gid}/draft").json()
        if draft["complete"]:
            return draft
        if draft["current_team"] != me:
            let_cpu_think(gid)
            continue
        kind = "pick" if draft["action_type"] == "PICK" else "ban"
        res = alice.post(f"/games/{gid}/draft/{kind}", {"champion_id": free_champion(draft)})
        assert res.status_code == 200, res.text


def started(alice, default_team_ids, **settings):
    lobby = cpu_lobby(alice, **settings)
    choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    state = alice.post(f"/games/{lobby['game_id']}/ready").json()
    assert state["status"] == "DRAFTING", state
    return lobby, state


def test_cpu_lobby_has_the_user_on_blue_and_the_cpu_on_red(alice):
    lobby = cpu_lobby(alice, hide_player_data=True)
    assert lobby["settings"]["mode"] == "CPU" and lobby["status"] == "TEAM_SELECTION"
    assert lobby["settings"]["hide_player_data"] is False
    state = alice.get(f"/games/{lobby['game_id']}/state").json()
    assert state["you"]["team"] == "BLUE"
    assert state["players"]["red"]["bot"] is True and state["players"]["red"]["username"] == "CPU"
    assert alice.get("/games").json()[0]["settings"]["mode"] == "CPU"


def test_the_user_chooses_both_teams(alice, default_team_ids):
    lobby = cpu_lobby(alice)
    state = choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    assert state["status"] == "READY_CHECK"
    assert state["teams"]["BLUE"]["id"] == default_team_ids[0] and state["teams"]["RED"]["id"] == default_team_ids[1]


def test_the_cpu_waits_its_thinking_time_then_acts(alice, default_team_ids):
    lobby, state = started(alice, default_team_ids)
    gid = lobby["game_id"]
    assert state["draft"]["current_team"] == "BLUE"
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 200
    draft = alice.get(f"/games/{gid}/draft").json()
    assert draft["current_team"] == "RED" and draft["expires_at"] is not None   # CPU thinking, timers off or not
    # the user can't act or hover for the CPU
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 2}).status_code == 409
    assert alice.post(f"/games/{gid}/draft/hover", {"champion_id": 2, "draft_action": 1}).status_code == 409
    # not before the delay is up
    assert let_cpu_think(gid, seconds=DRAFT_CONFIG["cpu_delay_seconds"] / 2) == []
    events = let_cpu_think(gid)
    assert [e["type"] for e in events][:1] == ["CHAMPION_BANNED"] and events[0]["team"] == "RED"
    draft = alice.get(f"/games/{gid}/draft").json()
    assert draft["current_team"] == "BLUE" and draft["history"][-1]["auto"] is False
    assert draft["expires_at"] is None                    # the user's turn has no timer when timers are off


def test_full_game_against_the_cpu(alice, default_team_ids):
    lobby, _ = started(alice, default_team_ids)
    gid = lobby["game_id"]
    draft = play_my_turns(alice, gid, "BLUE")
    assert len(draft["blue_picks"]) == len(draft["red_picks"]) == 5 and len(draft["bans"]) == 10
    state = alice.get(f"/games/{gid}/state").json()
    assert state["status"] == "LANE_ASSIGNMENT"
    assert state["players"]["red"]["lineup_ready"] is True          # the CPU locked its lanes in
    assert "opponent" not in state["lineup"]                        # and they stay hidden until the end
    done = alice.post(f"/games/{gid}/lineup/ready").json()
    assert done["status"] == "COMPLETED"
    result = alice.get(f"/games/{gid}/result").json()
    assert set(result["lineups"]["RED"].values()) == set(draft["red_picks"])


def test_playing_red_lets_the_cpu_ban_first(alice, default_team_ids):
    lobby = cpu_lobby(alice)
    assert alice.post(f"/lobbies/{lobby['id']}/side", {"side": "RED"}).status_code == 200
    state = alice.get(f"/games/{lobby['game_id']}/state").json()
    assert state["you"]["team"] == "RED" and state["players"]["blue"]["bot"] is True
    choose(alice, lobby, default_team_ids[0], default_team_ids[1])
    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 409
    let_cpu_think(gid)
    assert alice.get(f"/games/{gid}/draft").json()["current_team"] == "RED"
    play_my_turns(alice, gid, "RED")
    assert alice.post(f"/games/{gid}/lineup/ready").json()["status"] == "COMPLETED"


def test_with_timers_on_the_users_timeouts_and_the_cpu_both_play_out(alice, default_team_ids):
    lobby, _ = started(alice, default_team_ids, timers_enabled=True, pick_seconds=5, ban_seconds=5)
    gid = lobby["game_id"]
    let_cpu_think(gid)
    draft = alice.get(f"/games/{gid}/draft").json()
    assert draft["complete"]
    assert all(h["auto"] == (h["team"] == "BLUE") for h in draft["history"])


def test_without_bans(alice, default_team_ids):
    lobby, _ = started(alice, default_team_ids, bans_enabled=False)
    draft = play_my_turns(alice, lobby["game_id"], "BLUE")
    assert draft["bans"] == [] and len(draft["red_picks"]) == 5


def test_nobody_can_join_a_cpu_game(client, alice):
    lobby = cpu_lobby(alice)
    bob = Api(client, "bob")
    assert bob.post(f"/lobbies/{lobby['code']}/join").status_code == 409
    assert bob.get(f"/games/{lobby['game_id']}/state").status_code == 404


def test_series_against_the_cpu_moves_on_with_the_cpu_ready(alice, default_team_ids):
    lobby, _ = started(alice, default_team_ids, series_format="BO3", fearless=True)
    gid = lobby["game_id"]
    play_my_turns(alice, gid, "BLUE")
    state = alice.post(f"/games/{gid}/lineup/ready").json()
    assert state["status"] == "COMPLETED"
    loser = state["series"]["loser_side"]
    # the user stays on Blue whoever lost (the CPU keeps its side when it loses)
    res = alice.post(f"/games/{gid}/series/ready", {"side": "BLUE"})
    assert res.status_code == 200, res.text
    gid2 = res.json()["series"]["next_game_id"]
    assert gid2, (loser, res.json()["series"])
    g2 = alice.get(f"/games/{gid2}/state").json()
    assert g2["status"] == "DRAFTING" and g2["settings"]["mode"] == "CPU" and g2["you"]["team"] == "BLUE"
    draft = play_my_turns(alice, gid2, "BLUE")
    first_picks = set(state["draft"]["blue_picks"]) | set(state["draft"]["red_picks"])
    assert not first_picks & (set(draft["blue_picks"]) | set(draft["red_picks"]))     # fearless holds for the CPU
    assert alice.get(f"/series/{g2['series']['id']}").json()["mode"] == "CPU"

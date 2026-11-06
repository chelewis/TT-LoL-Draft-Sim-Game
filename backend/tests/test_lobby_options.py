"""Lobby creation options: ban phases on/off, pick/ban timers on/off, custom time limits."""
from datetime import timedelta

from tests.conftest import play_draft

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.models import Game
from app.services import game_service


def start(alice, bob, team_ids, **settings):
    lobby = alice.post("/lobbies", {"settings": settings})
    assert lobby.status_code == 201, lobby.text
    lobby = lobby.json()
    bob.post(f"/lobbies/{lobby['code']}/join")
    alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_ids[0]})
    bob.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_ids[1]})
    gid = lobby["game_id"]
    alice.post(f"/games/{gid}/ready")
    bob.post(f"/games/{gid}/ready")
    return lobby, gid


def test_defaults(alice, bob, default_team_ids):
    lobby, gid = start(alice, bob, default_team_ids)
    assert lobby["settings"] == {"hide_player_data": False, "bans_enabled": True, "timers_enabled": True,
                                 "pick_seconds": 30, "ban_seconds": 30, "mode": "MULTI",
                                 "series_format": "BO1", "fearless": False,
                                 "max_rank": None, "max_player_total": None, "max_team_total": None,
                                 "duplicate_clause": False, "mirror_clause": False,
                                 "ruleset": "ANYTHING_GOES", "ruleset_name": "Anything Goes",
                                 "ruleset_modified": False}
    assert lobby["series"] is None
    draft = alice.get(f"/games/{gid}/draft").json()
    assert len(draft["actions"]) == 20 and draft["timers_enabled"] and draft["expires_at"]


def test_bans_disabled_skips_every_ban_phase(alice, bob, default_team_ids):
    lobby, gid = start(alice, bob, default_team_ids, bans_enabled=False)
    draft = alice.get(f"/games/{gid}/draft").json()
    assert len(draft["actions"]) == 10 and all(a.endswith("_PICK") for a in draft["actions"])
    assert draft["action_type"] == "PICK" and draft["current_team"] == "BLUE"
    # a ban is rejected, picks complete the draft with no bans at all
    assert alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1}).status_code == 409
    done = play_draft(alice, bob, gid, range(1, 40))
    assert done["bans"] == [] and len(done["blue_picks"]) == 5 and len(done["red_picks"]) == 5
    assert alice.get(f"/games/{gid}/state").json()["status"] == "LANE_ASSIGNMENT"
    # the pick order keeps the configured snake, minus the bans
    assert [h["team"] for h in done["history"]] == ["BLUE", "RED", "RED", "BLUE", "BLUE", "RED", "RED", "BLUE", "BLUE", "RED"]


def test_timers_disabled_means_no_deadline(alice, bob, default_team_ids):
    lobby, gid = start(alice, bob, default_team_ids, timers_enabled=False)
    draft = alice.get(f"/games/{gid}/draft").json()
    assert draft["timers_enabled"] is False and draft["expires_at"] is None and draft["started_at"] is None or \
        draft["expires_at"] is None
    with SessionLocal() as db:
        game = db.get(Game, gid)
        events = game_service.advance_timeouts(db, game, now=utcnow() + timedelta(days=30))
        assert events == [] and game.current_action == 0 and game.status == "DRAFTING"
    # a pick still advances to the next action, which also has no deadline
    alice.post(f"/games/{gid}/draft/ban", {"champion_id": 1})
    after = alice.get(f"/games/{gid}/draft").json()
    assert after["current_action"] == 1 and after["expires_at"] is None


def test_custom_pick_and_ban_limits(alice, bob, default_team_ids):
    lobby, gid = start(alice, bob, default_team_ids, pick_seconds=45, ban_seconds=12)
    assert lobby["settings"]["pick_seconds"] == 45 and lobby["settings"]["ban_seconds"] == 12
    with SessionLocal() as db:
        game = db.get(Game, gid)
        assert (game.action_expires_at - game.action_started_at).total_seconds() == 12   # first action is a ban
    # walk to the first pick (after six bans): its limit is the pick limit
    ids = iter(range(1, 40))
    for _ in range(6):
        d = alice.get(f"/games/{gid}/draft").json()
        user = alice if d["current_team"] == "BLUE" else bob
        assert user.post(f"/games/{gid}/draft/ban", {"champion_id": next(ids)}).status_code == 200
    with SessionLocal() as db:
        game = db.get(Game, gid)
        assert (game.action_expires_at - game.action_started_at).total_seconds() == 45


def test_limit_validation(alice):
    for field in ("pick_seconds", "ban_seconds"):
        assert alice.post("/lobbies", {"settings": {field: 2}}).status_code == 422
        assert alice.post("/lobbies", {"settings": {field: 9999}}).status_code == 422
    assert alice.post("/lobbies", {"settings": {"pick_seconds": 5, "ban_seconds": 600}}).status_code == 201


def test_bans_disabled_with_timeouts_still_completes(alice, bob, default_team_ids):
    lobby, gid = start(alice, bob, default_team_ids, bans_enabled=False, pick_seconds=5)
    with SessionLocal() as db:
        game = db.get(Game, gid)
        game_service.advance_timeouts(db, game, now=utcnow() + timedelta(hours=1))
        assert game.status == "LANE_ASSIGNMENT"
    draft = alice.get(f"/games/{gid}/draft").json()
    assert len(draft["history"]) == 10 and draft["bans"] == []

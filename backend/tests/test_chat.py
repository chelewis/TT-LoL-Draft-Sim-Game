"""All-chat between the two players of a game."""
from datetime import timedelta

from app.core.database import SessionLocal
from app.models import ChatMessage
from tests.conftest import Api, start_draft


def test_both_players_see_the_chat_in_order(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    first = alice.post(f"/games/{gid}/chat", {"text": "  gg  ez\n already "})
    assert first.status_code == 201
    msg = first.json()
    assert msg["body"] == "gg ez already"            # whitespace collapsed
    assert msg["username"] == "alice" and msg["team"] == "BLUE"
    assert bob.post(f"/games/{gid}/chat", {"text": "we'll see"}).status_code == 201

    for viewer in (alice, bob):
        history = viewer.get(f"/games/{gid}/chat").json()
        assert [(m["username"], m["team"], m["body"]) for m in history] == [
            ("alice", "BLUE", "gg ez already"), ("bob", "RED", "we'll see")]


def test_message_is_pushed_to_the_opponent(client, alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    with client.websocket_connect(f"/ws/games/{gid}?token={bob.token}") as ws:
        assert ws.receive_json()["type"] == "CONNECTED"
        alice.post(f"/games/{gid}/chat", {"text": "nice ban"})
        event = ws.receive_json()
        while event["type"] != "CHAT_MESSAGE":      # skip presence notices
            event = ws.receive_json()
        assert event["message"]["body"] == "nice ban" and event["message"]["username"] == "alice"


def test_chat_rejects_empty_long_and_outsiders(client, alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    assert alice.post(f"/games/{gid}/chat", {"text": "   "}).status_code == 400
    assert alice.post(f"/games/{gid}/chat", {"text": "x" * 201}).status_code == 400
    assert alice.post(f"/games/{gid}/chat", {"text": "x" * 200}).status_code == 201
    carol = Api(client, "carol")
    assert carol.post(f"/games/{gid}/chat", {"text": "hi"}).status_code == 404
    assert carol.get(f"/games/{gid}/chat").status_code == 404


def test_chat_is_rate_limited(alice, bob, default_team_ids):
    gid = start_draft(alice, bob, default_team_ids)
    for i in range(5):
        assert alice.post(f"/games/{gid}/chat", {"text": f"spam {i}"}).status_code == 201
    assert alice.post(f"/games/{gid}/chat", {"text": "one more"}).status_code == 400
    assert bob.post(f"/games/{gid}/chat", {"text": "calm down"}).status_code == 201   # per player
    # once the window has passed, alice can talk again
    with SessionLocal() as db:
        for m in db.query(ChatMessage).filter(ChatMessage.game_id == gid):
            m.created_at -= timedelta(seconds=11)
        db.commit()
    assert alice.post(f"/games/{gid}/chat", {"text": "back"}).status_code == 201

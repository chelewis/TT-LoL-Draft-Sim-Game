"""Play one full game against a running server (default http://127.0.0.1:8000).

    python -m scripts.smoke_test [base_url]

Exercises register -> lobby -> draft (incl. a real timeout) -> lineup -> simulation -> result
over HTTP + WebSocket, exactly as the browser client does.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
LANES = ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"]


def register(client: httpx.Client, name: str) -> dict:
    suffix = uuid.uuid4().hex[:6]
    res = client.post(f"{BASE}/api/v1/auth/register", json={
        "username": f"{name}_{suffix}", "email": f"{name}_{suffix}@example.com", "password": "password123"})
    res.raise_for_status()
    return {"headers": {"Authorization": f"Bearer {res.json()['access_token']}"}, "token": res.json()["access_token"]}


async def main() -> None:
    with httpx.Client() as c:
        a, b = register(c, "smokea"), register(c, "smokeb")
        call = lambda u, m, p, **kw: getattr(c, m)(f"{BASE}/api/v1{p}", headers=u["headers"], **kw)  # noqa: E731

        teams = [t for t in call(a, "get", "/teams?selectable=true").json()]
        lobby = call(a, "post", "/lobbies", json={"settings": {"hide_player_data": False}}).json()
        gid = lobby["game_id"]
        ws_url = BASE.replace("http", "ws") + f"/ws/games/{gid}?token={a['token']}"
        async with websockets.connect(ws_url) as ws:
            assert json.loads(await ws.recv())["type"] == "CONNECTED"
            call(b, "post", f"/lobbies/{lobby['code']}/join").raise_for_status()
            call(a, "post", f"/lobbies/{lobby['id']}/team", json={"team_id": teams[0]["id"]}).raise_for_status()
            call(b, "post", f"/lobbies/{lobby['id']}/team", json={"team_id": teams[1]["id"]}).raise_for_status()
            call(a, "post", f"/games/{gid}/ready").raise_for_status()
            call(b, "post", f"/games/{gid}/ready").raise_for_status()

            champions = [ch["id"] for ch in call(a, "get", "/champions").json()]
            ids = iter(champions)
            users = {"BLUE": a, "RED": b}
            timed_out = False
            while True:
                d = call(a, "get", f"/games/{gid}/draft").json()
                if d["complete"]:
                    break
                if not timed_out and d["current_action"] == 3:
                    # let one real 30s timer run out to prove the server applies the timeout itself
                    print("waiting for a real draft timeout (30s)...")
                    start = time.time()
                    while call(a, "get", f"/games/{gid}/draft").json()["current_action"] == 3:
                        await asyncio.sleep(1)
                        if time.time() - start > 45:
                            raise SystemExit("timeout was never applied")
                    timed_out = True
                    continue
                kind = "pick" if d["action_type"] == "PICK" else "ban"
                r = call(users[d["current_team"]], "post", f"/games/{gid}/draft/{kind}", json={"champion_id": next(ids)})
                if r.status_code == 409:   # a timeout got there first; carry on
                    continue
                r.raise_for_status()

            d = call(a, "get", f"/games/{gid}/draft").json()
            assert any(h["auto"] for h in d["history"]), "expected an automatic timeout action"
            for user, picks in ((a, d["blue_picks"]), (b, d["red_picks"])):
                call(user, "put", f"/games/{gid}/lineup", json={"assignments": [
                    {"lane": lane, "champion_id": cid} for lane, cid in zip(LANES, picks)]}).raise_for_status()
                call(user, "post", f"/games/{gid}/lineup/ready").raise_for_status()

            seen = set()
            try:
                while True:
                    seen.add(json.loads(await asyncio.wait_for(ws.recv(), timeout=1))["type"])
            except asyncio.TimeoutError:
                pass

        result = call(a, "get", f"/games/{gid}/result").json()
        print(f"winner={result['winner']} via {result['win_condition']} in {result['duration_seconds'] // 60} min, "
              f"seed={result['seed']}, version={result['simulation_version']}")
        print("websocket events seen:", sorted(seen))
        assert {"CHAMPION_PICKED", "CHAMPION_BANNED", "DRAFT_COMPLETED", "SIMULATION_COMPLETED"} <= seen
        print("OK")


if __name__ == "__main__":
    asyncio.run(main())

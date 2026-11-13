"""Seasons (phase 4): Player Draft seasons (team identities, the pool, the snake draft, pick clocks) and free agency."""
from datetime import timedelta

from app.core.clock import utcnow
from app.core.database import SessionLocal
from app.services import season_draft_service
from tests.test_season_flow import started

LANES = ("TOP", "JUNGLE", "MID", "BOT", "SUPPORT")


def draft_season(alice, **options):
    options.setdefault("human_slots", 2)
    season = create(alice, roster_mode="DRAFT", **options)
    res = alice.post(f"/seasons/{season['id']}/teams", {"name": "Alice Academy", "style1": "early"})
    assert res.status_code == 201, res.text
    return res.json()


def create(alice, roster_mode="BYO", format="ROUND_ROBIN", **options):
    body = {"name": "Draft Cup", "roster_mode": roster_mode, "format": format, "rules": {"timers_enabled": False},
            "options": {"team_count": 4, **options}}
    res = alice.post("/seasons", body)
    assert res.status_code == 201, res.text
    return res.json()


def with_bob(alice, bob, **options):
    season = draft_season(alice, **options)
    res = bob.post(f"/seasons/join/{season['code']}", {"name": "Bob Bulls"})
    assert res.status_code == 201, res.text
    assert alice.post(f"/seasons/{season['id']}/pool/generate", {"per_role": 2}).status_code == 201
    return alice.get(f"/seasons/{season['id']}").json()


def run_draft(season, users):
    """Make every pick: the manager on the clock takes the best available player for one of their lanes."""
    view = season
    while view["status"] == "PLAYER_DRAFT":
        on_clock = view["draft"]["on_the_clock"]
        user = users[on_clock["manager"]["id"]]
        res = user.post(f"/seasons/{view['id']}/draft/auto")
        assert res.status_code == 200, res.text
        view = res.json()
    return view


def test_a_draft_team_is_an_identity_with_an_empty_roster(alice):
    season = draft_season(alice)
    assert season["roster_mode"] == "DRAFT"
    mine = next(t for t in season["teams"] if t["is_you"])
    assert mine["name"] == "Alice Academy" and mine["rating"] == 0
    detail = alice.get(f"/seasons/{season['id']}/teams/{mine['id']}").json()
    assert detail["view"]["coach"] is not None and detail["view"]["style1"] == "early" and detail["view"]["style2"]
    assert all(v is None for v in detail["view"]["roster"].values())
    # a name is needed (there's no team to bring)
    other = create(alice, roster_mode="DRAFT")
    assert alice.post(f"/seasons/{other['id']}/teams", {}).status_code == 400


def test_the_creator_fills_the_pool(alice, bob):
    season = draft_season(alice)
    assert season["pool"] == {"count": 0, "by_lane": dict.fromkeys(LANES, 0), "shortfall": dict.fromkeys(LANES, 1)}
    view = alice.post(f"/seasons/{season['id']}/pool/generate", {"per_role": 3}).json()
    assert view["pool"]["count"] == 15 and view["pool"]["shortfall"] == {}
    assert all(n >= 3 for n in view["pool"]["by_lane"].values())
    players = alice.get(f"/seasons/{season['id']}/pool").json()["players"]
    assert len(players) == 15 and all(p["generated"] and p["role"] in p["lanes"] for p in players)
    # your own (or default) players are copied in, once each
    default_players = [p["id"] for p in alice.get("/players").json()][:2]
    view = alice.post(f"/seasons/{season['id']}/pool/players", {"player_ids": default_players}).json()
    assert view["pool"]["count"] == 17
    assert alice.post(f"/seasons/{season['id']}/pool/players", {"player_ids": default_players[:1]}).status_code == 409
    one = players[0]["id"]
    assert alice.delete(f"/seasons/{season['id']}/pool/{one}").json()["pool"]["count"] == 16
    assert alice.delete(f"/seasons/{season['id']}/pool").json()["pool"]["count"] == 0
    # only the creator manages the pool
    bob.post(f"/seasons/join/{season['code']}", {"name": "Bob Bulls"})
    assert bob.post(f"/seasons/{season['id']}/pool/generate", {"per_role": 1}).status_code == 403


def test_the_pool_must_fill_every_roster(alice, bob):
    season = draft_season(alice)
    bob.post(f"/seasons/join/{season['code']}", {"name": "Bob Bulls"})
    alice.post(f"/seasons/{season['id']}/pool/generate", {"per_role": 1})        # one per lane, two managers
    res = alice.post(f"/seasons/{season['id']}/start")
    assert res.status_code == 409 and "short of" in res.json()["detail"]


def test_snake_draft_then_the_season(alice, bob):
    season = with_bob(alice, bob)
    season = alice.post(f"/seasons/{season['id']}/start").json()
    assert season["status"] == "PLAYER_DRAFT"
    draft = season["draft"]
    assert len(draft["order"]) == 2 and draft["total_picks"] == 10 and draft["current_pick"] == 1
    users = {alice.user["id"]: alice, bob.user["id"]: bob}
    first = users[draft["on_the_clock"]["manager"]["id"]]
    second = bob if first is alice else alice
    # only the manager on the clock picks, into a lane the player plays
    pool = first.get(f"/seasons/{season['id']}/pool").json()["players"]
    player = pool[0]
    assert second.post(f"/seasons/{season['id']}/draft/pick", {"player_id": player["id"], "lane": player["role"]}) \
        .status_code == 409
    wrong = next(lane for lane in LANES if lane not in player["lanes"])
    assert first.post(f"/seasons/{season['id']}/draft/pick", {"player_id": player["id"], "lane": wrong}) \
        .status_code == 409
    view = first.post(f"/seasons/{season['id']}/draft/pick", {"player_id": player["id"], "lane": player["role"]}).json()
    assert view["draft"]["picks"][0]["player_name"] == player["name"] and not view["draft"]["picks"][0]["auto"]
    # snake: the second team has picks 2 and 3
    assert view["draft"]["on_the_clock"]["manager"]["id"] == second.user["id"]
    view = run_draft(view, users)
    assert view["status"] == "REGULAR" and view["draft"]["complete"]
    assert len(view["draft"]["picks"]) == 10
    for t in view["teams"]:
        detail = alice.get(f"/seasons/{season['id']}/teams/{t['id']}").json()
        assert detail["view"]["selectable"], detail["view"]["issues"]
    # matches play as usual with the drafted rosters
    match = alice.get(f"/seasons/{season['id']}").json()["my_match"]
    alice.post(f"/seasons/matches/{match['id']}/auto")
    if not (match["home"]["is_cpu"] or match["away"]["is_cpu"]):
        bob.post(f"/seasons/matches/{match['id']}/auto")              # against Bob: both have to agree
    assert alice.get(f"/seasons/{season['id']}").json()["my_match"]["status"] == "COMPLETED"


def test_pick_clock_auto_picks(alice, bob):
    season = with_bob(alice, bob, draft_pick_seconds=60)
    season = alice.post(f"/seasons/{season['id']}/start").json()
    assert season["draft"]["pick_deadline_at"] is not None
    with SessionLocal() as db:
        assert season_draft_service.process_draft_clocks(db, utcnow() + timedelta(seconds=30)) == []
    with SessionLocal() as db:
        assert season_draft_service.process_draft_clocks(db, utcnow() + timedelta(seconds=61))
    view = alice.get(f"/seasons/{season['id']}").json()
    assert view["draft"]["current_pick"] == 2 and view["draft"]["picks"][0]["auto"]


def test_the_creator_can_move_the_draft_on(alice, bob):
    season = with_bob(alice, bob)
    season = alice.post(f"/seasons/{season['id']}/start").json()
    on_clock = season["draft"]["on_the_clock"]["manager"]["id"]
    if on_clock == alice.user["id"]:                       # make it Bob's turn
        season = alice.post(f"/seasons/{season['id']}/draft/auto").json()
    assert bob.post(f"/seasons/{season['id']}/draft/auto").status_code == 200    # Bob for himself
    view = alice.get(f"/seasons/{season['id']}").json()
    while view["draft"]["on_the_clock"]["manager"]["id"] != bob.user["id"]:
        view = alice.post(f"/seasons/{season['id']}/draft/auto").json()
    view = alice.post(f"/seasons/{season['id']}/draft/auto").json()             # the creator, for Bob
    assert view["draft"]["picks"][-1]["team"]["manager"]["id"] == bob.user["id"]


def test_the_cpu_drafts_for_a_manager_who_left(alice, bob):
    season = with_bob(alice, bob)
    season = alice.post(f"/seasons/{season['id']}/start").json()
    bob_team = bob.get(f"/seasons/{season['id']}").json()["my_team_id"]
    bob.post(f"/seasons/{season['id']}/teams/{bob_team}/release")
    view = run_draft(alice.get(f"/seasons/{season['id']}").json(), {alice.user["id"]: alice})
    assert view["status"] == "REGULAR"
    assert sum(p["team"]["id"] == bob_team for p in view["draft"]["picks"]) == 5


# ------------------------------------------------------------ free agency
def test_free_agents_and_signing(alice, default_team_ids):
    season = started(alice, default_team_ids)          # BYO; free agency on by default: 3 signings, 2 per lane
    assert season["free_agency"] == {"enabled": True, "max_signings": 3, "open": True, "signings_left": 3}
    agents = alice.get(f"/seasons/{season['id']}/pool").json()["players"]
    assert len(agents) == 10
    mine = next(t for t in season["teams"] if t["is_you"])
    before = alice.get(f"/seasons/{season['id']}/teams/{mine['id']}").json()["view"]["roster"]
    agent = agents[0]
    wrong = next(lane for lane in LANES if lane not in agent["lanes"])
    assert alice.post(f"/seasons/{season['id']}/free-agents/sign", {"player_id": agent["id"], "lane": wrong}) \
        .status_code == 400
    res = alice.post(f"/seasons/{season['id']}/free-agents/sign", {"player_id": agent["id"], "lane": agent["role"]})
    assert res.status_code == 200, res.text
    view = res.json()
    assert view["free_agency"]["signings_left"] == 2
    assert [t["type"] for t in view["transactions"]] == ["SIGN", "RELEASE"]
    after = alice.get(f"/seasons/{season['id']}/teams/{mine['id']}").json()["view"]["roster"]
    assert after[agent["role"]]["name"] == agent["name"]
    # the released player is a free agent now
    names = {p["name"] for p in alice.get(f"/seasons/{season['id']}/pool").json()["players"]}
    assert before[agent["role"]]["name"] in names and agent["name"] not in names


def test_no_signing_mid_match_or_past_the_limit(alice, default_team_ids):
    season = started(alice, default_team_ids, max_signings=1)
    agents = alice.get(f"/seasons/{season['id']}/pool").json()["players"]
    alice.post(f"/seasons/matches/{season['my_match']['id']}/play")          # a match in progress
    res = alice.post(f"/seasons/{season['id']}/free-agents/sign", {"player_id": agents[0]["id"], "lane": agents[0]["role"]})
    assert res.status_code == 409 and "middle of a match" in res.json()["detail"]
    alice.post(f"/seasons/matches/{season['my_match']['id']}/auto")
    assert alice.post(f"/seasons/{season['id']}/free-agents/sign",
                      {"player_id": agents[0]["id"], "lane": agents[0]["role"]}).status_code == 200
    res = alice.post(f"/seasons/{season['id']}/free-agents/sign", {"player_id": agents[1]["id"], "lane": agents[1]["role"]})
    assert res.status_code == 409 and "all 1" in res.json()["detail"]


def test_free_agency_can_be_off(alice, default_team_ids):
    season = started(alice, default_team_ids, max_signings=0)
    assert season["free_agency"]["enabled"] is False
    assert alice.get(f"/seasons/{season['id']}/pool").json()["players"] == []
    res = alice.post(f"/seasons/{season['id']}/free-agents/sign", {"player_id": 1, "lane": "TOP"})
    assert res.status_code == 409


def test_undrafted_players_become_free_agents(alice, bob):
    season = with_bob(alice, bob, free_agents_per_role=0)
    alice.post(f"/seasons/{season['id']}/pool/generate", {"per_role": 1})      # 15 in the pool, 10 get drafted
    season = alice.post(f"/seasons/{season['id']}/start").json()
    view = run_draft(season, {alice.user["id"]: alice, bob.user["id"]: bob})
    assert len(alice.get(f"/seasons/{view['id']}/pool").json()["players"]) == 5

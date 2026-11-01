"""Import seal: is a player a genuine Riot import, and was anything that affects its strength edited?"""
import jwt
import pytest

from app.api.management import get_riot_client
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models import Player
from app.services import game_service, riot_import_service
from tests.riot_fixtures import STRONG, WEAK, FakeRiotClient

BODY = {"riot_id": "Faker#KR1", "region": "KR"}
EDITABLE = ("name", "role", "secondary_role", "age", "region", "aggr", "aware", "pos", "dmg", "cs", "pool")


@pytest.fixture
def riot(client, monkeypatch):
    fake = FakeRiotClient(mine=STRONG)
    monkeypatch.setattr(settings, "riot_api_key", "test-key")
    monkeypatch.setattr(settings, "riot_user_cooldown_seconds", 0)
    riot_import_service.reset_state()
    app.dependency_overrides[get_riot_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_riot_client, None)
    riot_import_service.reset_state()


def imported(api, **overrides):
    preview = api.post("/riot/preview", BODY).json()
    res = api.post("/players", {**preview["player"], "riot_ref": preview["riot_ref"], **overrides})
    assert res.status_code == 201, res.text
    return res.json()


def edit(api, player, **changes):
    body = {**{k: player[k] for k in EDITABLE}, "tags": [t["key"] for t in player["tags"]], **changes}
    res = api.put(f"/players/{player['id']}", body)
    assert res.status_code == 200, res.text
    return res.json()


def check(player):
    return player["riot"]["import_check"]


def other_champions(api, exclude, n):
    return [c["id"] for c in api.get("/champions").json() if c["id"] not in exclude][:n]


def test_straight_import_is_unedited_and_free_fields_stay_so(alice, riot):
    p = imported(alice)
    assert check(p)["status"] == "unedited" and check(p)["edited_fields"] == []
    assert check(p)["original"]["aggr"] == p["aggr"] and check(p)["original"]["pool"] == p["pool"]
    lanes = ["TOP", "JUNGLE", "BOT", "SUPPORT"]
    p = edit(alice, p, name="Renamed", age=33, region="Narnia", secondary_role=lanes[0])
    assert check(p)["status"] == "unedited"
    assert p["riot"]["verified"] is False            # account ownership is a separate thing


@pytest.mark.parametrize("changes, fields", [
    ({"aggr": "+1"}, ["aggr"]),
    ({"role": "TOP"}, ["role"]),
    ({"pool": "swap"}, ["pool"]),
])
def test_strength_changes_are_edits(alice, riot, changes, fields):
    p = imported(alice)
    patch = {}
    if "aggr" in changes:
        patch["aggr"] = p["aggr"] % 10 + 1
    if "role" in changes:
        patch["role"] = "TOP"
    if "pool" in changes:
        patch["pool"] = [p["pool"][1], p["pool"][0], *p["pool"][2:]]
    p = edit(alice, p, **patch)
    assert check(p)["status"] == "edited" and check(p)["edited_fields"] == fields
    # putting it back makes it unedited again
    original = check(p)["original"]
    p = edit(alice, p, role=original["role"], aggr=original["aggr"], pool=original["pool"])
    assert check(p)["status"] == "unedited"


def test_the_browser_cannot_change_the_baseline(alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    p = preview["player"]
    better = {**p, "cs": min(10, p["cs"] + 2), "riot_ref": preview["riot_ref"]}
    saved = alice.post("/players", better).json()
    assert check(saved)["status"] == "edited" and check(saved)["edited_fields"] == ["cs"]


def test_filling_empty_pool_slots_is_not_an_edit(alice, riot):
    riot.champion_cycle = (103, 9999)           # one known champion; mastery tops up Aatrox and Wukong
    preview = alice.post("/riot/preview", BODY).json()
    pool = preview["player"]["pool"]
    assert 0 < len(pool) < 5
    filled = pool + other_champions(alice, pool, 5 - len(pool))
    p = imported(alice, pool=filled)
    assert check(p)["status"] == "unedited" and check(p)["original"]["pool"] == pool
    # the user-chosen slots can change freely; the imported ones can't
    p = edit(alice, p, pool=pool + other_champions(alice, filled, 5 - len(pool)))
    assert check(p)["status"] == "unedited"
    p = edit(alice, p, pool=list(reversed(p["pool"])))
    assert check(p)["edited_fields"] == ["pool"]


def test_dropping_a_weakness_is_an_edit_but_dropping_a_strength_is_not(alice, riot):
    riot.mine = WEAK                            # earns several weaknesses from these games
    riot.challenges = {203301: "MASTER"}       # Solo Bolo: earns the Duelist strength
    preview = alice.post("/riot/preview", BODY).json()
    polarity = {t["key"]: t["polarity"] for t in preview["analysis"]["tags"]["earned"]}
    suggested = preview["player"]["tags"]
    weak = [k for k in suggested if polarity[k] == "negative"]
    assert len(weak) >= 2 and "duelist" in suggested
    p = imported(alice, tags=weak)                                        # Duelist dropped: fine
    assert check(p)["status"] == "unedited" and check(p)["original"]["negative_tags"] == weak
    p = edit(alice, p, tags=weak[1:])                                     # one weakness dropped
    assert check(p)["status"] == "edited" and check(p)["edited_fields"] == ["tags"]


def test_refresh_restores_an_edited_player(alice, riot):
    p = edit(alice, imported(alice), dmg=1)
    assert check(p)["status"] == "edited"
    riot_import_service.reset_state()
    draft = alice.post(f"/players/{p['id']}/riot-refresh").json()
    res = alice.put(f"/players/{p['id']}", {**draft["player"], "riot_ref": draft["riot_ref"]})
    assert check(res.json())["status"] == "unedited"


def _set(player_id, **columns):
    with SessionLocal() as db:
        row = db.get(Player, player_id)
        for k, v in columns.items():
            setattr(row, k, v)
        db.commit()


def test_missing_forged_or_moved_seals_are_unverified(alice, riot):
    p = imported(alice)
    _set(p["id"], riot_seal=None)                                         # imported before seals existed
    assert check(alice.get(f"/players/{p['id']}").json())["status"] == "unverified"

    forged = jwt.encode({"typ": "riot_seal", "v": 1, "puuid": "puuid-faker", "role": p["role"],
                         **{s: 10 for s in ("aggr", "aware", "pos", "dmg", "cs")}, "pool": [],
                         "negative_tags": [], "rank_tier": "GOLD"}, "not-the-server-key", algorithm="HS256")
    _set(p["id"], riot_seal=forged)
    assert check(alice.get(f"/players/{p['id']}").json())["status"] == "unverified"
    _set(p["id"], riot_seal="garbage")
    assert check(alice.get(f"/players/{p['id']}").json())["status"] == "unverified"

    q = imported(alice)
    with SessionLocal() as db:
        seal = db.get(Player, q["id"]).riot_seal
    _set(q["id"], riot_puuid="someone-else")                              # seal moved to another account
    assert check(alice.get(f"/players/{q['id']}").json())["status"] == "unverified"
    _set(q["id"], riot_puuid="puuid-faker", riot_rank_tier="CHALLENGER")  # rank raised by hand
    assert check(alice.get(f"/players/{q['id']}").json())["status"] == "unverified"
    assert seal


def test_hand_made_players_have_no_riot_check(alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    plain = alice.post("/players", {k: v for k, v in preview["player"].items() if k != "tags"}).json()
    assert plain["riot"] is None


def test_hidden_mode_masks_the_check_and_snapshots_carry_it(alice, riot):
    from app.models import Team
    p = imported(alice)
    assert "riot" not in game_service._mask_player(alice.get(f"/players/{p['id']}").json())
    team = alice.get("/teams?selectable=true").json()[0]
    copy = alice.post(f"/teams/{team['id']}/duplicate").json()
    fields = ("name", "logo", "region", "fanbase", "style1", "style2", "focus1", "focus2")
    roster = {lane: q["id"] for lane, q in copy["roster"].items()} | {p["role"]: p["id"]}
    assert alice.put(f"/teams/{copy['id']}", {**{k: copy[k] for k in fields}, "coach_id": copy["coach"]["id"],
                                              "roster": roster}).status_code == 200
    with SessionLocal() as db:
        snapshot = game_service.build_snapshot(db, db.get(Team, copy["id"]))
    assert snapshot["roster"][p["role"]]["riot"]["import_check"]["status"] == "unedited"

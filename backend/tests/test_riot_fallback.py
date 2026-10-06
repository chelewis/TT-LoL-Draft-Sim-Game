"""Queue fallback for Riot imports: solo, then flex, then normal games, one queue only."""
import httpx
import pytest

from app.api.management import get_riot_client
from app.core.config import settings
from app.integrations.riot import stat_mapper
from app.integrations.riot.client import RiotClient
from app.integrations.riot.config import QUEUE_TIERS
from app.integrations.riot.errors import NotEnoughData
from app.integrations.riot.limiter import RateLimiter
from app.main import app
from app.services import riot_import_service
from tests.riot_fixtures import STRONG, FakeRiotClient

BODY = {"riot_id": "Faker#KR1", "region": "KR"}


@pytest.fixture
def setup(client, monkeypatch):
    """Returns a function that installs a fake Riot client with the given queue sizes."""
    monkeypatch.setattr(settings, "riot_api_key", "test-key")
    monkeypatch.setattr(settings, "riot_user_cooldown_seconds", 0)

    def install(**kw):
        fake = FakeRiotClient(mine=STRONG, **kw)
        riot_import_service.reset_state()
        app.dependency_overrides[get_riot_client] = lambda: fake
        return fake

    yield install
    app.dependency_overrides.pop(get_riot_client, None)
    riot_import_service.reset_state()


def source_of(preview):
    return preview["analysis"]["source"]


# ------------------------------------------------------------------ selection
def test_solo_with_enough_games_is_used_alone_and_not_highlighted(alice, setup):
    fake = setup(games=14, flex=20, normal=20)
    data = alice.post("/riot/preview", BODY).json()
    src = source_of(data)
    assert src["queue"] == "SOLO" and src["is_solo"] is True and src["games"] == 14
    assert not any("less reliable" in n for n in data["analysis"]["notes"])
    # flex and normal were never even looked up
    assert "match_ids:440" not in fake.calls and "match_ids:normal" not in fake.calls
    assert not any(c in ("match:440", "match:normal") for c in fake.calls)


def test_no_solo_history_falls_back_to_flex(alice, setup):
    fake = setup(games=0, flex=12, normal=20)
    data = alice.post("/riot/preview", BODY).json()
    src = source_of(data)
    assert src["queue"] == "FLEX" and src["is_solo"] is False and src["games"] == 12 and src["label"] == "Ranked flex"
    note = next(n for n in data["analysis"]["notes"] if "less reliable" in n)
    assert "ranked solo (0 usable games)" in note and "12 ranked flex games" in note
    assert "match_ids:normal" not in fake.calls                      # stopped at the first queue that qualified


def test_too_few_solo_games_also_falls_back_and_never_mixes(alice, setup):
    setup(games=4, flex=13)
    data = alice.post("/riot/preview", BODY).json()
    assert source_of(data)["queue"] == "FLEX" and source_of(data)["games"] == 13     # 13, not 13 + 4
    assert source_of(data)["tried"]["SOLO"] == 4


def test_falls_back_to_normals_and_skips_aram(alice, setup):
    fake = setup(games=2, flex=3, normal=11, aram=6)
    data = alice.post("/riot/preview", BODY).json()
    src = source_of(data)
    assert src["queue"] == "NORMAL" and src["games"] == 11 and src["label"] == "Normal games"   # the 6 ARAM games ignored
    note = next(n for n in data["analysis"]["notes"] if "less reliable" in n)
    assert "ranked solo (2 usable games)" in note and "ranked flex (3 usable games)" in note and "normal games" in note


def test_rank_follows_the_queue_that_was_used(alice, setup):
    setup(games=0, flex=12, rank={"SOLO": "DIAMOND", "FLEX": "SILVER"})
    rank = alice.post("/riot/preview", BODY).json()["analysis"]["rank"]
    assert rank["tier"] == "SILVER" and rank["budget"] == 32              # not the Diamond solo rank and its 36
    setup(games=0, flex=0, normal=12, rank={"SOLO": None, "FLEX": "EMERALD"})
    rank = alice.post("/riot/preview", BODY).json()["analysis"]["rank"]
    assert rank["tier"] == "EMERALD" and rank["queue"] == "FLEX" and rank["budget"] == 36   # normals borrow whatever rank exists


def test_remakes_do_not_count_towards_the_minimum(alice, setup):
    setup(games=12, flex=15, remakes={"420": 4})          # 12 solo ids but only 8 real games
    data = alice.post("/riot/preview", BODY).json()
    assert source_of(data)["queue"] == "FLEX" and source_of(data)["tried"]["SOLO"] == 8


def test_no_queue_with_enough_games_lists_the_counts(alice, setup):
    setup(games=3, flex=0, normal=6)
    res = alice.post("/riot/preview", BODY)
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "ranked solo 3" in detail and "ranked flex 0" in detail and "normal games 6" in detail
    assert "single queue" in detail


# --------------------------------------------------- persistence and highlighting
def save(api, preview):
    return api.post("/players", {**preview["player"], "riot_ref": preview["riot_ref"]})


def test_source_is_saved_with_the_player(alice, setup):
    setup(games=0, flex=14)
    player = save(alice, alice.post("/riot/preview", BODY).json()).json()
    assert player["riot"]["data_source"] == "FLEX" and player["riot"]["games_used"] == 14
    assert player["riot"]["is_solo_source"] is False
    assert alice.get(f"/players/{player['id']}").json()["riot"]["data_source"] == "FLEX"


def test_solo_import_is_marked_solo_and_manual_players_have_no_source(alice, setup):
    setup(games=14)
    player = save(alice, alice.post("/riot/preview", BODY).json()).json()
    assert player["riot"]["data_source"] == "SOLO" and player["riot"]["is_solo_source"] is True
    manual = alice.post("/players", {**player, "name": "Manual", "riot_ref": None}).json()
    assert manual["riot"] is None


def test_client_cannot_claim_a_different_source(alice, setup):
    setup(games=0, flex=14)
    preview = alice.post("/riot/preview", BODY).json()
    body = {**preview["player"], "riot_ref": preview["riot_ref"], "riot_data_source": "SOLO"}
    assert save_body(alice, body)["riot"]["data_source"] == "FLEX"       # comes from the signed token only


def save_body(api, body):
    return api.post("/players", body).json()


def test_refresh_moves_back_to_solo_once_solo_qualifies(alice, setup):
    fake = setup(games=0, flex=14)
    saved = save(alice, alice.post("/riot/preview", BODY).json()).json()
    assert saved["riot"]["data_source"] == "FLEX"
    fake.queue_games["420"] = 15                   # the account has since played enough solo games
    riot_import_service.reset_state()
    refreshed = alice.post(f"/players/{saved['id']}/riot-refresh").json()
    assert source_of(refreshed)["queue"] == "SOLO"
    updated = alice.put(f"/players/{saved['id']}", {**refreshed["player"], "riot_ref": refreshed["riot_ref"]}).json()
    assert updated["riot"]["data_source"] == "SOLO" and updated["riot"]["is_solo_source"] is True


def test_editing_a_saved_player_keeps_its_source(alice, setup):
    setup(games=0, flex=14)
    saved = save(alice, alice.post("/riot/preview", BODY).json()).json()
    edited = alice.put(f"/players/{saved['id']}", {**saved, "name": "Renamed", "riot_ref": None}).json()
    assert edited["riot"]["data_source"] == "FLEX"


def test_other_users_cannot_see_riot_source_when_data_is_hidden():
    from app.services.game_service import _mask_player
    masked = _mask_player({"id": 1, "name": "X", "role": "MID", "riot": {"data_source": "FLEX"}})
    assert "riot" not in masked


# ----------------------------------------------------------------- pure selection
def test_select_source_downloads_only_what_it_needs():
    fetched = []

    def get_ids(tier):
        return [f"{tier['key']}_{i}" for i in range({"SOLO": 3, "FLEX": 10, "NORMAL": 10}[tier["key"]])]

    def get_match(match_id):
        fetched.append(match_id)
        queue = 440 if match_id.startswith("FLEX") else 420
        from tests.riot_fixtures import make_match
        return make_match("me", queue=queue)

    choice = stat_mapper.select_source(QUEUE_TIERS, get_ids, get_match, "me", 10)
    assert choice.tier["key"] == "FLEX" and len(choice.matches) == 10
    assert all(m.startswith("FLEX") for m in fetched)         # the 3 solo ids were too few to download anything


def test_select_source_error_when_nothing_qualifies():
    with pytest.raises(NotEnoughData, match="ranked solo 1, ranked flex 2, normal games 3"):
        stat_mapper.select_source(QUEUE_TIERS, lambda t: ["x"] * {"SOLO": 1, "FLEX": 2, "NORMAL": 3}[t["key"]],
                                  lambda i: {}, "me", 10)


# --------------------------------------------------------------------- client
def test_match_ids_sends_queue_or_type_filters():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=[])

    c = RiotClient("k", transport=httpx.MockTransport(handler), limiter=RateLimiter(max_wait=0.1))
    c.match_ids("NA1", "p", 20, queue=440)
    c.match_ids("NA1", "p", 20, type="normal")
    assert seen[0] == {"queue": "440", "start": "0", "count": "20"}
    assert seen[1] == {"type": "normal", "start": "0", "count": "20"}


def test_wrong_queue_games_are_ignored_by_the_mapper():
    from tests.riot_fixtures import make_match
    matches = [make_match("me", queue=450) for _ in range(12)]            # ARAM
    with pytest.raises(NotEnoughData):
        stat_mapper.analyse(matches, "me", 32, queue_ids={400, 430, 490})
    assert stat_mapper.analyse(matches, "me", 32).games == 12             # no queue filter: legacy behaviour


def test_login_is_checked_before_the_feature_flag(client):
    # with no key configured an anonymous caller gets 401, not a hint about server configuration
    assert client.post("/api/v1/riot/preview", json=BODY).status_code == 401

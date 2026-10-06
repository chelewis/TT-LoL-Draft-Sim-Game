"""Riot account import through the HTTP API, using a fake Riot client."""
import pytest

from app.api.management import get_riot_client
from app.core.config import settings
from app.main import app
from app.services import riot_import_service
from tests.conftest import Api
from tests.riot_fixtures import STRONG, WEAK, FakeRiotClient

BODY = {"riot_id": "Faker#KR1", "region": "KR"}


@pytest.fixture
def riot(client, monkeypatch):
    """Enable the feature with a fake Riot client; returns that client for call counting."""
    fake = FakeRiotClient(mine=STRONG)
    monkeypatch.setattr(settings, "riot_api_key", "test-key")
    monkeypatch.setattr(settings, "riot_user_cooldown_seconds", 0)
    riot_import_service.reset_state()
    app.dependency_overrides[get_riot_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_riot_client, None)
    riot_import_service.reset_state()


def save_from_preview(api, preview, **overrides):
    p = preview["player"]
    body = {**p, "riot_ref": preview["riot_ref"], **overrides}
    return api.post("/players", body)


def test_feature_is_off_without_a_key(alice):
    assert alice.get("/riot/status").json()["enabled"] is False
    res = alice.post("/riot/preview", BODY)
    assert res.status_code == 503 and "not set up" in res.json()["detail"]


def test_status_when_enabled(alice, riot):
    status = alice.get("/riot/status").json()
    assert status["enabled"] is True and "KR" in status["regions"] and "EUW1" in status["regions"]


def test_requires_login(client, riot):
    assert client.post("/api/v1/riot/preview", json=BODY).status_code == 401


def test_preview_builds_a_valid_player_draft(alice, riot):
    res = alice.post("/riot/preview", BODY)
    assert res.status_code == 200, res.text
    data = res.json()
    p = data["player"]
    assert p["name"] == "Faker" and p["role"] == "MID"
    assert all(1 <= p[s] <= 10 for s in ("aggr", "aware", "pos", "dmg", "cs"))
    assert sum(p[s] for s in ("aggr", "aware", "pos", "dmg", "cs")) <= 32       # fitted to the soft ceiling
    assert data["analysis"]["fitted_to_budget"] is True
    assert data["analysis"]["games"] == 14
    # pool: most played champions that exist in the game; the unknown one is skipped and reported
    assert len(p["pool"]) == 5 and len(set(p["pool"])) == 5
    names = {c["id"]: c["name"] for c in alice.get("/champions").json()}
    pooled = [names[i] for i in p["pool"]]
    assert pooled[0] == "Ahri"
    explain = data["analysis"]
    assert set(explain["breakdown"]) == {"aggr", "aware", "pos", "dmg", "cs"}
    assert explain["breakdown"]["cs"][0]["how"] and explain["fit"]["budget"] == 32
    assert explain["fit"]["total_before"] > explain["fit"]["total_after"]          # fitted to the ceiling
    assert data["riot"] == {"game_name": "Faker", "tag_line": "KR1", "region": "KR"}
    assert data["riot_ref"]
    assert "_puuid" not in data and "puuid" not in str(data["riot"])      # the puuid never reaches the browser


def test_short_pools_are_topped_up_from_mastery_and_unknown_champions_reported(alice, riot):
    riot.champion_cycle = (103, 266, 9999)         # Ahri, Aatrox and a champion our game does not have
    data = alice.post("/riot/preview", BODY).json()
    names = {c["id"]: c["name"] for c in alice.get("/champions").json()}
    pooled = [names[i] for i in data["player"]["pool"]]
    assert pooled[:2] == ["Ahri", "Aatrox"] or pooled[:2] == ["Aatrox", "Ahri"]
    assert "Wukong" in pooled                        # from mastery, matched via its Data Dragon display name
    assert len(pooled) == 3 and data["analysis"]["missing_pool_slots"] == 2
    notes = " ".join(data["analysis"]["notes"])
    assert "Brand New Champion" in notes and "Only 3" in notes


def test_saving_a_preview_creates_a_linked_player(alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    res = save_from_preview(alice, preview)
    assert res.status_code == 201, res.text
    player = res.json()
    assert player["riot"]["game_name"] == "Faker" and player["riot"]["verified"] is False
    assert player["over_budget_by"] == 0 and player["is_default"] is False
    assert alice.get(f"/players/{player['id']}").json()["riot"]["region"] == "KR"
    # a hand-made player has no link
    manual = alice.post("/players", {**preview["player"], "name": "Manual"}).json()
    assert manual["riot"] is None


def test_preview_reports_rank_and_saving_keeps_it(alice, riot):
    riot.ranks = {"SOLO": "EMERALD", "FLEX": "GOLD"}
    preview = alice.post("/riot/preview", BODY).json()
    assert preview["analysis"]["rank"] == {"queue": "SOLO", "tier": "EMERALD", "division": "II", "lp": 45,
                                           "wins": 60, "losses": 40, "budget": 36, "floor": 28}
    assert preview["analysis"]["fit"]["budget"] == 36
    assert "league" in riot.calls
    # the browser cannot claim a better rank: it comes from the signed token only
    saved = alice.post("/players", {**preview["player"], "riot_ref": preview["riot_ref"],
                                    "riot_rank_tier": "CHALLENGER"}).json()
    assert saved["riot"]["rank"] == {"queue": "SOLO", "tier": "EMERALD", "division": "II", "lp": 45,
                                     "wins": 60, "losses": 40}
    assert saved["stat_budget"] == 36
    assert alice.get(f"/players/{saved['id']}").json()["riot"]["rank"]["tier"] == "EMERALD"


def preview_at(alice, riot, rank):
    riot.ranks = {"SOLO": rank, "FLEX": None}
    riot_import_service.reset_state()
    return alice.post("/riot/preview", BODY).json()


def stat_total(player):
    return sum(player[s] for s in ("aggr", "aware", "pos", "dmg", "cs"))


def test_stat_ceiling_rises_with_rank(alice, riot):
    totals = []
    for rank, cap in (("BRONZE", 28), ("GOLD", 32), ("DIAMOND", 36), ("MASTER", 40), ("CHALLENGER", 48)):
        data = preview_at(alice, riot, rank)             # the same dominant games every time
        assert data["analysis"]["rank"]["budget"] == data["analysis"]["fit"]["budget"] == cap
        assert stat_total(data["player"]) <= cap
        totals.append(stat_total(data["player"]))
    assert totals == sorted(totals) and len(set(totals)) == len(totals)         # strictly higher at each step
    assert any(f"{48}-point ceiling for Challenger" in n for n in data["analysis"]["notes"])


def test_weak_games_are_raised_to_the_floor_for_the_rank(alice, riot):
    riot.mine = WEAK
    unranked = preview_at(alice, riot, None)
    raw_total = stat_total(unranked["player"])
    assert unranked["analysis"]["raised_to_floor"] is False and raw_total < 10       # no rank, no floor
    for rank, floor in (("BRONZE", 10), ("GOLD", 28), ("DIAMOND", 28), ("MASTER", 36), ("CHALLENGER", 40)):
        data = preview_at(alice, riot, rank)
        assert data["analysis"]["rank"]["floor"] == data["analysis"]["fit"]["floor"] == floor
        assert data["analysis"]["raised_to_floor"] is True and stat_total(data["player"]) == floor
        assert all(1 <= data["player"][s] <= 10 for s in ("aggr", "aware", "pos", "dmg", "cs"))
        assert data["analysis"]["fit"]["total_before"] == raw_total            # the tooltip shows where they started
        assert any(f"{floor}-point floor" in n for n in data["analysis"]["notes"])


def test_stats_between_floor_and_ceiling_are_left_alone(alice, riot):
    riot.mine = None                                     # an ordinary stat line
    gold, diamond = preview_at(alice, riot, "GOLD"), preview_at(alice, riot, "DIAMOND")
    assert 28 <= stat_total(gold["player"]) <= 32
    assert gold["analysis"]["fitted_to_budget"] is False and gold["analysis"]["raised_to_floor"] is False
    assert gold["player"] == diamond["player"]


def test_saved_players_are_flagged_against_their_own_ceiling(alice, riot):
    high = preview_at(alice, riot, "CHALLENGER")
    saved = save_from_preview(alice, high).json()
    assert saved["stat_total"] > 32 and saved["stat_budget"] == 48 and saved["over_budget_by"] == 0
    low = preview_at(alice, riot, "BRONZE")
    edited = save_from_preview(alice, low, name="Padded", aggr=7, aware=7, pos=6, dmg=6, cs=6).json()    # 32
    assert edited["stat_budget"] == 28 and edited["over_budget_by"] == 4
    # a hand-made player with the same stats keeps the standard ceiling
    manual = alice.post("/players", {**low["player"], "name": "Manual", "aggr": 7, "aware": 7, "pos": 6, "dmg": 6,
                                     "cs": 6}).json()
    assert manual["stat_budget"] == 32 and manual["over_budget_by"] == 0


def test_unranked_account_gets_the_standard_ceiling_and_says_so(alice, riot):
    riot.ranks = {"SOLO": None, "FLEX": "DIAMOND"}          # solo stats never borrow the flex rank
    preview = alice.post("/riot/preview", BODY).json()
    rank = preview["analysis"]["rank"]
    assert rank["tier"] is None and rank["budget"] == 32 and rank["floor"] == 0
    assert any("No rank was found" in n for n in preview["analysis"]["notes"])
    saved = save_from_preview(alice, preview).json()
    assert saved["riot"]["rank"] is None and saved["stat_budget"] == 32


def test_refreshing_updates_the_saved_rank(alice, riot):
    riot.ranks = {"SOLO": "GOLD", "FLEX": None}
    saved = save_from_preview(alice, alice.post("/riot/preview", BODY).json()).json()
    assert saved["riot"]["rank"]["tier"] == "GOLD"
    riot.ranks = {"SOLO": None, "FLEX": None}               # the season reset: no rank any more
    riot_import_service.reset_state()
    refreshed = alice.post(f"/players/{saved['id']}/riot-refresh").json()
    updated = alice.put(f"/players/{saved['id']}", {**refreshed["player"], "riot_ref": refreshed["riot_ref"]}).json()
    assert updated["riot"]["rank"] is None


def test_user_can_edit_the_preview_before_saving(alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    res = save_from_preview(alice, preview, name="My Faker", aggr=9, dmg=9)
    player = res.json()
    assert player["name"] == "My Faker" and player["aggr"] == 9
    assert player["over_budget_by"] >= 0 and player["riot"] is not None   # still linked; ceiling is soft


def test_ref_tokens_cannot_be_forged_or_borrowed(client, alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    bob = Api(client, "bob")
    assert save_from_preview(bob, preview).status_code == 400                       # someone else's token
    assert alice.post("/players", {**preview["player"], "riot_ref": "not-a-token"}).status_code == 400


def test_second_import_of_same_account_is_cached(alice, riot):
    alice.post("/riot/preview", BODY)
    calls = len(riot.calls)
    again = alice.post("/riot/preview", {"riot_id": "faker#kr1", "region": "kr"})
    assert again.status_code == 200 and len(riot.calls) == calls            # no new Riot requests
    assert again.json()["riot_ref"]


def test_duplicate_import_is_flagged_in_notes(alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    save_from_preview(alice, preview)
    riot_import_service.reset_state()
    again = alice.post("/riot/preview", BODY).json()
    assert any("already imported" in n for n in again["analysis"]["notes"])


def test_refresh_returns_a_new_draft_without_changing_the_player(alice, riot):
    preview = alice.post("/riot/preview", BODY).json()
    saved = save_from_preview(alice, preview, aggr=2).json()
    riot_import_service.reset_state()
    res = alice.post(f"/players/{saved['id']}/riot-refresh")
    assert res.status_code == 200
    assert res.json()["player"]["aggr"] != 2 and res.json()["riot_ref"]
    assert alice.get(f"/players/{saved['id']}").json()["aggr"] == 2          # nothing saved until the user does so


def test_refresh_rules(client, alice, riot):
    manual = alice.post("/players", {"name": "M", "role": "TOP", "aggr": 5, "aware": 5, "pos": 5, "dmg": 5, "cs": 5,
                                     "pool": [1, 2, 3, 4, 5]}).json()
    assert alice.post(f"/players/{manual['id']}/riot-refresh").status_code == 400
    default = next(p for p in alice.get("/players").json() if p["is_default"])
    assert alice.post(f"/players/{default['id']}/riot-refresh").status_code == 403
    bob = Api(client, "bob")
    assert bob.post(f"/players/{manual['id']}/riot-refresh").status_code == 404


def test_input_and_riot_errors(alice, riot):
    assert alice.post("/riot/preview", {"riot_id": "no-tag-here", "region": "KR"}).status_code == 400
    assert alice.post("/riot/preview", {"riot_id": "A#B", "region": "MARS"}).status_code == 400
    assert alice.post("/riot/preview", {**BODY, "role": "ADC"}).status_code == 400
    missing = alice.post("/riot/preview", {"riot_id": "Nobody#0000", "region": "KR"})
    assert missing.status_code == 404 and "no record" in missing.json()["detail"]
    riot.games = 4
    short = alice.post("/riot/preview", {**BODY, "role": "TOP"})
    assert short.status_code == 422 and "at least 10" in short.json()["detail"]


def test_per_user_cooldown(alice, riot, monkeypatch):
    monkeypatch.setattr(settings, "riot_user_cooldown_seconds", 60)
    riot_import_service.reset_state()
    riot.accounts[("other", "na1")] = {"puuid": "puuid-other", "gameName": "Other", "tagLine": "NA1"}
    assert alice.post("/riot/preview", BODY).status_code == 200
    second = alice.post("/riot/preview", {"riot_id": "Other#NA1", "region": "NA1"})
    assert second.status_code == 429 and "wait" in second.json()["detail"]


def test_riot_details_are_hidden_from_opponents_when_player_data_is_hidden():
    from app.services.game_service import _mask_player
    masked = _mask_player({"id": 1, "name": "Faker", "role": "MID", "aggr": 5, "riot": {"game_name": "Faker"}})
    assert "riot" not in masked and "aggr" not in masked and masked["hidden"] is True

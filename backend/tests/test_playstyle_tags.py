"""Playstyle tags: earning rules, suggestions, the engine hooks, saving on players, and admin management."""
from dataclasses import replace

import pytest

from app.api.management import get_optional_riot_client, get_riot_client
from app.core.config import settings
from app.game.comfort import comfort_modifier
from app.game.config import LANES, simulation_config
from app.game.models import PlayerSpec
from app.game.playstyle import adjust_comfort, effect_totals
from app.game.state import Match
from app.integrations.riot import challenges, stat_mapper
from app.main import app
from app.services import riot_import_service
from tests.conftest import Api
from tests.riot_fixtures import STRONG, WEAK, FakeRiotClient

BODY = {"riot_id": "Faker#KR1", "region": "KR"}
SOLO_BOLO, LIZARD, JACK = 203301, 402206, 401106


# ------------------------------------------------------------------ unit
CH_TAG = {"key": "duelist", "polarity": "positive", "source": "challenge",
          "rule": {"challenges": [{"id": SOLO_BOLO, "name": "Solo Bolo"}], "min_level": "DIAMOND"}}
MATCH_TAG = {"key": "poor_farmer", "polarity": "negative", "source": "match",
             "rule": {"metric": "cs_per_min", "op": "<=", "value": 5.5, "lanes": {"SUPPORT": None, "TOP": 5.0}}}


def progress(*rows):
    return {"challenges": [{"challengeId": cid, "level": lvl, "percentile": pct} for cid, lvl, pct in rows]}


def test_challenge_tag_needs_the_minimum_level():
    assert stat_mapper.earned_tags([CH_TAG], progress((SOLO_BOLO, "PLATINUM", 0.2)), {}, "MID") == []
    earned = stat_mapper.earned_tags([CH_TAG], progress((SOLO_BOLO, "MASTER", 0.01)), {}, "MID")
    assert earned[0]["key"] == "duelist" and earned[0]["evidence"]["level"] == "MASTER"
    assert earned[0]["evidence"]["challenge_name"] == "Solo Bolo"
    # no challenge data at all (the endpoint failed): no challenge tags
    assert stat_mapper.earned_tags([CH_TAG], None, {}, "MID") == []


def test_match_tag_uses_lane_thresholds():
    low = {"cs_per_min": 5.2}
    assert [e["key"] for e in stat_mapper.earned_tags([MATCH_TAG], None, low, "MID")] == ["poor_farmer"]
    assert stat_mapper.earned_tags([MATCH_TAG], None, low, "TOP") == []          # TOP threshold is 5.0
    assert stat_mapper.earned_tags([MATCH_TAG], None, {"cs_per_min": 0.5}, "SUPPORT") == []   # not for supports
    ev = stat_mapper.earned_tags([MATCH_TAG], None, low, "MID")[0]["evidence"]
    assert ev["threshold"] == 5.5 and ev["value"] == 5.2 and ev["label"] == "CS per minute"


def test_suggestions_put_negatives_first_then_best_levels_and_cap_at_five():
    def e(key, polarity="positive", level=None, pct=None):
        return {"key": key, "polarity": polarity, "evidence": {"level": level, "percentile": pct}}
    earned = [e("a", level="DIAMOND", pct=0.1), e("b", level="CHALLENGER", pct=0.001), e("neg", "negative"),
              e("c", level="DIAMOND", pct=0.01), e("d", level="MASTER"), e("f", level="DIAMOND", pct=0.5)]
    assert stat_mapper.suggest_tags(earned, 5) == ["neg", "b", "d", "c", "a"]


def test_effects_are_summed_and_clamped_per_hook():
    spec = PlayerSpec(1, "P", "MID", 20, 5, 5, 5, 5, 5, (), (("objective", 0.05), ("objective", 0.05),
                                                             ("cs_rate", -0.04), ("not_a_hook", 9.0)))
    assert effect_totals(spec) == {"objective": 0.06, "cs_rate": -0.04}       # objective cap is 0.06


def test_pool_hooks_change_the_comfort_modifier():
    cfg = simulation_config()
    vulnerable, best = comfort_modifier("VULNERABLE", cfg), comfort_modifier("BEST", cfg)
    assert adjust_comfort(vulnerable, "VULNERABLE", {"off_pool_penalty": 0.5}) == pytest.approx(vulnerable / 2)
    assert adjust_comfort(vulnerable, "VULNERABLE", {"off_pool_penalty": 1.0}) == 0
    assert adjust_comfort(vulnerable, "VULNERABLE", {"off_pool_penalty": -0.5}) == pytest.approx(vulnerable * 1.5)
    assert adjust_comfort(best, "BEST", {"pool_best_bonus": 0.15}) == pytest.approx(best * 1.15)
    assert adjust_comfort(best, "BEST", {"off_pool_penalty": 1.0}) == best                # only off-pool picks


# ---------------------------------------------------------------- engine
def _with_tags(setup, lane, *effects):
    roster = dict(setup.roster)
    roster[lane] = replace(roster[lane], tag_effects=tuple(effects))
    return replace(setup, roster=roster)


def test_tags_reach_the_engine(make_teams, champions):
    blue, red = make_teams(3)
    cfg = simulation_config()
    plain = Match(blue, red, champions, 7, cfg)
    farmer = Match(_with_tags(blue, "MID", ("cs_rate", 0.04)), red, champions, 7, cfg)
    poor = Match(_with_tags(blue, "MID", ("cs_rate", -0.04)), red, champions, 7, cfg)
    base = plain.teams["BLUE"].players["MID"].cs_rate
    assert farmer.teams["BLUE"].players["MID"].cs_rate == pytest.approx(base * 1.04)
    assert poor.teams["BLUE"].players["MID"].cs_rate == pytest.approx(base * 0.96)

    hunter = Match(_with_tags(blue, "JUNGLE", ("objective", 0.06)), red, champions, 7, cfg)
    assert hunter.objective_control(hunter.teams["BLUE"], roll=False) > plain.objective_control(plain.teams["BLUE"], roll=False)
    breaker = Match(_with_tags(blue, "TOP", ("tower", 0.06)), red, champions, 7, cfg)
    t = breaker.teams["BLUE"]
    assert breaker.objective_control(t, roll=False) == plain.objective_control(plain.teams["BLUE"], roll=False)
    assert breaker.objective_control(t, roll=False, towers=True) > breaker.objective_control(t, roll=False)

    playmaker = Match(_with_tags(blue, "MID", ("initiative", 0.08)), red, champions, 7, cfg)
    assert playmaker.initiative_chance(playmaker.teams["BLUE"]) >= plain.initiative_chance(plain.teams["BLUE"])


def test_champion_ocean_softens_off_pool_picks(make_teams, champions):
    blue, red = make_teams(3)
    cfg = simulation_config()
    lane = "MID"
    off_pool = next(cid for cid in champions if cid not in blue.roster[lane].pool and cid not in red.lineup.values()
                    and cid not in blue.lineup.values())
    lineup = {**blue.lineup, lane: off_pool}
    blue = replace(blue, lineup=lineup)
    plain = Match(blue, red, champions, 7, cfg).teams["BLUE"].players[lane]
    ocean = Match(_with_tags(blue, lane, ("off_pool_penalty", 0.5)), red, champions, 7, cfg).teams["BLUE"].players[lane]
    trick = Match(_with_tags(blue, lane, ("off_pool_penalty", -0.5)), red, champions, 7, cfg).teams["BLUE"].players[lane]
    assert plain.tier == "VULNERABLE" and plain.comfort == pytest.approx(-0.10)
    assert ocean.comfort == pytest.approx(-0.05) and trick.comfort == pytest.approx(-0.15)


def test_untagged_players_simulate_exactly_as_before(make_teams, champions):
    from app.game.simulation_engine import simulate_match
    blue, red = make_teams(5)
    a = simulate_match(blue, red, champions, 11, simulation_config())
    b = simulate_match(_with_tags(blue, "MID"), red, champions, 11, simulation_config())    # no effects
    assert a == b


# ------------------------------------------------------------------ API
@pytest.fixture
def riot(client, monkeypatch):
    fake = FakeRiotClient(mine=STRONG, challenges={SOLO_BOLO: ("MASTER", 0.01), LIZARD: ("DIAMOND", 0.05),
                                                   JACK: ("PLATINUM", 0.2)})
    monkeypatch.setattr(settings, "riot_api_key", "test-key")
    monkeypatch.setattr(settings, "riot_user_cooldown_seconds", 0)
    riot_import_service.reset_state()
    challenges.clear_cache()
    app.dependency_overrides[get_riot_client] = lambda: fake
    app.dependency_overrides[get_optional_riot_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_riot_client, None)
    app.dependency_overrides.pop(get_optional_riot_client, None)
    riot_import_service.reset_state()


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_usernames", ["Root"])
    return Api(client, "root")


def save(api, preview, **overrides):
    return api.post("/players", {**preview["player"], "riot_ref": preview["riot_ref"], **overrides})


def test_preview_earns_and_suggests_tags(alice, riot):
    data = alice.post("/riot/preview", BODY).json()
    earned = {t["key"]: t for t in data["analysis"]["tags"]["earned"]}
    assert set(earned) == {"duelist", "objective_hunter"}           # Jack of All Champs is only Platinum
    assert earned["duelist"]["evidence"]["level"] == "MASTER" and earned["duelist"]["polarity"] == "positive"
    assert data["player"]["tags"] == ["duelist", "objective_hunter"]
    assert data["analysis"]["tags"]["challenges_loaded"] is True

    saved = save(alice, data).json()
    assert [t["key"] for t in saved["tags"]] == ["duelist", "objective_hunter"]
    assert {t["key"] for t in saved["earned_tags"]} == {"duelist", "objective_hunter"}
    assert saved["tags"][0]["effects"] == [{"hook": "lane_score", "value": 0.03}]


def test_weak_recent_games_earn_negative_tags_which_can_be_removed(alice, riot):
    riot.mine = WEAK
    data = alice.post("/riot/preview", BODY).json()
    keys = data["player"]["tags"]
    negatives = [t["key"] for t in data["analysis"]["tags"]["earned"] if t["polarity"] == "negative"]
    assert {"reckless", "passive", "poor_farmer", "map_blind"} <= set(negatives)
    assert len(keys) == 5 and keys[:4] == negatives[:4]               # negatives are suggested first
    kept = save(alice, data, tags=["duelist"]).json()                 # the user drops every negative tag
    assert [t["key"] for t in kept["tags"]] == ["duelist"]


def test_tags_must_be_earned_and_at_most_five(alice, riot):
    data = alice.post("/riot/preview", BODY).json()
    res = save(alice, data, tags=["farmer"])
    assert res.status_code == 400 and "not earned" in res.json()["detail"]
    assert save(alice, data, tags=["duelist", "duelist"]).status_code == 400
    assert save(alice, data, tags=["no_such_tag"]).status_code == 400
    riot.mine = WEAK
    riot_import_service.reset_state()                                # skip the cached preview
    weak = alice.post("/riot/preview", BODY).json()
    six = [t["key"] for t in weak["analysis"]["tags"]["earned"]][:6]
    assert len(six) == 6 and save(alice, weak, tags=six).status_code == 400


def test_hand_made_players_cannot_have_tags(alice, riot):
    data = alice.post("/riot/preview", BODY).json()
    body = {k: v for k, v in data["player"].items() if k != "tags"}
    res = alice.post("/players", {**body, "tags": ["duelist"]})
    assert res.status_code == 400 and "imported from Riot" in res.json()["detail"]
    plain = alice.post("/players", body).json()
    assert plain["tags"] == [] and plain["earned_tags"] == []
    # editing a player keeps its tags when the body leaves them out, and [] removes them
    saved = save(alice, data).json()
    edit = {k: v for k, v in saved.items() if k in body}
    assert [t["key"] for t in alice.put(f"/players/{saved['id']}", edit).json()["tags"]] == ["duelist", "objective_hunter"]
    assert alice.put(f"/players/{saved['id']}", {**edit, "tags": []}).json()["tags"] == []


def test_challenge_failure_still_imports(alice, riot):
    riot.challenges = "fail"
    data = alice.post("/riot/preview", BODY).json()
    assert data["analysis"]["tags"]["challenges_loaded"] is False
    assert any("challenge data could not be loaded" in n for n in data["analysis"]["notes"])
    assert save(alice, data).status_code == 201


def test_refresh_keeps_chosen_tags_that_are_still_earned(alice, riot):
    saved = save(alice, alice.post("/riot/preview", BODY).json(), tags=["objective_hunter"]).json()
    riot_import_service.reset_state()
    again = alice.post(f"/players/{saved['id']}/riot-refresh").json()
    assert again["player"]["tags"] == ["objective_hunter"]
    riot.challenges = {SOLO_BOLO: "MASTER"}                           # dragon progress no longer counts
    riot_import_service.reset_state()
    lost = alice.post(f"/players/{saved['id']}/riot-refresh").json()
    assert lost["player"]["tags"] == ["duelist"]                      # falls back to the suggestion


def test_admin_manages_tags(admin, alice, riot):
    assert alice.get("/admin/playstyle-tags").status_code == 403
    tags = admin.get("/admin/playstyle-tags").json()
    assert {"champion_ocean", "one_trick", "reckless"} <= {t["key"] for t in tags}
    opts = admin.get("/admin/playstyle-tags/options").json()
    assert {"off_pool_penalty", "survival"} <= {h["hook"] for h in opts["hooks"]}
    assert [c["name"] for c in opts["challenges"]] == ["Solo Bolo"]   # disabled challenges are left out

    body = {"key": "lane_bully", "label": "Lane Bully", "description": "Wins lane.", "polarity": "positive",
            "source": "challenge", "rule": {"challenges": [{"id": JACK, "name": "Jack of All Champs"}],
                                            "min_level": "PLATINUM"},
            "effects": [{"hook": "lane_score", "value": 0.02}]}
    created = admin.post("/admin/playstyle-tags", body)
    assert created.status_code == 201, created.text
    assert admin.post("/admin/playstyle-tags", body).status_code == 400                       # key taken
    assert admin.post("/admin/playstyle-tags", {**body, "key": "x2", "effects": [{"hook": "lane_score", "value": 0.5}]}).status_code == 400
    assert admin.post("/admin/playstyle-tags", {**body, "key": "x3", "effects": [{"hook": "nope", "value": 0.01}]}).status_code == 400
    assert admin.post("/admin/playstyle-tags", {**body, "key": "x4", "source": "match",
                                                "rule": {"metric": "nope", "op": ">=", "value": 1}}).status_code == 400
    # the new tag is earned straight away by the next import
    data = alice.post("/riot/preview", BODY).json()
    assert "lane_bully" in {t["key"] for t in data["analysis"]["tags"]["earned"]}
    assert "lane_bully" in [t["key"] for t in alice.get("/playstyle-tags").json()]

    # a tag kept on a player is disabled rather than deleted, and disappears from that player
    saved = save(alice, data, tags=["lane_bully"]).json()
    tag_id = created.json()["id"]
    assert admin.delete(f"/admin/playstyle-tags/{tag_id}").json() == {"deleted": False, "disabled": True, "players": 1}
    assert alice.get(f"/players/{saved['id']}").json()["tags"] == []
    unused = admin.post("/admin/playstyle-tags", {**body, "key": "unused"}).json()
    assert admin.delete(f"/admin/playstyle-tags/{unused['id']}").json()["deleted"] is True


def test_game_snapshot_keeps_tag_effects_after_admin_edits(admin, alice, riot):
    from app.core.database import SessionLocal
    from app.models import Team
    from app.services import game_service

    saved = save(alice, alice.post("/riot/preview", BODY).json(), tags=["duelist"]).json()
    source = alice.get("/teams?selectable=true").json()[0]
    copy = alice.post(f"/teams/{source['id']}/duplicate").json()
    fields = ("name", "logo", "region", "fanbase", "style1", "style2", "focus1", "focus2")
    roster = {lane: p["id"] for lane, p in copy["roster"].items()} | {"MID": saved["id"]}
    res = alice.put(f"/teams/{copy['id']}", {**{k: copy[k] for k in fields}, "coach_id": copy["coach"]["id"],
                                             "roster": roster})
    assert res.status_code == 200, res.text
    with SessionLocal() as db:
        snapshot = game_service.build_snapshot(db, db.get(Team, copy["id"]))
    mid = snapshot["roster"]["MID"]
    assert mid["tags"][0]["effects"] == [{"hook": "lane_score", "value": 0.03}]
    assert game_service._player_spec(mid).tag_effects == (("lane_score", 0.03),)

    duelist = next(t for t in admin.get("/admin/playstyle-tags").json() if t["key"] == "duelist")
    edited = {k: duelist[k] for k in ("key", "label", "description", "polarity", "source", "rule", "sort_order")}
    res = admin.put(f"/admin/playstyle-tags/{duelist['id']}", {**edited, "effects": [{"hook": "lane_score", "value": 0.01}]})
    assert res.status_code == 200, res.text
    assert alice.get(f"/players/{saved['id']}").json()["tags"][0]["effects"][0]["value"] == 0.01   # new games
    assert game_service._player_spec(mid).tag_effects == (("lane_score", 0.03),)                  # frozen snapshot
    # snapshots from before tags existed still build an engine player
    legacy = {k: v for k, v in mid.items() if k not in ("tags", "earned_tags")}
    assert game_service._player_spec(legacy).tag_effects == ()

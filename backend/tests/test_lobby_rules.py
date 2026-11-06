"""Lobby rulesets: presets for every lobby option, plus rank and stat total restrictions on the teams."""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Player, Team


def ranked_copy(alice, team_id, tier="GOLD"):
    """Duplicate a default team into alice's account and make every player a ranked Riot import."""
    res = alice.post(f"/teams/{team_id}/duplicate")
    assert res.status_code in (200, 201), res.text
    copy = res.json()
    with SessionLocal() as db:
        team = db.get(Team, copy["id"])
        for i, slot in enumerate(team.slots):
            p = db.get(Player, slot.player_id)
            p.riot_puuid, p.riot_game_name, p.riot_tag_line, p.riot_region = f"puuid-{p.id}", p.name, "T", "KR"
            p.riot_rank_tier = tier
        db.commit()
    return copy["id"]


def team_totals(alice, team_id):
    team = next(t for t in alice.get("/teams").json() if t["id"] == team_id)
    totals = [p["stat_total"] for p in team["roster"].values()]
    return max(totals), sum(totals)


def solo_lobby(alice, **settings):
    res = alice.post("/lobbies", {"mode": "SOLO", "settings": {"timers_enabled": False, **settings}})
    assert res.status_code == 201, res.text
    return res.json()


def pick(alice, lobby, team_id, side="BLUE"):
    return alice.post(f"/lobbies/{lobby['id']}/team", {"team_id": team_id, "side": side})


def test_rulesets_endpoint(alice):
    data = alice.get("/lobbies/rulesets").json()
    keys = [r["key"] for r in data["rulesets"]]
    assert keys == ["ANYTHING_GOES", "PRO", "APEX", "HIGH_ELO", "MID_ELO", "LOW_ELO", "TOURNAMENT"]
    assert data["default"] == "ANYTHING_GOES" and data["rank_tiers"][0] == "IRON"
    tournament = next(r for r in data["rulesets"] if r["key"] == "TOURNAMENT")["settings"]
    assert tournament["series_format"] == "BO3" and tournament["fearless"] and tournament["hide_player_data"]


def test_ruleset_with_creator_edits_is_stored_and_marked_modified(alice):
    preset = next(r for r in alice.get("/lobbies/rulesets").json()["rulesets"] if r["key"] == "HIGH_ELO")["settings"]
    lobby = alice.post("/lobbies", {"settings": {"ruleset": "HIGH_ELO", **preset}}).json()
    s = lobby["settings"]
    assert s["ruleset"] == "HIGH_ELO" and s["ruleset_name"] == "High Elo" and not s["ruleset_modified"]
    assert (s["max_rank"], s["max_player_total"], s["max_team_total"]) == ("DIAMOND", 36, 170)
    edited = alice.post("/lobbies", {"settings": {"ruleset": "HIGH_ELO", **preset, "max_team_total": 160}}).json()
    assert edited["settings"]["max_team_total"] == 160 and edited["settings"]["ruleset_modified"]


def test_validation(alice):
    for bad in ({"ruleset": "UBERS"}, {"max_rank": "WOOD"}, {"max_player_total": 4}, {"max_player_total": 51},
                {"max_team_total": 24}, {"max_team_total": 251}):
        assert alice.post("/lobbies", {"settings": bad}).status_code == 422, bad


def test_rank_limit_blocks_unranked_players(alice, default_team_ids):
    lobby = solo_lobby(alice, max_rank="CHALLENGER")
    res = pick(alice, lobby, default_team_ids[0])
    assert res.status_code == 400 and "has no rank" in res.json()["detail"]


def test_rank_limit_by_tier(alice, default_team_ids):
    gold = ranked_copy(alice, default_team_ids[0], "GOLD")
    master = ranked_copy(alice, default_team_ids[0], "MASTER")
    lobby = solo_lobby(alice, max_rank="DIAMOND")
    assert pick(alice, lobby, gold).status_code == 200
    res = pick(alice, lobby, master, "RED")
    assert res.status_code == 400 and "above the Diamond limit" in res.json()["detail"]


def test_player_and_team_caps_at_the_boundary(alice, default_team_ids):
    team = default_team_ids[0]
    best, total = team_totals(alice, team)
    assert pick(alice, solo_lobby(alice, max_player_total=best, max_team_total=total), team).status_code == 200
    res = pick(alice, solo_lobby(alice, max_player_total=best - 1), team)
    assert res.status_code == 400 and f"(limit {best - 1})" in res.json()["detail"]
    res = pick(alice, solo_lobby(alice, max_team_total=total - 1), team)
    assert res.status_code == 400 and f"Team stats total {total}" in res.json()["detail"]


def test_cpu_team_is_checked_too(alice, default_team_ids):
    gold = ranked_copy(alice, default_team_ids[0], "GOLD")
    lobby = alice.post("/lobbies", {"mode": "CPU", "settings": {"max_rank": "DIAMOND", "timers_enabled": False}}).json()
    assert pick(alice, lobby, gold, "BLUE").status_code == 200
    assert pick(alice, lobby, default_team_ids[1], "RED").status_code == 400


def test_team_list_reports_rule_issues_for_a_game(alice, default_team_ids):
    gold = ranked_copy(alice, default_team_ids[0], "GOLD")
    lobby = solo_lobby(alice, max_rank="DIAMOND")
    teams = {t["id"]: t for t in alice.get(f"/teams?selectable=true&game_id={lobby['game_id']}").json()}
    assert teams[gold]["rule_issues"] == []
    assert teams[default_team_ids[0]]["rule_issues"]
    assert "rule_issues" not in alice.get("/teams?selectable=true").json()[0]


def test_team_edited_after_selection_is_caught_at_ready(alice, default_team_ids):
    gold = ranked_copy(alice, default_team_ids[0], "GOLD")
    lobby = solo_lobby(alice, max_rank="DIAMOND")
    assert pick(alice, lobby, gold, "BLUE").status_code == 200
    assert pick(alice, lobby, gold, "RED").status_code == 200
    with SessionLocal() as db:
        team = db.get(Team, gold)
        db.get(Player, team.slots[0].player_id).riot_rank_tier = "CHALLENGER"
        db.commit()
    res = alice.post(f"/games/{lobby['game_id']}/ready", {"ready": True})
    assert res.status_code == 409 and "no longer meets" in res.json()["detail"]


def test_solo_tournament_is_not_modified_by_forced_visible_data(alice):
    preset = next(r for r in alice.get("/lobbies/rulesets").json()["rulesets"] if r["key"] == "TOURNAMENT")["settings"]
    lobby = alice.post("/lobbies", {"mode": "SOLO", "settings": {"ruleset": "TOURNAMENT", **preset}}).json()
    assert lobby["settings"]["hide_player_data"] is False and not lobby["settings"]["ruleset_modified"]


# ------------------------------------------------------- duplicate / mirror clauses
from app.game.config import LANES  # noqa: E402
from tests.test_import_seal import riot  # noqa: E402,F401  (fixture)
from tests.test_sharing import coach, imported  # noqa: E402


def same_account_team(alice, fake, name="Faker x5"):
    """A complete team whose five players are all imports of the same Riot account."""
    roster = {lane: imported(alice, fake, role=lane)["id"] for lane in LANES}
    res = alice.post("/teams", {"name": name, "style1": "early", "style2": "teamfight",
                                "coach_id": coach(alice)["id"], "roster": roster})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_tournament_preset_turns_both_clauses_on(alice):
    rulesets = {r["key"]: r["settings"] for r in alice.get("/lobbies/rulesets").json()["rulesets"]}
    assert rulesets["TOURNAMENT"]["duplicate_clause"] and rulesets["TOURNAMENT"]["mirror_clause"]
    assert not any(s["duplicate_clause"] or s["mirror_clause"] for k, s in rulesets.items() if k != "TOURNAMENT")


def test_duplicate_clause_blocks_one_riot_account_twice(alice, riot):  # noqa: F811
    team = same_account_team(alice, riot)
    assert pick(alice, solo_lobby(alice), team).status_code == 200            # off: allowed
    res = pick(alice, solo_lobby(alice, duplicate_clause=True), team)
    assert res.status_code == 400 and "Faker#KR1 is on the team 5 times (same Riot account)" in res.json()["detail"]


def test_duplicate_clause_matches_hand_made_players_by_name(alice, default_team_ids):
    copy = alice.post(f"/teams/{default_team_ids[0]}/duplicate").json()
    with SessionLocal() as db:
        team = db.get(Team, copy["id"])
        for slot in team.slots[:2]:
            db.get(Player, slot.player_id).name = "Twin"
        db.commit()
    res = pick(alice, solo_lobby(alice, duplicate_clause=True), copy["id"])
    assert res.status_code == 400 and "Twin is on the team 2 times (same player name)" in res.json()["detail"]


def test_mirror_clause_blocks_the_same_player_on_both_sides(alice, default_team_ids):
    team = default_team_ids[0]
    off = solo_lobby(alice)
    assert pick(alice, off, team, "BLUE").status_code == 200 and pick(alice, off, team, "RED").status_code == 200
    on = solo_lobby(alice, mirror_clause=True)
    assert pick(alice, on, team, "BLUE").status_code == 200
    res = pick(alice, on, team, "RED")
    assert res.status_code == 400 and "already on the other team" in res.json()["detail"]
    # a copy of the same team is still the same players
    copy = alice.post(f"/teams/{team}/duplicate").json()["id"]
    assert pick(alice, on, copy, "RED").status_code == 400
    assert pick(alice, on, default_team_ids[1], "RED").status_code == 200
    # the team list says which side each team is blocked for
    listed = {t["id"]: t for t in alice.get(f"/teams?selectable=true&game_id={on['game_id']}").json()}
    assert listed[team]["mirror_issues"]["RED"] and not listed[team]["mirror_issues"]["BLUE"]


def test_mirror_clause_is_checked_again_at_ready(alice, default_team_ids):
    on = solo_lobby(alice, mirror_clause=True)
    blue = alice.post(f"/teams/{default_team_ids[0]}/duplicate").json()
    assert pick(alice, on, blue["id"], "BLUE").status_code == 200
    assert pick(alice, on, default_team_ids[1], "RED").status_code == 200
    red = next(t for t in alice.get("/teams").json() if t["id"] == default_team_ids[1])
    with SessionLocal() as db:   # blue's owner renames a player to match one on red
        db.get(Player, blue["roster"]["TOP"]["id"]).name = red["roster"]["TOP"]["name"]
        db.commit()
    res = alice.post(f"/games/{on['game_id']}/ready", {"ready": True})
    assert res.status_code == 409 and "already on the other team" in res.json()["detail"]

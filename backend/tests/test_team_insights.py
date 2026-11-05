"""Team notes for the team editor (game/team_insights.py and POST /team-insights)."""
import dataclasses

from app.data.loader import seed_team_setup
from app.game import team_insights
from app.game.config import LANES, simulation_config
from app.game.models import MatchupTable

CFG = simulation_config()


def setup(seed, team_id=1):
    return seed_team_setup(seed, team_id, dict(zip(LANES, range(1, 6))))


def analyse(seed, champions, roster=None, styles=("teamfight", "scaling"), focus=("MID",), coach=None, team_id=1):
    team = setup(seed, team_id)
    return team_insights.analyse(team.roster if roster is None else roster, styles, focus,
                                 team.coach if coach is None else coach, champions, MatchupTable(), CFG, 32)


def test_full_roster_gets_every_section(seed, champions):
    out = analyse(seed, champions)
    assert out["filled"] == 5
    assert out["strengths"] or out["weaknesses"]
    assert [s["style"] for s in out["styles"]] and len(out["suggested_styles"]) == 2
    assert {s["style"] for s in out["styles"]} == set(team_insights.STYLES)
    assert all(0 <= s["score"] <= 100 for s in out["styles"])
    assert len(out["suggested_focus"]) == 2 and len(set(out["suggested_focus"])) == 2
    assert out["comps"]


def test_suggested_styles_never_pair_early_with_scaling(seed, champions):
    for team_id in (1, 2):
        out = analyse(seed, champions, team_id=team_id)
        assert set(out["suggested_styles"]) != {"early", "scaling"}


def test_comps_use_each_players_pool_once(seed, champions):
    team = setup(seed)
    out = analyse(seed, champions)
    for comp in out["comps"]:
        ids = [p["champion_id"] for p in comp["picks"].values()]
        assert len(ids) == len(set(ids)) == 5
        for lane, pick in comp["picks"].items():
            assert pick["champion_id"] in team.roster[lane].pool
    keys = [tuple(sorted((l, p["champion_id"]) for l, p in c["picks"].items())) for c in out["comps"]]
    assert len(keys) == len(set(keys))


def test_empty_slots_are_a_weakness_and_comps_cover_the_filled_lanes(seed, champions):
    team = setup(seed)
    roster = {l: p for l, p in team.roster.items() if l in ("TOP", "MID")}
    out = analyse(seed, champions, roster=roster)
    assert out["filled"] == 2
    assert any(n["title"] == "Empty roster slots" for n in out["weaknesses"])
    assert all(set(c["picks"]) == {"TOP", "MID"} for c in out["comps"])


def test_no_players_still_answers(seed, champions):
    out = analyse(seed, champions, roster={})
    assert out["filled"] == 0 and out["comps"] == [] and out["focus"] == []


def test_stronger_stats_turn_weaknesses_into_strengths(seed, champions):
    team = setup(seed)
    strong = {l: dataclasses.replace(p, aggr=10, aware=10, pos=10, dmg=10, cs=10) for l, p in team.roster.items()}
    weak = {l: dataclasses.replace(p, aggr=2, aware=2, pos=2, dmg=2, cs=2) for l, p in team.roster.items()}
    titles = lambda notes: {n["title"] for n in notes}
    s, w = analyse(seed, champions, roster=strong), analyse(seed, champions, roster=weak)
    assert {"Fight initiative", "Objective control"} <= titles(s["strengths"])
    assert {"Slow to start fights", "Losing objectives"} <= titles(w["weaknesses"])


def test_a_mismatched_primary_style_is_flagged(seed, champions):
    out = analyse(seed, champions)
    wrong = next(s for s in team_insights.STYLES if s not in out["suggested_styles"])
    flagged = analyse(seed, champions, styles=(wrong,))
    assert any(n["title"] == "Playstyle doesn't suit the roster" for n in flagged["weaknesses"])


def test_api_analyses_unsaved_choices(alice, default_team_ids):
    team = alice.get(f"/teams/{default_team_ids[0]}").json()
    body = {"style1": "early", "style2": "teamfight", "focus1": "MID", "focus2": None,
            "coach_id": team["coach"]["id"], "roster": {l: p["id"] for l, p in team["roster"].items() if p}}
    res = alice.post("/team-insights", body)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["filled"] == 5 and out["comps"] and out["suggested_styles"]


def test_api_rejects_players_the_user_cannot_see(alice, bob):
    pool = [c["id"] for c in bob.get("/champions").json()[:5]]
    pid = bob.post("/players", {"name": "Hidden", "role": "TOP", "age": 20, "region": "EU", "aggr": 6, "aware": 6,
                                "pos": 6, "dmg": 6, "cs": 6, "pool": pool})
    assert pid.status_code == 201, pid.text
    res = alice.post("/team-insights", {"roster": {"TOP": pid.json()["id"]}})
    assert res.status_code in (403, 404)


def test_config_sends_the_team_rules_for_field_help(alice):
    rules = alice.get("/config").json()["team_rules"]
    assert rules["primary_bonus"] == CFG["team_style"]["primary_bonus"]
    assert rules["focus_cs_bonus"] == CFG["cs"]["focus_bonus"]
    assert rules["coach_synergy_scale"] == CFG["coach"]["synergy_scale"]

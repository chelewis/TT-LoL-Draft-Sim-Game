"""Admin module: who may use it, and the two champion x champion win rate matrices."""
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.data import matchup_seed
from app.data.seed_db import seed_database
from app.models import ChampionMatchup
from tests.conftest import Api


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_usernames", ["Root"])       # matched without regard to case
    return Api(client, "root")


def cells(api, kind):
    return {(a, b): (rate, games, edited) for a, b, rate, games, edited in api.get(f"/admin/matchups/{kind}").json()["cells"]}


def put(api, kind, *changes):
    return api.put(f"/admin/matchups/{kind}", {"changes": [{"a": a, "b": b, "win_rate": rate} for a, b, rate in changes]})


def test_only_listed_users_are_admins(admin, alice):
    assert admin.user["is_admin"] is True and alice.user["is_admin"] is False
    assert admin.get("/auth/me").json()["is_admin"] is True
    assert alice.get("/auth/me").json()["is_admin"] is False
    assert alice.get("/admin/matchups/ally").status_code == 403
    assert put(alice, "ally", (1, 2, 60)).status_code == 403
    assert alice.post("/admin/matchups/ally/reset").status_code == 403
    assert admin.client.get("/api/v1/admin/matchups/ally").status_code == 401         # not signed in


def test_same_team_matrix_is_seeded_and_against_team_starts_empty(admin):
    body = admin.get("/admin/matchups/ally").json()
    names = [c["name"] for c in body["champions"]]
    assert names == sorted(names) and "Ahri" in names
    assert len(body["cells"]) > 10000
    assert all(a < b and not edited for a, b, _rate, _games, edited in body["cells"])
    assert admin.get("/admin/matchups/enemy").json()["cells"] == []
    assert admin.get("/admin/matchups/nonsense").status_code == 404


def test_edits_are_saved_either_way_round(admin):
    assert put(admin, "ally", (2, 1, 61.26), (3, 5, None)).json() == {"updated": 2}
    after = cells(admin, "ally")
    assert after[(1, 2)][0] == 61.3 and after[(1, 2)][2] is True                     # stored once, rounded
    assert after[(3, 5)][0] is None and after[(3, 5)][2] is True                     # cleared
    assert (2, 1) not in after


def test_against_team_values_are_mirrored(admin):
    assert put(admin, "enemy", (1, 2, 55), (9, 4, 70)).status_code == 200
    after = cells(admin, "enemy")
    assert after[(1, 2)][0] == 55.0
    assert after[(4, 9)][0] == 30.0                 # 9 beats 4 seventy percent of the time, so 4 beats 9 thirty
    assert len(after) == 2
    assert cells(admin, "ally")[(1, 2)][2] is False                                  # the other matrix is untouched


def test_bad_edits_are_rejected(admin):
    assert put(admin, "ally", (1, 1, 50)).status_code == 400
    assert put(admin, "ally", (1, 999999, 50)).status_code == 400
    assert put(admin, "ally", (1, 2, 101)).status_code == 422
    assert put(admin, "ally", (1, 2, -1)).status_code == 422
    assert admin.put("/admin/matchups/ally", {"changes": []}).status_code == 422
    assert put(admin, "nonsense", (1, 2, 50)).status_code == 404
    assert cells(admin, "ally")[(1, 2)][2] is False


def test_edits_survive_a_restart_and_reset_brings_the_seed_back(admin):
    seeded = cells(admin, "ally")[(1, 2)][0]
    put(admin, "ally", (1, 2, 99))
    with SessionLocal() as db:
        seed_database(db)                                                            # what every backend start runs
    assert cells(admin, "ally")[(1, 2)] == (99.0, 0, True)
    assert admin.post("/admin/matchups/ally/reset").json()["cells"] == len(cells(admin, "ally"))
    assert cells(admin, "ally")[(1, 2)][0] == seeded and cells(admin, "ally")[(1, 2)][2] is False
    put(admin, "enemy", (1, 2, 55))
    assert admin.post("/admin/matchups/enemy/reset").json() == {"cells": 0}          # no seed file for it yet
    assert cells(admin, "enemy") == {}


def test_against_team_seed_file_is_read_from_the_first_champions_side(admin, tmp_path):
    (tmp_path / "champion_counter.csv").write_text(
        "champion_a,champion_b,games,wins,win_rate,expected_win_rate,smoothed_win_rate,synergy\n"
        "Ahri,Aatrox,10,6,60.0,50.0,56.0,+6.0\nAhri,Nobody,5,5,100.0,50.0,60.0,+10.0\n", encoding="utf-8")
    with SessionLocal() as db:
        assert matchup_seed.import_matchups(db, "enemy", seed_dir=tmp_path) == 1     # the unknown name is skipped
        db.commit()
        row = db.query(ChampionMatchup).filter_by(kind="enemy").one()
        assert row.champion_a_id < row.champion_b_id                                 # Aatrox (1) before Ahri (2)
        assert (row.win_rate, row.games, row.wins) == (44.0, 10, 4)
        assert matchup_seed.import_matchups(db, "enemy", seed_dir=tmp_path) == 0     # already has rows: left alone

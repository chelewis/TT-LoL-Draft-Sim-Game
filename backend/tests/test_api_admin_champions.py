"""Admin → Champions → Info: viewing and editing champion win rates, pick rates and attributes."""
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.data.seed_db import seed_database
from tests.conftest import Api


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_usernames", ["Root"])
    return Api(client, "root")


def listing(api):
    return {c["id"]: c for c in api.get("/admin/champions").json()["champions"]}


def put(api, *changes):
    return api.put("/admin/champions", {"changes": [{"id": cid, "values": values} for cid, values in changes]})


def test_only_admins_can_use_it(admin, alice):
    assert alice.get("/admin/champions").status_code == 403
    assert put(alice, (1, {"pick_rate": 10})).status_code == 403
    assert alice.post("/admin/champions/reset", {}).status_code == 403


def test_lists_every_champion_with_its_info(admin, champions):
    body = admin.get("/admin/champions").json()
    assert body["fields"]["win_rate"] == {"kind": "float", "min": 0, "max": 100, "choices": []}
    rows = {c["id"]: c for c in body["champions"]}
    assert set(champions) <= set(rows)
    ahri = next(c for c in rows.values() if c["name"] == "Ahri")
    seed = champions[ahri["id"]]
    assert ahri["win_rate"] == seed.win_rate and ahri["pick_rate"] == seed.pick_rate
    assert ahri["crowd_control"] == seed.cc and ahri["edited"] == [] and ahri["seed"] == {}


def test_edits_are_saved_and_marked(admin, champions):
    assert put(admin, (2, {"pick_rate": 20.456, "damage": 5, "damage_type": "PM"})).json() == {"updated": 3}
    ahri = listing(admin)[2]
    assert ahri["pick_rate"] == 20.46 and ahri["damage_type"] == "PM"
    assert ahri["edited"] == ["damage", "damage_type", "pick_rate"]
    assert ahri["seed"]["pick_rate"] == champions[2].pick_rate        # what a reset would bring back
    assert listing(admin)[1]["edited"] == []          # other champions are untouched


@pytest.mark.parametrize("values", [
    {"win_rate": 101}, {"pick_rate": -1}, {"damage": 2.5}, {"scaling": 4}, {"damage_type": "X"},
    {"name": "Bob"}, {"enabled": 0}, {"damage": "3"},
])
def test_bad_edits_are_rejected_and_nothing_is_saved(admin, values):
    response = put(admin, (1, {"pick_rate": 30}), (2, values))
    assert response.status_code in (400, 422)
    assert listing(admin)[1]["edited"] == []          # all or nothing


def test_unknown_champion_is_rejected(admin):
    assert put(admin, (999999, {"pick_rate": 1})).status_code == 400
    assert admin.put("/admin/champions", {"changes": []}).status_code == 422


def test_edits_survive_a_restart_and_reset_brings_the_csv_back(admin, champions):
    put(admin, (1, {"win_rate": 60, "pick_rate": 2}), (2, {"utility": 0}))
    with SessionLocal() as db:
        seed_database(db)                                       # what every backend start runs
    after = listing(admin)
    assert after[1]["win_rate"] == 60 and after[1]["pick_rate"] == 2 and after[2]["utility"] == 0

    assert admin.post("/admin/champions/reset", {"ids": [1]}).json() == {"reset": 1}
    after = listing(admin)
    assert after[1]["win_rate"] == champions[1].win_rate and after[1]["edited"] == []
    assert after[2]["utility"] == 0                             # only the champion asked for

    assert admin.post("/admin/champions/reset", {}).json() == {"reset": 1}
    assert listing(admin)[2]["utility"] == champions[2].utility


def test_edits_reach_the_simulation_data(admin):
    put(admin, (2, {"win_rate": 70}))
    listed = {c["id"]: c for c in admin.get("/champions").json()}
    assert listed[2]["win_rate"] == 70

import pytest

from app.main import FRONTEND_DIST

pytestmark = pytest.mark.skipif(not (FRONTEND_DIST / "index.html").exists(), reason="frontend not built")


def test_spa_routes_serve_index(client):
    res = client.get("/game/12")
    assert res.status_code == 200 and "<div id=\"root\">" in res.text
    assert client.get("/").status_code == 200


def test_api_paths_are_not_swallowed_by_the_spa(client):
    assert client.get("/api/v1/does-not-exist").status_code == 404
    assert client.get("/api/v1/does-not-exist").headers["content-type"].startswith("application/json")


def test_path_traversal_is_not_served(client):
    res = client.get("/..%2f..%2fbackend/app/main.py")
    assert "create_app" not in res.text

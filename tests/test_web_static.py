from fastapi.testclient import TestClient

from app.main import create_app


def _dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><div id=app></div>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return d


def test_index_is_served_for_app_paths(tmp_path, client):
    c = TestClient(create_app(_dist(tmp_path)))
    for path in ("/", "/s/abc123/setup", "/s/abc123/plan/map"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert "id=app" in r.text


def test_assets_are_served_as_files(tmp_path, client):
    c = TestClient(create_app(_dist(tmp_path)))
    assert c.get("/assets/app.js").text == "console.log(1)"


def test_unknown_api_path_stays_404_json(tmp_path, client):
    r = TestClient(create_app(_dist(tmp_path))).get("/api/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_api_still_wins_over_the_fallback(tmp_path, client):
    assert isinstance(TestClient(create_app(_dist(tmp_path))).get("/api/scenarios").json(), list)


def test_files_outside_dist_are_not_served(tmp_path, client):
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    r = TestClient(create_app(_dist(tmp_path))).get("/..%2Fsecret.txt")
    assert "nope" not in r.text


def test_without_dist_there_is_no_fallback(tmp_path, client):
    assert TestClient(create_app(tmp_path / "missing")).get("/s/abc/setup").status_code == 404

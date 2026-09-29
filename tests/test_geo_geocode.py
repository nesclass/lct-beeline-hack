import pytest

from app.geo import geocode as gc


class Http:
    def __init__(self, hits=None, fail=False):
        self.hits, self.fail, self.calls = hits or [], fail, []

    def get(self, url, params=None, **kw):
        self.calls.append(params["q"])
        if self.fail:
            raise ConnectionError("нет сети")
        hits = self.hits

        class R:
            def raise_for_status(self): pass
            def json(self): return hits
        return R()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(gc, "_memo", {})
    monkeypatch.setenv("GEOCODER_URL", "http://geo")


def test_found_address_gives_its_point():
    http = Http([{"lat": "55.616625", "lon": "37.658361"}])
    assert gc.geocode("Царицыно, ул. Бакинская, д. 3", http) == (55.616625, 37.658361)
    assert http.calls[0] == "ул. Бакинская, д. 3, Москва"


def test_point_outside_the_road_graph_is_ignored():
    assert gc.geocode("Сочи, Курортный пр., 1", Http([{"lat": "43.58", "lon": "39.72"}])) is None


def test_network_failure_keeps_the_form_point():
    assert gc.geocode("Царицыно, ул. Бакинская, д. 3", Http(fail=True)) is None


def test_off_switch(monkeypatch):
    monkeypatch.setenv("GEOCODER_URL", "off")
    http = Http([{"lat": "55.6", "lon": "37.6"}])
    assert gc.geocode("Царицыно, ул. Бакинская, д. 3", http) is None and http.calls == []


def test_request_is_saved_at_the_geocoded_point(client, sid, monkeypatch):
    from app.routers import catalog
    monkeypatch.setattr(catalog, "geocode", lambda a: (55.616625, 37.658361))
    body = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3", "district": "Царицыно",
            "type": "Нет линка", "skill": "local", "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}
    r = client.post(f"/api/sessions/{sid}/requests", json=body).json()["request"]
    assert (r["lat"], r["lon"]) == (55.616625, 37.658361)

"""День диспетчера целиком на уровне API, на каждом сценарии, с перезапуском сервера посередине."""
import pytest
from fastapi.testclient import TestClient

from app import geo, state, store
from app.geo import cache
from app.geo.haversine import Haversine
from app.main import create_app

URGENT = {"lat": 55.62, "lon": 37.67, "address": "Царицыно, ул. Луганская, 7", "district": "Царицыно",
          "type": "Обрыв магистрали", "skill": "emergency", "work_type": "emergency",
          "tw_start": "13:30", "tw_end": "16:00", "priority": "urgent"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "DIR", tmp_path / "geo")
    monkeypatch.setattr(cache, "_memo", {})
    monkeypatch.setattr(geo, "_provider", Haversine())
    db = tmp_path / "app.sqlite"

    def boot():
        state.use(store.connect(db))
        return TestClient(create_app(tmp_path / "no-dist"))
    return boot


@pytest.mark.parametrize("scenario", ["normal", "peak", "short-staffed"])
def test_dispatcher_day(world, scenario):
    c = world()
    sid = c.post("/api/sessions", json={"scenario": scenario}).json()["session_id"]
    c.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3, "priority": "balance"})
    v = c.post(f"/api/sessions/{sid}/variants").json()
    rec = next(x for x in v["variants"] if x["key"] == v["recommended"])
    assert c.post(f"/api/sessions/{sid}/variants/{rec['plan_id']}/approve").json()["status"] == "planned"

    plan = c.get(f"/api/sessions/{sid}/plan").json()["plan"]
    busy = next(rt for rt in plan["routes"] if sum(1 for s in rt["stops"] if s["start"] > "14:00") >= 1)
    c.put(f"/api/sessions/{sid}/clock", json={"time": "13:30"})
    c.post(f"/api/sessions/{sid}/requests", json=URGENT)
    c.put(f"/api/sessions/{sid}/clock", json={"time": "13:45"})
    c.post(f"/api/sessions/{sid}/engineers/{busy['engineer_id']}/unavailable", json={"mode": "leave", "time": "14:00"})
    imp = c.get(f"/api/sessions/{sid}/impact").json()
    assert imp["since"] == "13:30" and imp["urgent_unassigned"] == 1

    draft = c.post(f"/api/sessions/{sid}/replan", json={"mode": "minimal"}).json()
    assert draft["accepted"] is False and draft["diff"]
    assert c.get(f"/api/sessions/{sid}").json()["status"] == "draft"

    c = world()                                                # перезапуск сервера посреди дня
    assert c.get(f"/api/sessions/{sid}").json()["status"] == "draft"
    got = c.post(f"/api/sessions/{sid}/plan/accept").json()
    assert got["plan_id"] == draft["plan_id"] and busy["engineer_id"] in got["affected"]
    h = c.get(f"/api/sessions/{sid}/history").json()
    assert [x["kind"] for x in h] == ["variant", "replan"]
    a = c.get(f"/api/sessions/{sid}/analytics").json()
    assert a["current"]["engineers_used"] <= a["baseline"]["engineers_used"]
    r = c.post(f"/api/sessions/{sid}/assistant", json={"context": {"kind": "changes"}, "question": "что поменялось?"}).json()
    assert r["text"]
    assert c.put(f"/api/sessions/{sid}/clock", json={"time": "12:00"}).status_code == 409
    assert c.post(f"/api/sessions/{sid}/replan").status_code == 409

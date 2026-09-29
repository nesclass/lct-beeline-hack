import pytest


@pytest.fixture
def fast(client, sid):
    """Быстрый движок: тесты не должны ждать OR-Tools."""
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    return sid


def test_plan_is_built(client, fast):
    r = client.post(f"/api/sessions/{fast}/plan")
    assert r.status_code == 200
    m = r.json()["metrics"]
    assert m["assigned"] > 40
    assert m["assigned"] + m["unassigned"] == 59


def test_session_becomes_planned(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    body = client.get(f"/api/sessions/{fast}").json()
    assert body["status"] == "planned"
    assert body["plan_id"]


def test_plan_view_carries_engineers_and_requests(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    body = client.get(f"/api/sessions/{fast}/plan").json()
    assert len(body["engineers"]) == 12
    assert len(body["requests"]) == 59
    assert body["plan"]["routes"]
    assert body["dict"]["skills"]


def test_plan_reports_travel_source(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    assert client.get(f"/api/sessions/{fast}/plan").json()["travel_source"] in ("osrm", "haversine")


def test_reading_plan_before_building_is_409(client, sid):
    r = client.get(f"/api/sessions/{sid}/plan")
    assert r.status_code == 409


def test_padding_makes_the_plan_more_cautious(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    lean = client.post(f"/api/sessions/{sid}/plan").json()["metrics"]
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 30, "travel_pct": 30, "travel_min": 10})
    padded = client.post(f"/api/sessions/{sid}/plan").json()["metrics"]
    # строго: при нестрогом сравнении тест проходил и с выключенным запасом
    assert padded["assigned"] < lean["assigned"]


def test_plan_carries_the_padding_from_settings(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 20, "travel_pct": 30, "travel_min": 5})
    built = client.post(f"/api/sessions/{sid}/plan").json()["robustness"]
    assert (built["work_factor"], built["travel_factor"], built["travel_min"]) == (0.2, 0.3, 5)
    assert client.get(f"/api/sessions/{sid}/plan").json()["plan"]["robustness"] == built


def test_plan_of_one_session_is_not_visible_in_another(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    other = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
    assert client.get(f"/api/sessions/{other}/plan").status_code == 409


def test_engineer_unavailable_before_the_plan_gets_no_work(client, fast):
    """«Заболел с утра» — базовое расписание строится без него, событие считается учтённым,
    и следующее перепланирование его тоже не возвращает."""
    client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={"finish_current": True})
    plan = client.post(f"/api/sessions/{fast}/plan").json()
    e01 = next(rt for rt in plan["routes"] if rt["engineer_id"] == "E01")
    assert e01["stops"] == []
    assert e01["unavailable_from"] == "09:00"
    body = client.get(f"/api/sessions/{fast}").json()
    assert body["status"] == "planned" and body["pending_events"] == []

    client.put(f"/api/sessions/{fast}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{fast}/requests",
                json={"lat": 55.617, "lon": 37.660, "skill": "local", "work_type": "local_repair",
                      "tw_start": "15:00", "tw_end": "17:00"})
    again = client.post(f"/api/sessions/{fast}/replan").json()
    e01 = next(rt for rt in again["routes"] if rt["engineer_id"] == "E01")
    assert e01["stops"] == []


def test_rebuilding_after_a_replan_is_409(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    client.put(f"/api/sessions/{fast}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={"finish_current": True})
    assert client.post(f"/api/sessions/{fast}/replan").status_code == 200
    r = client.post(f"/api/sessions/{fast}/plan")
    assert r.status_code == 409
    assert "перепланирован" in r.json()["detail"]


class ConstantRoads:
    """Подставной OSRM: любая дорога — 11 минут и 1 км любым транспортом. По формуле
    по прямой такое не получается, поэтому видно, откуда план взял время в пути."""

    def matrix(self, points):
        from app.geo.provider import MODES
        ids = list(points)
        return {"ids": ids, "source": "osrm",
                "km": {(a, b): 0.0 if a == b else 1.0 for a in ids for b in ids},
                "min": {(a, b, m): 0 if a == b else 11 for a in ids for b in ids for m in MODES}}

    def line(self, a, b, mode):
        return [a, b]


def test_plan_travels_by_the_geo_matrix(client, fast, monkeypatch):
    from app import geo
    monkeypatch.setattr(geo, "_provider", ConstantRoads())
    plan = client.post(f"/api/sessions/{fast}/plan").json()
    legs = {s["leg_min"] for rt in plan["routes"] for s in rt["stops"]}
    assert legs == {11}, f"план считал дорогу мимо матрицы гео-слоя: {sorted(legs)}"
    assert plan["travel_mode"] == "external"
    assert client.get(f"/api/sessions/{fast}/plan").json()["travel_source"] == "osrm"
    assert client.get(f"/api/sessions/{fast}/routes").json()["source"] == "osrm"


def test_estimated_matrix_is_reported_as_such(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    assert client.get(f"/api/sessions/{fast}/plan").json()["travel_source"] == "haversine"


def test_plan_with_every_engineer_unavailable_explains_itself(client):
    sid = client.post("/api/sessions", json={"scenario": "short-staffed"}).json()["session_id"]
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 2})
    for e in client.get(f"/api/sessions/{sid}/engineers").json():
        client.post(f"/api/sessions/{sid}/engineers/{e['id']}/unavailable", json={"finish_current": True})
    r = client.post(f"/api/sessions/{sid}/plan")
    assert r.status_code == 200
    a = next(iter(r.json()["assignments"].values()))
    assert a["reason"]["code"] == "ENGINEER_LOST"
    assert "нет ни одного доступного инженера" in a["text"]
    assert client.get(f"/api/sessions/{sid}/routes").json()["routes"] == []


def test_leave_declared_before_the_plan_cuts_the_shift(client, sid):
    from app import state, store
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    with store.tx(state.con()):
        store.add_event(state.con(), sid, {"type": "engineer_unavailable", "time": "14:00",
                                           "engineer_id": "E01", "finish_current": True})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    rt = next(r for r in plan["routes"] if r["engineer_id"] == "E01")
    assert rt["unavailable_from"] == "14:00"
    assert rt["stops"], "до 14:00 он работает"
    assert all(s["finish"] <= "14:00" for s in rt["stops"])


def test_leave_declared_before_the_plan_is_removed_by_the_replan_that_reaches_it(client, sid):
    """Уход в 14:00 до базового плана: перепланирование в 15:00 показывает инженера снятым."""
    from app import state, store
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    with store.tx(state.con()):
        store.add_event(state.con(), sid, {"type": "engineer_unavailable", "time": "14:00",
                                           "engineer_id": "E01", "finish_current": True})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    rid = next(s["request_id"] for rt in plan["routes"] for s in rt["stops"] if s["start"] >= "16:00")
    client.put(f"/api/sessions/{sid}/clock", json={"time": "15:00"})
    client.post(f"/api/sessions/{sid}/requests/{rid}/cancel", json={})
    new = client.post(f"/api/sessions/{sid}/replan").json()
    assert new["diff"]["engineers"]["E01"]["status"] == "removed"

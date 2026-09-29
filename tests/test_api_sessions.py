def test_scenarios_are_listed(client):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    assert {s["id"] for s in r.json()} == {"normal", "peak", "short-staffed"}


def test_session_is_created_with_scenario_content(client, sid):
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["scenario"] == "normal"
    assert body["status"] == "new"
    assert body["plan_id"] is None
    assert body["counts"] == {"engineers": 12, "requests": 59}


def test_session_clock_starts_at_first_shift(client, sid):
    assert client.get(f"/api/sessions/{sid}").json()["clock"] == "09:00"


def test_scenario_events_are_not_copied(client, sid):
    assert client.get(f"/api/sessions/{sid}").json()["pending_events"] == []


def test_unknown_scenario_is_404(client):
    r = client.post("/api/sessions", json={"scenario": "нет-такого"})
    assert r.status_code == 404
    assert "сценар" in r.json()["detail"].lower()


def test_unknown_session_is_404(client):
    assert client.get("/api/sessions/ffffffff").status_code == 404


def test_settings_round_trip(client, sid):
    assert client.get(f"/api/sessions/{sid}/settings").json()["engine"] == "ortools"
    r = client.put(f"/api/sessions/{sid}/settings",
                   json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                         "work_pct": 10, "travel_pct": 10, "travel_min": 2})
    assert r.status_code == 200
    assert client.get(f"/api/sessions/{sid}/settings").json()["work_pct"] == 10


def test_settings_reject_out_of_range(client, sid):
    r = client.put(f"/api/sessions/{sid}/settings",
                   json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                         "work_pct": 500, "travel_pct": 0, "travel_min": 0})
    assert r.status_code == 422


def test_clock_can_be_moved(client, sid):
    assert client.put(f"/api/sessions/{sid}/clock", json={"time": "13:30"}).status_code == 200
    assert client.get(f"/api/sessions/{sid}").json()["clock"] == "13:30"


def test_clock_rejects_garbage(client, sid):
    assert client.put(f"/api/sessions/{sid}/clock", json={"time": "не время"}).status_code == 422


def test_two_sessions_are_independent(client):
    a = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
    b = client.post("/api/sessions", json={"scenario": "short-staffed"}).json()["session_id"]
    assert a != b
    assert client.get(f"/api/sessions/{a}").json()["counts"]["engineers"] == 12
    assert client.get(f"/api/sessions/{b}").json()["counts"]["engineers"] == 8


def test_sessions_are_listed_newest_first(client):
    a = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
    b = client.post("/api/sessions", json={"scenario": "peak"}).json()["session_id"]
    rows = client.get("/api/sessions").json()
    assert [r["session_id"] for r in rows[:2]] == [b, a]
    assert rows[0] | {"updated_at": 0, "created_at": 0} == {
        "session_id": b, "scenario": "peak", "title": "Пиковая нагрузка", "clock": "09:00",
        "status": "new", "pending": 0, "created_at": 0, "updated_at": 0}


def test_building_a_plan_moves_the_session_up(client):
    a = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
    client.post("/api/sessions", json={"scenario": "peak"})
    client.put(f"/api/sessions/{a}/settings", json={"engine": "greedy", "time_limit": 2})
    client.post(f"/api/sessions/{a}/plan")
    assert client.get("/api/sessions").json()[0]["session_id"] == a

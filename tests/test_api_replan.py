import pytest

NEW = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3",
       "district": "Царицыно", "type": "Нет линка", "skill": "local",
       "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}


@pytest.fixture
def planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    client.post(f"/api/sessions/{sid}/plan")
    return sid


def test_replan_before_any_plan_is_409(client, sid):
    r = client.post(f"/api/sessions/{sid}/replan")
    assert r.status_code == 409
    assert "базов" in r.json()["detail"].lower()


def test_replan_without_changes_is_409(client, planned):
    r = client.post(f"/api/sessions/{planned}/replan")
    assert r.status_code == 409


def test_losing_an_engineer_produces_a_new_plan(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"finish_current": True})
    r = client.post(f"/api/sessions/{planned}/replan")
    assert r.status_code == 200
    plan = r.json()
    assert plan["replan_of"]
    assert plan["now"] == "13:00"
    assert plan["diff"] is not None


def test_session_returns_to_planned(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"finish_current": True})
    client.post(f"/api/sessions/{planned}/replan")
    body = client.get(f"/api/sessions/{planned}").json()
    assert body["status"] == "draft"
    assert body["pending_events"] == []
    client.post(f"/api/sessions/{planned}/plan/accept")
    body = client.get(f"/api/sessions/{planned}").json()
    assert body["status"] == "planned"


def test_started_work_is_frozen(client, planned):
    before = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    after = client.post(f"/api/sessions/{planned}/replan").json()
    locked_seen = False
    for rt in after["routes"]:
        for s in rt["stops"]:
            if s["locked"]:
                locked_seen = True
                assert before["assignments"][s["request_id"]]["engineer_id"] == rt["engineer_id"]
    assert locked_seen


def test_new_request_lands_in_the_new_plan(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    rid = client.post(f"/api/sessions/{planned}/requests", json=NEW).json()["request"]["id"]
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    assert rid in plan["assignments"]


def test_urgent_request_is_scheduled(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    rid = client.post(f"/api/sessions/{planned}/requests",
                      json={**NEW, "priority": "urgent", "skill": "emergency",
                            "work_type": "emergency", "tw_start": "13:00",
                            "tw_end": "15:30", "required_transport": "car"}).json()["request"]["id"]
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    assert plan["assignments"][rid]["engineer_id"] is not None


def test_clock_at_the_very_end_of_day_does_not_crash(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "23:59"})
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    r = client.post(f"/api/sessions/{planned}/replan")
    assert r.status_code == 200
    assert r.json()["metrics"]["engineers_total"] == 12
    stops = [s for rt in r.json()["routes"] for s in rt["stops"]]
    assert stops, "нечего проверять: в плане нет остановок"
    assert all(s["locked"] for s in stops), "в конце дня всё уже начато, значит заморожено"


def test_clock_before_any_shift_does_not_crash(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "00:01"})
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    r = client.post(f"/api/sessions/{planned}/replan")
    assert r.status_code == 200
    assert all(not s["locked"] for rt in r.json()["routes"] for s in rt["stops"])


def test_second_replan_keeps_the_unavailable_engineer_out(client, planned):
    """Недоступность погашена первым перепланированием и во второе уже не передаётся —
    инженер всё равно не должен вернуться в расписание."""
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"finish_current": True})
    first = client.post(f"/api/sessions/{planned}/replan").json()
    e01 = next(rt for rt in first["routes"] if rt["engineer_id"] == "E01")
    assert e01["unavailable_from"] == "12:00"
    assert all(s["locked"] for s in e01["stops"])

    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:30"})
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    second = client.post(f"/api/sessions/{planned}/replan").json()
    e01 = next(rt for rt in second["routes"] if rt["engineer_id"] == "E01")
    assert e01.get("unavailable_from") == "12:00", "второе перепланирование забыло о недоступности"
    assert all(s["locked"] for s in e01["stops"]), "недоступному инженеру снова раздали заявки"


def test_replan_uses_the_current_padding(client, planned):
    """Экран настроек — источник истины: запас, выставленный после базового плана,
    действует на перепланирование (и сохраняется вместе с ним)."""
    client.put(f"/api/sessions/{planned}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 20, "travel_pct": 30, "travel_min": 5})
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    rb = plan["robustness"]
    assert (rb["work_factor"], rb["travel_factor"], rb["travel_min"]) == (0.2, 0.3, 5)
    stored = client.get(f"/api/sessions/{planned}/plan").json()["plan"]["robustness"]
    assert stored == rb


def test_clock_cannot_go_back_past_the_replan(client, planned):
    """Перепланирование заморозило сделанное к 13:00; часы раньше этого разморозили бы его."""
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    client.post(f"/api/sessions/{planned}/replan")
    r = client.put(f"/api/sessions/{planned}/clock", json={"time": "12:59"})
    assert r.status_code == 409
    assert client.get(f"/api/sessions/{planned}").json()["clock"] == "13:00"
    assert client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"}).status_code == 200
    assert client.put(f"/api/sessions/{planned}/clock", json={"time": "14:00"}).status_code == 200


def test_clock_can_go_back_over_a_base_plan(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    assert client.put(f"/api/sessions/{planned}/clock", json={"time": "10:00"}).status_code == 200

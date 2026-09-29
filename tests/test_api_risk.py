import pytest


@pytest.fixture
def planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    client.post(f"/api/sessions/{sid}/plan")
    return sid


def test_plan_carries_risk(client, planned):
    risk = client.post(f"/api/sessions/{planned}/plan").json()["risk"]
    assert risk is not None
    assert "tol" in risk and "late_prob" in risk
    assert risk["stress"]["expected_late"] >= 0


def test_risk_is_returned_in_the_view(client, planned):
    assert client.get(f"/api/sessions/{planned}/plan").json()["risk"] is not None


def test_tolerances_cover_every_scheduled_stop(client, planned):
    body = client.get(f"/api/sessions/{planned}/plan").json()
    scheduled = {s["request_id"] for rt in body["plan"]["routes"] for s in rt["stops"]}
    assert scheduled <= set(body["risk"]["tol"])


def test_padding_reduces_expected_lateness(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    lean = client.post(f"/api/sessions/{sid}/plan").json()["risk"]["stress"]["expected_late"]
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 20, "travel_pct": 20, "travel_min": 5})
    padded = client.post(f"/api/sessions/{sid}/plan").json()["risk"]["stress"]["expected_late"]
    assert padded < lean


def test_explain_assigned_request(client, planned):
    rows = client.get(f"/api/sessions/{planned}/requests").json()
    rid = next(r["id"] for r in rows if r["assigned_to"])
    body = client.get(f"/api/sessions/{planned}/explain/{rid}").json()
    assert body["engineer_id"]
    assert body["text"]
    assert body["reason"]["constraints_ok"]


def test_explain_unassigned_request_names_a_reason(client, planned):
    rows = client.get(f"/api/sessions/{planned}/requests").json()
    unassigned = [r["id"] for r in rows if not r["assigned_to"]]
    if not unassigned:
        pytest.skip("в этом прогоне всё назначено")
    body = client.get(f"/api/sessions/{planned}/explain/{unassigned[0]}").json()
    assert body["engineer_id"] is None
    assert body["reason"]["code"] in ("SKILL", "TRANSPORT", "WINDOW_REACH", "SHIFT_FIT",
                                      "BUSY", "DISPLACED", "ENGINEER_LOST")


def test_explain_unknown_request_is_404(client, planned):
    assert client.get(f"/api/sessions/{planned}/explain/R999").status_code == 404


def test_replanned_risk_covers_only_the_unfinished_tail(client, planned):
    """Оценка риска относится к тому, что ещё предстоит, и считается из настоящей точки,
    а не из депо: для уже выполненного запас прочности бессмыслен."""
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"finish_current": True})
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    risk = plan["risk"]
    assert risk is not None, "риск перепланированного расписания должен считаться"
    locked = {s["request_id"] for rt in plan["routes"] for s in rt["stops"] if s["locked"]}
    tail = {s["request_id"] for rt in plan["routes"] for s in rt["stops"] if not s["locked"]}
    assert locked, "нечего проверять: при 13:00 ничего не заморожено"
    assert tail, "нечего проверять: нет незамороженного остатка"
    assert not (set(risk["tol"]) & locked), "запас прочности посчитан для уже сделанного"
    assert tail & set(risk["tol"]), "остаток дня не оценён"


def test_replanned_risk_is_assessed_from_the_current_position(client, planned, monkeypatch):
    """Оценке риска отдаётся задача, где инженеры стоят там, где их застал план, а не в депо
    с начала смены. Перехватываем то, что уходит в assess_safe."""
    from app import planning
    from planner.model import hhmm

    seen = []
    real = planning.assess_safe

    def spy(p, routes, cfg):
        seen.append(p)
        return real(p, routes, cfg)

    monkeypatch.setattr(planning, "assess_safe", spy)
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"finish_current": True})
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    assert len(seen) == 1
    p = seen[0]
    moved = [rt for rt in plan["routes"] if rt["start"]["node"] != rt["engineer_id"]]
    assert moved, "нечего проверять: все инженеры ещё в депо"
    for rt in plan["routes"]:
        e = p.engineers[rt["engineer_id"]]
        assert e.start_node == rt["start"]["node"]
        assert e.available_from == hhmm(rt["available_from"])

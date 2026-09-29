import pytest

NEW = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3", "district": "Царицыно",
       "type": "Нет линка", "skill": "local", "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}


@pytest.fixture
def planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    client.put(f"/api/sessions/{sid}/clock", json={"time": "12:00"})
    return sid


def _status(client, sid):
    return client.get(f"/api/sessions/{sid}").json()["status"]


def test_base_plan_is_accepted_right_away(client, planned):
    assert client.get(f"/api/sessions/{planned}/plan").json()["plan"]["accepted"] is True
    assert _status(client, planned) == "planned"


def test_replan_is_a_draft_until_accepted(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    draft = client.post(f"/api/sessions/{planned}/replan").json()
    assert draft["accepted"] is False
    assert _status(client, planned) == "draft"
    r = client.post(f"/api/sessions/{planned}/plan/accept").json()
    assert r["plan_id"] == draft["plan_id"]
    assert "E01" in r["affected"]
    assert _status(client, planned) == "planned"
    assert client.post(f"/api/sessions/{planned}/plan/accept").status_code == 409


def test_rollback_restores_the_previous_plan_and_the_queue(client, planned):
    base = client.get(f"/api/sessions/{planned}").json()["plan_id"]
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{planned}/replan")
    client.post(f"/api/sessions/{planned}/requests", json=NEW)                  # пришло уже после черновика
    s = client.post(f"/api/sessions/{planned}/plan/rollback").json()
    assert s["plan_id"] == base
    assert s["status"] == "dirty"
    assert [e["type"] for e in s["pending_events"]] == ["engineer_unavailable", "new_request"]
    again = client.post(f"/api/sessions/{planned}/replan").json()                 # оба события снова учитываются
    assert {e["type"] for e in again["events"]} == {"engineer_unavailable", "new_request"}


def test_accepted_plan_cannot_be_rolled_back(client, planned):
    assert client.post(f"/api/sessions/{planned}/plan/rollback").status_code == 409


def test_full_mode_reaches_the_solver(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    assert client.post(f"/api/sessions/{planned}/replan", json={"mode": "full"}).json()["stability"] == "full"


def test_rebuild_is_refused_over_a_draft(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{planned}/replan")
    r = client.post(f"/api/sessions/{planned}/plan")
    assert r.status_code == 409
    assert "откатите" in r.json()["detail"]


def test_replan_over_a_draft_replaces_it(client, planned):
    """draft1 -> новое событие -> replan: второй черновик не наращивает цепочку, а заменяет
    первый, считая от базового плана и объединяя события обоих."""
    base = client.get(f"/api/sessions/{planned}").json()["plan_id"]
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    draft1 = client.post(f"/api/sessions/{planned}/replan").json()
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    draft2 = client.post(f"/api/sessions/{planned}/replan").json()
    assert draft2["plan_id"] != draft1["plan_id"]
    assert draft2["replan_of"] == base
    assert {e["type"] for e in draft2["events"]} == {"engineer_unavailable", "new_request"}
    r = client.post(f"/api/sessions/{planned}/plan/accept").json()
    assert r["plan_id"] == draft2["plan_id"]
    assert "E01" in r["affected"], "приняли черновик, который заменил тот, где E01 стал недоступен"
    h = client.get(f"/api/sessions/{planned}/history").json()
    assert [x["plan_id"] for x in h] == [base, draft2["plan_id"]], "черновик1 не должен остаться в истории"
    assert [x["kind"] for x in h] == ["base", "replan"]


def test_rollback_after_replan_over_a_draft_restores_both_events(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{planned}/replan")
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    client.post(f"/api/sessions/{planned}/replan")
    s = client.post(f"/api/sessions/{planned}/plan/rollback").json()
    assert {e["type"] for e in s["pending_events"]} == {"engineer_unavailable", "new_request"}


def test_view_carries_the_previous_routes(client, planned):
    assert client.get(f"/api/sessions/{planned}/plan").json()["previous"] is None
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    old = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    client.post(f"/api/sessions/{planned}/replan")
    prev = client.get(f"/api/sessions/{planned}/plan").json()["previous"]
    assert prev["plan_id"] == old["plan_id"]
    assert prev["routes"] == old["routes"]
    assert prev["metrics"] == old["metrics"]
    assert prev["replan_of"] is None and prev["risk"]["tol"]
    assert prev["assignments"] == old["assignments"] and prev["unassigned"] == old["unassigned"]


def test_history_runs_from_base_to_current(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{planned}/replan")
    h = client.get(f"/api/sessions/{planned}/history").json()
    assert [x["kind"] for x in h] == ["base", "replan"]
    assert h[0]["at"] is None and h[1]["at"] == "12:00"
    assert h[0]["changes"] is None and h[1]["changes"] > 0
    assert h[1]["events"][0]["type"] == "engineer_unavailable"
    assert [x["accepted"] for x in h] == [True, False]

import json
from pathlib import Path

import pytest

from planner.engines import solve
from planner.model import Problem, fmt, hhmm
from planner.plan import build_plan
from planner.replan import replan
from planner.routing import simulate

SCENARIO = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "normal.json"


@pytest.fixture
def ds():
    return json.loads(SCENARIO.read_text(encoding="utf-8"))


def _overlaps(stops, b, e):
    return [s for s in stops if s.arrive - s.leg_min < e and s.finish > b]


def test_simulate_moves_work_past_the_break(ds):
    p = Problem.from_dataset(ds)
    routes, _ = solve(p, "greedy", time_limit=3)
    # второй заявке маршрута хватает запаса по окну и смене, чтобы сдвинуться на 45 минут
    k, route, stops = next((k, v[:2], st) for k, v in routes.items() if len(v) >= 2
                           for st in [simulate(p, p.engineers[k], v[:2])[0]]
                           if p.requests[v[1]].tw_end - st[1].start >= 60
                           and p.engineers[k].shift_end - st[1].finish >= 60)
    e = p.engineers[k]
    b = stops[1].start
    e.breaks = [(b, b + 45)]
    moved, fail = simulate(p, e, route)
    assert fail is None
    assert not _overlaps(moved, b, b + 45)
    assert moved[0] == stops[0]
    assert moved[1].arrive - moved[1].leg_min == b + 45


def test_no_breaks_means_the_same_schedule(ds):
    p = Problem.from_dataset(ds)
    routes, _ = solve(p, "greedy", time_limit=3)
    k = next(k for k, v in routes.items() if v)
    before = simulate(p, p.engineers[k], routes[k])
    p.engineers[k].breaks = []
    assert simulate(p, p.engineers[k], routes[k]) == before


@pytest.mark.parametrize("engine", ["greedy", "ortools"])
def test_engines_respect_a_break(ds, engine):
    p = Problem.from_dataset(ds)
    p.engineers["E01"].breaks = [(13 * 60, 14 * 60)]
    routes, unassigned = solve(p, engine, time_limit=3)
    stops, fail = simulate(p, p.engineers["E01"], routes["E01"])
    assert fail is None
    assert not _overlaps(stops, 13 * 60, 14 * 60)
    plan = build_plan(p, p, routes, unassigned, engine, breaks={"E01": [(13 * 60, 14 * 60)]})
    rt = next(r for r in plan["routes"] if r["engineer_id"] == "E01")
    assert rt["breaks"] == [{"start": "13:00", "end": "14:00"}]


def test_replan_applies_a_break_event_and_keeps_it(ds):
    p = Problem.from_dataset(ds)
    routes, unassigned = solve(p, "greedy", time_limit=3)
    base = build_plan(p, p, routes, unassigned, "greedy")
    ev = {"id": "EV1", "type": "engineer_break", "time": "14:00", "until": "15:00", "engineer_id": "E01"}
    first = replan(ds, base, [ev], "greedy", now=12 * 60, time_limit=3)
    rt = next(r for r in first["routes"] if r["engineer_id"] == "E01")
    assert rt["breaks"] == [{"start": "14:00", "end": "15:00"}]
    busy = [s for s in rt["stops"] if not s["locked"]]
    assert all(hhmm(s["finish"]) <= 14 * 60 or hhmm(s["arrive"]) - s["leg_min"] >= 15 * 60 for s in busy)
    second = replan(ds, first, [], "greedy", now=12 * 60 + 30, time_limit=3)
    assert next(r for r in second["routes"] if r["engineer_id"] == "E01")["breaks"] == [{"start": "14:00", "end": "15:00"}]


def test_break_is_queued_through_the_api(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    client.put(f"/api/sessions/{sid}/clock", json={"time": "12:00"})
    bad = client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={"mode": "break", "time": "14:00", "until": "14:00"})
    assert bad.status_code == 422
    assert "перерыв должен заканчиваться позже начала" in bad.text
    pre = client.post(f"/api/sessions/{sid}/preview/unavailable/E01", json={"mode": "break", "time": "14:00", "until": "15:00"}).json()
    assert pre["leave"] == "14:00"
    client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={"mode": "break", "time": "14:00", "until": "15:00"})
    ev = client.get(f"/api/sessions/{sid}").json()["pending_events"][0]
    assert (ev["type"], ev["time"], ev["until"]) == ("engineer_break", "14:00", "15:00")
    plan = client.post(f"/api/sessions/{sid}/replan").json()
    rt = next(r for r in plan["routes"] if r["engineer_id"] == "E01")
    assert rt["breaks"] == [{"start": "14:00", "end": "15:00"}]
    assert "unavailable_from" not in rt, "перерыв — не уход"


def test_break_in_the_base_plan_is_honoured(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={"mode": "break", "time": "13:00", "until": "14:00"})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    rt = next(r for r in plan["routes"] if r["engineer_id"] == "E01")
    assert rt["breaks"] == [{"start": "13:00", "end": "14:00"}]
    assert "unavailable_from" not in rt
    assert all(hhmm(s["finish"]) <= 13 * 60 or hhmm(s["arrive"]) - s["leg_min"] >= 14 * 60 for s in rt["stops"])
    assert plan["risk"] is not None


def test_break_before_the_clock_is_refused(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    client.put(f"/api/sessions/{sid}/clock", json={"time": "12:00"})
    r = client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={"mode": "break", "time": "11:00", "until": "13:00"})
    assert r.status_code == 409
    assert "начало перерыва раньше часов" in r.text


def _later_stop(client, sid, fits):
    """План, часы 10:00 и незамороженная остановка, выезд к которой не раньше 10:30, по условию fits."""
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    client.put(f"/api/sessions/{sid}/clock", json={"time": "10:00"})
    return next((rt["engineer_id"], s) for rt in plan["routes"] for s in rt["stops"]
                if hhmm(s["arrive"]) - s["leg_min"] >= 10 * 60 + 30 and fits(s))


def _break_before(s, until):
    """Перерыв с момента выезда к остановке s: предыдущие остановки он не задевает."""
    return {"mode": "break", "time": fmt(hhmm(s["arrive"]) - s["leg_min"]), "until": fmt(until)}


def test_break_that_only_shifts_a_stop_does_not_release_it(client, sid):
    k, s = _later_stop(client, sid, lambda s: s["slack_min"] >= 40)
    body = _break_before(s, hhmm(s["arrive"]) - s["leg_min"] + 10)
    pre = client.post(f"/api/sessions/{sid}/preview/unavailable/{k}", json=body).json()
    assert s["request_id"] not in [r["request_id"] for r in pre["released"]]


def test_break_past_the_window_end_releases_the_stop(client, sid):
    k, s = _later_stop(client, sid, lambda s: hhmm(s["start"]) + s["slack_min"] < 23 * 60)
    body = _break_before(s, hhmm(s["start"]) + s["slack_min"] + 1)       # конец окна + 1
    pre = client.post(f"/api/sessions/{sid}/preview/unavailable/{k}", json=body).json()
    assert s["request_id"] in [r["request_id"] for r in pre["released"]]


def test_impact_counts_requests_released_by_a_break(client, sid):
    k, s = _later_stop(client, sid, lambda s: hhmm(s["start"]) + s["slack_min"] < 23 * 60)
    body = _break_before(s, hhmm(s["start"]) + s["slack_min"] + 1)
    assert client.post(f"/api/sessions/{sid}/engineers/{k}/unavailable", json=body).status_code == 200
    assert s["request_id"] in client.get(f"/api/sessions/{sid}/impact").json()["orphaned"]


def test_a_past_break_is_remembered(ds):
    p = Problem.from_dataset(ds)
    routes, unassigned = solve(p, "greedy", time_limit=3)
    base = build_plan(p, p, routes, unassigned, "greedy")
    ev = {"id": "EV1", "type": "engineer_break", "time": "12:00", "until": "13:00", "engineer_id": "E01"}
    first = replan(ds, base, [ev], "greedy", now=11 * 60, time_limit=3)
    later = replan(ds, first, [], "greedy", now=14 * 60, time_limit=3)
    rt = next(r for r in later["routes"] if r["engineer_id"] == "E01")
    assert rt["breaks"] == [{"start": "12:00", "end": "13:00"}]
    assert all(hhmm(s["finish"]) <= 12 * 60 or hhmm(s["arrive"]) - s["leg_min"] >= 13 * 60 for s in rt["stops"])

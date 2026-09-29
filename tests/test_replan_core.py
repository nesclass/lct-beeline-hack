"""Ядро перепланирования: уход в будущем, закрепление заявки, снимок."""
import json
from pathlib import Path

import pytest

from planner.compat import compat
from planner.engines import solve
from planner.explain import probe
from planner.model import Problem, hhmm
from planner.plan import build_plan
from planner.replan import replan, snapshot

SCENARIO = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "normal.json"


@pytest.fixture
def ds():
    return json.loads(SCENARIO.read_text(encoding="utf-8"))


@pytest.fixture
def base(ds):
    p = Problem.from_dataset(ds)
    routes, unassigned = solve(p, "greedy", time_limit=5)
    return build_plan(p, p, routes, unassigned, "greedy")


def _busy_across(plan, t):
    """Инженер, у которого есть заявки и до, и после t."""
    for rt in plan["routes"]:
        starts = [hhmm(s["start"]) for s in rt["stops"]]
        if any(x < t for x in starts) and any(x >= t + 60 for x in starts):
            return rt["engineer_id"]
    raise AssertionError("в сценарии нет инженера с заявками по обе стороны от t")


def test_future_leave_keeps_the_engineer_until_then(ds, base):
    k = _busy_across(base, 14 * 60)
    ev = {"id": "EV1", "type": "engineer_unavailable", "time": "14:00", "engineer_id": k, "finish_current": True}
    new = replan(ds, base, [ev], "greedy", now=12 * 60, time_limit=5)
    rt = next(r for r in new["routes"] if r["engineer_id"] == k)
    assert rt["unavailable_from"] == "14:00"
    assert rt["stops"], "до ухода инженер должен работать"
    assert all(hhmm(s["finish"]) <= 14 * 60 for s in rt["stops"] if not s["locked"])


def _departed_stop(base):
    """Инженер и заявка, к которой он уже выехал (выезд = прибытие − дорога), начинающаяся
    после 10:00 — застолбленная («замороженная») в снимке, но ещё не начатая."""
    for rt in base["routes"]:
        for s in rt["stops"]:
            if hhmm(s["start"]) > 10 * 60 and s["leg_min"] > 0:
                return rt["engineer_id"], s
    raise AssertionError("в сценарии нет инженера, уже выехавшего к заявке после 10:00")


@pytest.mark.parametrize("engine", ["greedy", "ortools"])
def test_leave_before_the_frozen_job_ends_does_not_crash(ds, base, engine):
    k, s = _departed_stop(base)
    t = hhmm(s["arrive"]) - s["leg_min"]           # уже выехал к заявке — она застолблена
    leave = s["start"]                             # уходит раньше конца этой заявки
    ev = {"id": "EV1", "type": "engineer_unavailable", "time": leave, "engineer_id": k, "finish_current": True}
    new = replan(ds, base, [ev], engine, now=t, time_limit=5)
    rt = next(r for r in new["routes"] if r["engineer_id"] == k)
    assert rt["unavailable_from"] == leave
    assert rt["stops"], "замороженная заявка должна остаться в плане"
    assert all(x["locked"] for x in rt["stops"]), "после ухода раньше конца замороженной новых заявок у него нет"


def test_leave_in_the_past_removes_the_rest_of_the_day(ds, base):
    k = _busy_across(base, 14 * 60)
    ev = {"id": "EV1", "type": "engineer_unavailable", "time": "12:00", "engineer_id": k, "finish_current": True}
    new = replan(ds, base, [ev], "greedy", now=13 * 60, time_limit=5)
    rt = next(r for r in new["routes"] if r["engineer_id"] == k)
    assert all(s["locked"] for s in rt["stops"])


def test_second_replan_after_the_leave_time_takes_him_off(ds, base):
    k = _busy_across(base, 14 * 60)
    ev = {"id": "EV1", "type": "engineer_unavailable", "time": "14:00", "engineer_id": k, "finish_current": True}
    first = replan(ds, base, [ev], "greedy", now=12 * 60, time_limit=5)
    second = replan(ds, first, [], "greedy", now=15 * 60, time_limit=5)
    rt = next(r for r in second["routes"] if r["engineer_id"] == k)
    assert rt["unavailable_from"] == "14:00"
    assert all(hhmm(s["start"]) < 14 * 60 for s in rt["stops"])
    assert all(s["locked"] for s in rt["stops"]), "после ухода незамороженных заявок у него нет"


def _movable(ds, base, now):
    """Незамороженная заявка и другой инженер, которому её можно отдать."""
    snap = snapshot(ds, base, [], now=now)
    for rid, owner in snap.p.prev_owner.items():
        for k in snap.p.engineers:
            if k != owner and probe(snap.p, snap.initial, rid, k)["feasible"]:
                return rid, owner, k
    raise AssertionError("нечего переназначить")


def test_moved_request_lands_on_the_chosen_engineer_and_stays(ds, base):
    rid, owner, k = _movable(ds, base, 10 * 60)
    mv = {"id": "EV1", "type": "move_request", "time": "10:00", "request_id": rid, "engineer_id": k}
    first = replan(ds, base, [mv], "greedy", now=10 * 60, time_limit=5)
    assert first["assignments"][rid]["engineer_id"] == k
    assert first["assignments"][rid]["manual"] is True
    assert first["diff"]["requests"][rid]["status"] == "moved"
    second = replan(ds, first, [], "greedy", now=10 * 60 + 5, time_limit=5)
    assert second["assignments"][rid]["engineer_id"] == k, "закрепление потерялось на следующем перепланировании"


def test_pin_makes_everyone_else_incompatible(ds):
    p = Problem.from_dataset(ds)
    r = p.requests["R001"]
    ok = [e for e in p.engineers.values() if compat(p, r, e) is None]
    assert len(ok) >= 2
    p.pinned = {"R001": ok[0].id}
    assert compat(p, r, ok[0]) is None
    assert compat(p, r, ok[1]) == "PINNED"


def test_pinned_request_that_no_longer_fits_explains_why(ds, base):
    rid, owner, k = _movable(ds, base, 10 * 60)
    snap = snapshot(ds, base, [{"id": "EV1", "type": "move_request", "time": "10:00", "request_id": rid, "engineer_id": k}],
                    now=10 * 60)
    assert snap.p.pinned == {rid: k}
    snap.p.engineers[k].shift_end = snap.p.engineers[k].available_from      # места у него больше нет
    routes, unassigned = solve(snap.p, "greedy", time_limit=2, initial=snap.initial)
    assert rid in unassigned
    plan = build_plan(snap.p_full, snap.p, routes, unassigned, "greedy", locked=snap.locked, now=snap.T)
    assert "закреплена за" in plan["assignments"][rid]["text"]


def test_snapshot_pool_is_what_replan_solves(ds, base):
    snap = snapshot(ds, base, [], now=13 * 60)
    started = {s["request_id"] for rt in base["routes"] for s in rt["stops"] if hhmm(s["start"]) <= 13 * 60}
    assert not started & set(snap.p.requests)
    assert set(snap.p.requests) | {s["request_id"] for v in snap.locked.values() for s in v} >= set(base["assignments"])


def test_assigned_reason_carries_the_detour(base):
    a = next(a for a in base["assignments"].values() if a["engineer_id"] and not a.get("locked"))
    assert isinstance(a["reason"]["delta_km"], float)
    assert a["reason"]["delta_km"] >= 0


def test_pin_that_did_not_fit_survives_to_the_next_replan(ds, base, monkeypatch):
    import planner.replan as rp
    rid, owner, k = _movable(ds, base, 10 * 60)
    real = rp.snapshot

    def squeezed(*a, **kw):                              # в первом перепланировании места у него нет
        snap = real(*a, **kw)
        snap.p.engineers[k].shift_end = snap.p.engineers[k].available_from
        return snap

    monkeypatch.setattr(rp, "snapshot", squeezed)
    mv = {"id": "EV1", "type": "move_request", "time": "10:00", "request_id": rid, "engineer_id": k}
    first = replan(ds, base, [mv], "greedy", now=10 * 60, time_limit=5)
    assert first["assignments"][rid]["engineer_id"] is None
    assert first["pins"] == {rid: k}
    monkeypatch.setattr(rp, "snapshot", real)
    assert snapshot(ds, first, [], now=10 * 60 + 5).p.pinned == {rid: k}
    second = replan(ds, first, [], "greedy", now=10 * 60 + 5, time_limit=5)
    assert second["assignments"][rid]["engineer_id"] == k, "закрепление потерялось, пока заявка не помещалась"
    assert second["assignments"][rid]["manual"] is True


def test_future_leave_is_not_removed_until_it_comes(ds, base):
    k = _busy_across(base, 14 * 60)
    ev = {"id": "EV1", "type": "engineer_unavailable", "time": "14:00", "engineer_id": k, "finish_current": True}
    first = replan(ds, base, [ev], "greedy", now=12 * 60, time_limit=5)
    assert first["diff"]["engineers"][k]["status"] != "removed"
    second = replan(ds, first, [], "greedy", now=15 * 60, time_limit=5)
    assert second["diff"]["engineers"][k]["status"] == "removed"
    third = replan(ds, second, [], "greedy", now=16 * 60, time_limit=5)
    assert third["diff"]["engineers"][k]["status"] != "removed", "снят в разборе только один раз"


def test_pinned_text_ends_with_one_full_stop(ds):
    from planner.explain import text_unassigned, why_unassigned
    p = Problem.from_dataset(ds)
    k = next(iter(p.engineers))
    p.pinned = {"R001": k}
    p.engineers[k].shift_end = p.engineers[k].available_from
    routes = {e: [] for e in p.engineers}
    text = text_unassigned(p, "R001", why_unassigned(p, routes, "R001"))
    assert "закреплена за" in text
    assert not text.endswith(". ."), text


def _base_with_leave(ds, k, t):
    """Базовый план, в котором уход k в t объявлен до расчёта: смена обрезана, маршрут помечен."""
    p_full = Problem.from_dataset(ds)
    engs = [dict(e, shift_end=t) if e["id"] == k else e for e in ds["engineers"]
            if not (e["id"] == k and hhmm(t) <= hhmm(e["shift_start"]))]
    p = Problem.from_dataset({**ds, "engineers": engs})
    routes, unassigned = solve(p, "greedy", time_limit=5)
    return build_plan(p_full, p, routes, unassigned, "greedy", inactive={k: t})


def test_base_plan_leave_later_in_the_day_is_removed_when_it_comes(ds, base):
    """Уход в 14:00, объявленный до базового плана: до 14:00 инженер в работе, и снятым его
    показывает первое перепланирование, чьи часы дошли до ухода, — и только оно."""
    k = _busy_across(base, 14 * 60)
    b = _base_with_leave(ds, k, "14:00")
    before = replan(ds, b, [], "greedy", now=12 * 60, time_limit=5)
    assert before["diff"]["engineers"][k]["status"] != "removed"
    at = replan(ds, before, [], "greedy", now=14 * 60, time_limit=5)
    assert at["diff"]["engineers"][k]["status"] == "removed"
    direct = replan(ds, b, [], "greedy", now=15 * 60, time_limit=5)
    assert direct["diff"]["engineers"][k]["status"] == "removed"
    again = replan(ds, direct, [], "greedy", now=16 * 60, time_limit=5)
    assert again["diff"]["engineers"][k]["status"] != "removed"


def test_base_plan_leave_before_the_shift_is_off_from_the_start(ds, base):
    """Недоступный с начала смены снят уже в базовом плане — перепланирование не повторяет это."""
    k = base["routes"][0]["engineer_id"]
    start = next(e["shift_start"] for e in ds["engineers"] if e["id"] == k)
    b = _base_with_leave(ds, k, start)
    new = replan(ds, b, [], "greedy", now=12 * 60, time_limit=5)
    assert new["diff"]["engineers"][k]["status"] != "removed"

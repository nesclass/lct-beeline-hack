import json
from pathlib import Path

import pytest

from planner.engines import solve
from planner.model import Problem, fmt, hhmm
from planner.plan import build_plan
from planner.replan import replan

SCENARIO = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "normal.json"


@pytest.fixture
def ds():
    return json.loads(SCENARIO.read_text(encoding="utf-8"))


@pytest.fixture
def base(ds):
    p = Problem.from_dataset(ds)
    routes, unassigned = solve(p, "greedy", time_limit=5)
    return build_plan(p, p, routes, unassigned, "greedy")


NEW = {"id": "R900", "lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3",
       "district": "Царицыно", "type": "Нет линка", "skill": "local", "work_type": "local_repair",
       "duration_min": 30, "tw_start": "15:00", "tw_end": "17:00",
       "priority": "normal", "required_transport": None}


def test_request_created_after_the_plan_is_replanned(ds, base):
    ds["requests"].append(NEW)
    new = replan(ds, base, [], "greedy", now=13 * 60, time_limit=5)
    known = set(new["assignments"])
    assert "R900" in known, "новая заявка не попала в задачу перепланирования"


def test_it_is_actually_scheduled_when_there_is_room(ds, base):
    ds["requests"].append(NEW)
    new = replan(ds, base, [], "greedy", now=13 * 60, time_limit=5)
    assert new["assignments"]["R900"]["engineer_id"] is not None


def test_external_matrix_survives_into_the_reduced_problem(ds, base):
    ids = [e["id"] for e in ds["engineers"]] + [r["id"] for r in ds["requests"]]
    ds["matrix"] = {"ids": ids, "source": "osrm",
                    "km": {(a, b): 0.0 if a == b else 2.0 for a in ids for b in ids},
                    "min": {(a, b, m): 0 if a == b else 4
                            for a in ids for b in ids for m in ("car", "bike", "foot", "public")}}
    ds["config"]["travel"]["mode"] = "external"
    p = Problem.from_dataset(ds)
    routes, unassigned = solve(p, "greedy", time_limit=5)
    old = build_plan(p, p, routes, unassigned, "greedy")
    new = replan(ds, old, [], "greedy", now=13 * 60, time_limit=5)
    legs = [s["leg_min"] for rt in new["routes"] for s in rt["stops"] if not s["locked"] and s["seq"] > 1]
    assert legs, "нечего проверять: все остановки заморожены"
    assert set(legs) == {4}, f"перепланирование считало дорогу мимо матрицы: {sorted(set(legs))}"


def test_locked_stops_stay_put(ds, base):
    new = replan(ds, base, [], "greedy", now=13 * 60, time_limit=5)
    for rt in new["routes"]:
        for s in rt["stops"]:
            if s["locked"]:
                assert base["assignments"][s["request_id"]]["engineer_id"] == rt["engineer_id"]


def test_stop_the_engineer_already_drives_to_stays_locked(ds, base):
    """Выехал (прибытие − дорога ≤ T), но ещё не начал — остановка всё равно заморожена:
    разворачивать доступного инженера в пути прототип не пытается."""
    rt = next(rt for rt in base["routes"] if rt["stops"] and rt["stops"][0]["leg_min"] > 0)
    s = rt["stops"][0]
    T = hhmm(s["arrive"]) - s["leg_min"]
    assert T < hhmm(s["start"])
    new = replan(ds, base, [], "greedy", now=T, time_limit=5)
    got = next(r for r in new["routes"] if r["engineer_id"] == rt["engineer_id"])
    assert got["stops"][0]["request_id"] == s["request_id"]
    assert got["stops"][0]["locked"]


def test_engineer_who_drops_the_current_job_releases_it(ds, base):
    """finish_current=False: заявка, которую инженер делал в момент T, уходит обратно в пул."""
    rt, s = next((rt, s) for rt in base["routes"] for s in rt["stops"]
                 if hhmm(s["finish"]) - hhmm(s["start"]) >= 2)
    T = hhmm(s["start"]) + 1
    ev = {"type": "engineer_unavailable", "time": fmt(T), "engineer_id": rt["engineer_id"],
          "finish_current": False}
    new = replan(ds, base, [ev], "greedy", now=T, time_limit=5)
    got = next(r for r in new["routes"] if r["engineer_id"] == rt["engineer_id"])
    assert s["request_id"] not in {x["request_id"] for x in got["stops"]}
    assert new["assignments"][s["request_id"]]["engineer_id"] != rt["engineer_id"]


def _lose(ds, base, k, t):
    ev = {"type": "engineer_unavailable", "time": fmt(t), "engineer_id": k, "finish_current": True}
    return replan(ds, base, [ev], "greedy", now=t, time_limit=5)


def test_repeated_unavailability_keeps_the_earliest_time(ds, base):
    """Повторное объявление позже не сдвигает начало недоступности вперёд."""
    first = _lose(ds, base, "E01", 10 * 60)
    second = replan(ds, first, [{"type": "engineer_unavailable", "time": "14:00", "engineer_id": "E01",
                                 "finish_current": True}], "greedy", now=14 * 60, time_limit=5)
    rt = next(r for r in second["routes"] if r["engineer_id"] == "E01")
    assert rt["unavailable_from"] == "10:00"


def test_engineer_is_removed_only_once(ds, base):
    """«Снят с маршрута» — изменение; на следующем перепланировании он уже снят,
    и повторять это как новость — значит врать в разборе изменений."""
    first = _lose(ds, base, "E01", 10 * 60)
    assert first["diff"]["engineers"]["E01"]["status"] == "removed"
    second = replan(ds, first, [], "greedy", now=11 * 60, time_limit=5)
    assert second["diff"]["engineers"]["E01"]["status"] != "removed"

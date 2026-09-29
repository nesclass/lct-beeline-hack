import copy
import json
from pathlib import Path

import pytest

from planner.model import Problem

DATASET = Path(__file__).resolve().parent.parent / "data" / "synth" / "dataset.json"


@pytest.fixture
def ds():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def external_matrix(ds, minutes=7, km=3.0):
    """Матрица-константа по всем точкам датасета, кроме диагонали."""
    ids = [e["id"] for e in ds["engineers"]] + [r["id"] for r in ds["requests"]]
    return {"ids": ids, "source": "osrm",
            "km": {(a, b): 0.0 if a == b else km for a in ids for b in ids},
            "min": {(a, b, m): 0 if a == b else minutes
                    for a in ids for b in ids
                    for m in ("car", "bike", "foot", "public")}}


def test_external_minutes_win_over_formula(ds):
    ds["matrix"] = external_matrix(ds)
    ds["config"]["travel"]["mode"] = "external"
    p = Problem.from_dataset(ds)
    assert p.travel_raw("E01", "R001", "car") == 7


def test_external_kilometres_win_over_formula(ds):
    ds["matrix"] = external_matrix(ds)
    ds["config"]["travel"]["mode"] = "external"
    p = Problem.from_dataset(ds)
    assert p.km("E01", "R001") == 3.0


def test_without_matrix_formula_still_works(ds):
    p = Problem.from_dataset(ds)
    assert p.travel_raw("E01", "R001", "car") > 0


def test_request_added_after_the_matrix_is_measured_anyway(ds):
    """Срочная заявка приходит событием: её координат в прогретой матрице нет."""
    ds["matrix"] = external_matrix(ds)
    ds["config"]["travel"]["mode"] = "external"
    p = Problem.from_dataset(ds)
    ev = next(e for e in ds["events"] if e["type"] == "urgent_request")
    p.requests[ev["request"]["id"]] = p.new_request(ev["request"])
    p._pos[ev["request"]["id"]] = (ev["request"]["lat"], ev["request"]["lon"])
    assert p.travel_raw("E01", ev["request"]["id"], "car") > 0
    assert p.km("E01", ev["request"]["id"]) > 0


def test_normative_mode_is_untouched(ds):
    ds["config"]["travel"]["mode"] = "normative"
    p = Problem.from_dataset(ds)
    assert p.travel_raw("E01", "R001", "car") == 20


def test_verify_checks_the_plan_against_the_same_matrix(ds):
    """План, посчитанный на внешней матрице, независимая проверка обязана проверять по ней же.
    Если verify собьётся на формулу, плечи разойдутся и корректный план объявят неверным."""
    from planner.engines import solve
    from planner.plan import build_plan
    from planner.verify import verify

    ds["matrix"] = external_matrix(ds)
    ds["config"]["travel"]["mode"] = "external"
    p = Problem.from_dataset(ds)
    routes, unassigned = solve(p, "greedy", time_limit=5)
    plan = build_plan(p, p, routes, unassigned, "greedy")
    assert verify(copy.deepcopy(ds), plan) == []

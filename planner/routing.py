"""Прокрутка маршрута по времени (T1–T4) и стоимость плана (целевая функция §1.4)."""
from __future__ import annotations

from dataclasses import dataclass

from .model import Engineer, Problem

Routes = dict[str, list[str]]   # engineer_id -> упорядоченные request_id


@dataclass
class Stop:
    request_id: str
    arrive: int
    start: int
    finish: int
    leg_km: float
    leg_min: int


@dataclass
class Fail:
    index: int            # позиция в маршруте, где сломалось
    request_id: str
    code: str             # WINDOW | SHIFT
    arrive: int           # когда бы приехали


def simulate(p: Problem, e: Engineer, route: list[str]) -> tuple[list[Stop], Fail | None]:
    """Едем от start_node с available_from; начало работ в окне, раньше — ждём.
    Перерыв (backups/docs/model.md §4.2) не пересекают ни дорога, ни работа: выезд переносится на его конец."""
    t, cur, stops = e.available_from, e.start_node, []
    for i, rid in enumerate(route):
        r = p.requests[rid]
        leg_min = p.travel(cur, rid, e.transport)
        depart = t
        while True:
            arrive = depart + leg_min
            start = max(arrive, r.tw_start)
            finish = start + p.service(r)
            hit = next(((b, en) for b, en in e.breaks if depart < en and finish > b), None)
            if hit is None:
                break
            depart = hit[1]
        if start > r.tw_end:
            return stops, Fail(i, rid, "WINDOW", arrive)
        if finish > e.shift_end:
            return stops, Fail(i, rid, "SHIFT", arrive)
        stops.append(Stop(rid, arrive, start, finish, p.km(cur, rid), leg_min))
        t, cur = finish, rid
    return stops, None


def feasible(p: Problem, e: Engineer, route: list[str]) -> bool:
    return simulate(p, e, route)[1] is None


def route_km(p: Problem, e: Engineer, route: list[str]) -> float:
    km, cur = 0.0, e.start_node
    for rid in route:
        km += p.km(cur, rid)
        cur = rid
    return km


def route_cost(p: Problem, e: Engineer, route: list[str]) -> float:
    """км + F·[маршрут не пуст] + G·(число заявок, ушедших от прежнего владельца)."""
    if not route:
        return 0.0
    w = p.weights
    moved = sum(1 for rid in route if p.prev_owner.get(rid, e.id) != e.id)
    return route_km(p, e, route) + w["F"] + w["G"] * moved


def total_cost(p: Problem, routes: Routes, unassigned: set[str]) -> float:
    c = sum(route_cost(p, p.engineers[k], v) for k, v in routes.items())
    c += p.weights["P"] * sum(p.weight(p.requests[i]) for i in unassigned)
    return c

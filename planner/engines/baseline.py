"""Baseline по ТЗ §2.3: заявки по порядку входа → первый по порядку инженер, у которого
заявка проходит совместимость и влезает в ХВОСТ текущего маршрута. Без оптимизации."""
from __future__ import annotations

from ..compat import compat
from ..model import Problem
from ..routing import Routes, feasible


def solve_baseline(p: Problem) -> tuple[Routes, set[str]]:
    routes: Routes = {k: [] for k in p.engineers}
    unassigned: set[str] = set()
    for r in p.requests.values():
        for e in p.engineers.values():
            if compat(p, r, e) is None and feasible(p, e, routes[e.id] + [r.id]):
                routes[e.id].append(r.id)
                break
        else:
            unassigned.add(r.id)
    return routes, unassigned

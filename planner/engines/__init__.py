"""Движки. Все принимают Problem и возвращают (routes, unassigned)."""
from __future__ import annotations

from ..model import Engineer, Problem
from ..routing import Routes, simulate


def solve(p: Problem, engine: str, time_limit: float = 10.0, **kw) -> tuple[Routes, set[str]]:
    routes, unassigned = _solve(p, engine, time_limit, **kw)
    if any(e.breaks for e in p.engineers.values()):
        routes, unassigned = _repair(p, routes, unassigned)
    return routes, unassigned


def drop_until_feasible(p: Problem, e: Engineer, route: list[str]) -> tuple[list[str], list[str]]:
    """Снимать сорвавшуюся остановку, пока прокрутка не примет маршрут: (оставшиеся, снятые).
    Этим же правилом предпросмотр перерыва решает, какие заявки освободятся."""
    kept, dropped = list(route), []
    while kept:
        _, fail = simulate(p, e, kept)
        if fail is None:
            break
        dropped.append(kept.pop(fail.index))
    return kept, dropped


def _repair(p: Problem, routes: Routes, unassigned: set[str]) -> tuple[Routes, set[str]]:
    """Маршрут, который прокрутка с перерывами не принимает, теряет сорвавшиеся остановки;
    один проход быстрого движка пытается вернуть их на свободные места."""
    from .greedy import solve_greedy
    broken = False
    for k in routes:
        routes[k], dropped = drop_until_feasible(p, p.engineers[k], routes[k])
        unassigned.update(dropped)
        broken = broken or bool(dropped)
    if not broken:
        return routes, unassigned
    return solve_greedy(p, time_limit=1.0, initial=routes)


def _solve(p: Problem, engine: str, time_limit: float, **kw) -> tuple[Routes, set[str]]:
    if engine == "baseline":
        from .baseline import solve_baseline
        kw.pop("initial", None)
        return solve_baseline(p)
    if engine == "greedy":
        from .greedy import solve_greedy
        return solve_greedy(p, time_limit=time_limit, **kw)
    if engine == "ortools":
        from .ortools_engine import solve_ortools
        return solve_ortools(p, time_limit=time_limit, **kw)
    raise ValueError(f"unknown engine {engine}")

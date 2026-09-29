"""Жадная вставка + local search. Прозрачный движок и страховка для OR-Tools.

Вставка: срочные → самые «зажатые» (мало кандидатов) → узкое окно; лучшая позиция по
Δ = Δкм + F·[маршрут пуст] + G·[k ≠ прежний владелец].
Local search: relocate, swap, 2-opt, empty-route, повторная вставка неназначенных.
"""
from __future__ import annotations

import time

from ..compat import candidates, compat
from ..model import Problem
from ..routing import Routes, feasible, route_cost

EPS = 1e-6


def best_insertion(p: Problem, routes: Routes, rid: str, only: list[str] | None = None):
    """(delta, engineer_id, position) или None. Δ считается относительно текущей стоимости маршрута."""
    r = p.requests[rid]
    best = None
    cands = candidates(p, r)
    for k in (cands if only is None else [k for k in cands if k in only]):
        e, route = p.engineers[k], routes[k]
        base = route_cost(p, e, route)
        for pos in range(len(route) + 1):
            cand = route[:pos] + [rid] + route[pos:]
            if not feasible(p, e, cand):
                continue
            d = route_cost(p, e, cand) - base
            if best is None or d < best[0] - EPS:
                best = (d, k, pos)
    return best


def _eject_insert(p: Problem, routes: Routes, rid: str):
    """(k, pos, x, k2, pos2): вставить rid в маршрут k на pos вместо x; x переезжает в k2/pos2,
    либо (k2 = None) вытесняется в неназначенные — только если rid весит больше x (срочная > обычная, L5).
    Выбираем вариант с минимальным суммарным Δ."""
    r = p.requests[rid]
    P = p.weights["P"]
    best = None
    for k in candidates(p, r):
        e, route = p.engineers[k], routes[k]
        for x in route:
            without = [y for y in route if y != x]
            for pos in range(len(without) + 1):
                cand = without[:pos] + [rid] + without[pos:]
                if not feasible(p, e, cand):
                    continue
                d_route = route_cost(p, e, cand) - route_cost(p, e, route)
                trial = dict(routes)
                trial[k] = cand
                b = best_insertion(p, trial, x)
                if b is not None:
                    d, k2, pos2 = d_route + b[0], b[1], b[2]
                elif p.weight(r) > p.weight(p.requests[x]):
                    d, k2, pos2 = d_route + P * p.weight(p.requests[x]), None, None
                else:
                    continue
                if best is None or d < best[0]:
                    best = (d, k, pos, x, k2, pos2)
    return best[1:] if best else None


def _insert_all(p: Problem, routes: Routes, pool: list[str], unassigned: set[str]) -> None:
    for rid in pool:
        b = best_insertion(p, routes, rid)
        if b is None:
            unassigned.add(rid)
        else:
            routes[b[1]].insert(b[2], rid)


def solve_greedy(p: Problem, time_limit: float = 10.0, local_search: bool = True,
                 initial: Routes | None = None) -> tuple[Routes, set[str]]:
    """initial — стартовые маршруты (перепланирование: старый план). Что в них недопустимо
    при новых стартах/событиях — выбрасывается в пул и вставляется заново."""
    routes: Routes = {k: [] for k in p.engineers}
    placed: set[str] = set()
    if initial:
        for k, route in initial.items():
            if k not in p.engineers:
                continue
            e, kept = p.engineers[k], []
            for rid in route:
                if rid in p.requests and compat(p, p.requests[rid], e) is None and feasible(p, e, kept + [rid]):
                    kept.append(rid)
            routes[k], placed = kept, placed | set(kept)
    unassigned: set[str] = set()
    order = sorted((r for r in p.requests.values() if r.id not in placed),
                   key=lambda r: (r.priority != "urgent", len(candidates(p, r)), r.tw_end - r.tw_start))
    _insert_all(p, routes, [r.id for r in order], unassigned)
    if local_search:
        _local_search(p, routes, unassigned, time.time() + time_limit)
    return routes, unassigned


def _local_search(p: Problem, routes: Routes, unassigned: set[str], deadline: float) -> None:
    cost = {k: route_cost(p, p.engineers[k], v) for k, v in routes.items()}
    improved = True
    while improved and time.time() < deadline:
        improved = False
        # 0. неназначенные: любая вставка — выигрыш (P огромен); если напрямую не лезет —
        #    ejection глубины 1: выкинуть одну заявку из маршрута, вставить нашу, выкинутую — в лучшее место
        for rid in sorted(unassigned):
            b = best_insertion(p, routes, rid)
            if b is None:
                b = _eject_insert(p, routes, rid)
                if b is None:
                    continue
                k, pos, x, k2, pos2 = b
                routes[k].remove(x)
                routes[k].insert(pos, rid)
                cost[k] = route_cost(p, p.engineers[k], routes[k])
                if k2 is None:
                    unassigned.add(x)                       # вытеснена
                else:
                    routes[k2].insert(pos2, x)
                    cost[k2] = route_cost(p, p.engineers[k2], routes[k2])
            else:
                routes[b[1]].insert(b[2], rid)
                cost[b[1]] = route_cost(p, p.engineers[b[1]], routes[b[1]])
            unassigned.discard(rid)
            improved = True
        # 1. relocate: перенос одной заявки в лучшее место любого маршрута
        for k in list(routes):
            for rid in list(routes[k]):
                src = [x for x in routes[k] if x != rid]
                src_cost = route_cost(p, p.engineers[k], src)
                trial = dict(routes)
                trial[k] = src
                b = best_insertion(p, trial, rid)
                if b is None:
                    continue
                d, k2, pos = b
                gain = (cost[k] - src_cost) - d if k2 != k else cost[k] - (src_cost + d)
                if gain > EPS:
                    routes[k] = src
                    routes[k2].insert(pos, rid)
                    cost[k] = route_cost(p, p.engineers[k], routes[k])
                    cost[k2] = route_cost(p, p.engineers[k2], routes[k2])
                    improved = True
        # 2. swap между маршрутами
        keys = [k for k in routes if routes[k]]
        for a_i, ka in enumerate(keys):
            for kb in keys[a_i + 1:]:
                ea, eb = p.engineers[ka], p.engineers[kb]
                done = False
                for i, ra in enumerate(routes[ka]):
                    for j, rb in enumerate(routes[kb]):
                        if ka not in candidates(p, p.requests[rb]) or kb not in candidates(p, p.requests[ra]):
                            continue
                        na = routes[ka][:i] + [rb] + routes[ka][i + 1:]
                        nb = routes[kb][:j] + [ra] + routes[kb][j + 1:]
                        if not (feasible(p, ea, na) and feasible(p, eb, nb)):
                            continue
                        ca, cb = route_cost(p, ea, na), route_cost(p, eb, nb)
                        if cost[ka] + cost[kb] - ca - cb > EPS:
                            routes[ka], routes[kb], cost[ka], cost[kb] = na, nb, ca, cb
                            improved = done = True
                            break
                    if done:
                        break
        # 3. 2-opt внутри маршрута
        for k, route in routes.items():
            e = p.engineers[k]
            n = len(route)
            for i in range(n - 1):
                for j in range(i + 2, n + 1):
                    cand = route[:i] + route[i:j][::-1] + route[j:]
                    if feasible(p, e, cand):
                        c = route_cost(p, e, cand)
                        if cost[k] - c > EPS:
                            routes[k], cost[k] = cand, c
                            improved = True
                            break
                if improved:
                    break
        # 4. empty-route: попытка расформировать самый короткий маршрут (работа члена F)
        nonempty = sorted((k for k in routes if routes[k]), key=lambda k: len(routes[k]))
        for k in nonempty[:3]:
            trial = {kk: list(v) for kk, v in routes.items()}
            trial[k] = []
            ok, delta = True, -cost[k]
            for rid in routes[k]:
                b = best_insertion(p, trial, rid, only=[kk for kk in trial if kk != k])
                if b is None:
                    ok = False
                    break
                trial[b[1]].insert(b[2], rid)
                delta += b[0]
            if ok and delta < -EPS:
                routes.update(trial)
                cost = {kk: route_cost(p, p.engineers[kk], v) for kk, v in routes.items()}
                improved = True
                break

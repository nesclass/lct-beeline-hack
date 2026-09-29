"""OR-Tools Routing: та же модель (backups/docs/model.md §1.7, таблица соответствия API).

Узлы: заявки [0, n), стартовые точки инженеров [n, n+m), фиктивный конец n+m.
Стоимости в метрах (км·1000), время в минутах. Начальное решение — из greedy.
"""
from __future__ import annotations

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from ..compat import candidates
from ..model import Problem
from ..routing import Routes
from .greedy import solve_greedy

SCALE = 1000


def solve_ortools(p: Problem, time_limit: float = 10.0, warm_start: bool = True,
                  initial: Routes | None = None) -> tuple[Routes, set[str]]:
    reqs = [r for r in p.requests.values() if candidates(p, r)]     # без кандидатов — сразу мимо
    unassigned = {r.id for r in p.requests.values() if not candidates(p, r)}
    engs = list(p.engineers.values())
    n, m = len(reqs), len(engs)
    if n == 0 or m == 0:
        return {e.id: [] for e in engs}, set(p.requests)
    END = n + m
    node_id = [r.id for r in reqs] + [e.start_node for e in engs]   # старт может быть виртуальным (L2)
    service = [p.service(r) for r in reqs] + [0] * m
    w = p.weights

    manager = pywrapcp.RoutingIndexManager(n + m + 1, m, list(range(n, n + m)), [END] * m)
    routing = pywrapcp.RoutingModel(manager)

    time_cbs = []
    for v, e in enumerate(engs):
        def cost_cb(fi, ti, e=e):
            a, b = manager.IndexToNode(fi), manager.IndexToNode(ti)
            if a == END or b == END:
                return 0
            c = p.km(node_id[a], node_id[b]) * SCALE
            if b < n and p.prev_owner.get(node_id[b], e.id) != e.id:
                c += w["G"] * SCALE                                   # член (4): нестабильность
            return int(round(c))

        def time_cb(fi, ti, e=e):
            a, b = manager.IndexToNode(fi), manager.IndexToNode(ti)
            if a == END:
                return 0
            if b == END:
                return service[a]
            return service[a] + p.travel(node_id[a], node_id[b], e.transport)

        routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(cost_cb), v)
        time_cbs.append(routing.RegisterTransitCallback(time_cb))

    routing.AddDimensionWithVehicleTransits(time_cbs, 24 * 60, 48 * 60, False, "Time")
    tdim = routing.GetDimensionOrDie("Time")
    for i, r in enumerate(reqs):
        idx = manager.NodeToIndex(i)
        tdim.CumulVar(idx).SetRange(r.tw_start, r.tw_end)                       # (T3)
        routing.AddDisjunction([idx], int(w["P"] * p.weight(r) * SCALE))        # член (1)
        allowed = [v for v, e in enumerate(engs) if e.id in candidates(p, r)]
        if len(allowed) < m:
            routing.VehicleVar(idx).SetValues([-1] + allowed)                   # (A2); -1 = не назначена
    for v, e in enumerate(engs):
        tdim.CumulVar(routing.Start(v)).SetRange(e.available_from, e.shift_end)  # (T2)
        tdim.CumulVar(routing.End(v)).SetRange(0, e.shift_end)                  # (T4)
    visit = [service[i] for i in range(n)] + [0] * (m + 1)       # по узлам: заявки, старты, конец
    for v, e in enumerate(engs):
        if e.breaks:                                             # §4.2; дорогу через перерыв ловит починка в solve
            solver = routing.solver()
            iv = [solver.FixedDurationIntervalVar(b, b, en - b, False, f"break_{e.id}_{b}") for b, en in e.breaks]
            tdim.SetBreakIntervalsOfVehicle(iv, v, visit)
    routing.SetFixedCostOfAllVehicles(int(w["F"] * SCALE))                      # член (2)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(time_limit * 1000))

    solution = None
    if warm_start:
        g_routes, _ = solve_greedy(p, time_limit=min(3.0, time_limit / 3), initial=initial)
        rid_to_node = {r.id: i for i, r in enumerate(reqs)}
        init = [[rid_to_node[rid] for rid in g_routes[e.id]] for e in engs]
        routing.CloseModelWithParameters(params)
        initial = routing.ReadAssignmentFromRoutes(init, True)
        if initial is not None:
            solution = routing.SolveFromAssignmentWithParameters(initial, params)
    if solution is None:
        solution = routing.SolveWithParameters(params)
    if solution is None:
        raise RuntimeError("OR-Tools: решение не найдено")

    routes: Routes = {}
    visited = set()
    for v, e in enumerate(engs):
        idx, route = routing.Start(v), []
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node < n:
                route.append(node_id[node])
                visited.add(node_id[node])
            idx = solution.Value(routing.NextVar(idx))
        routes[e.id] = route
    unassigned |= {r.id for r in reqs if r.id not in visited}
    return routes, unassigned

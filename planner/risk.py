"""Риск-менеджмент плана (backups/docs/model.md §4.4б): допуск tol_i, стресс-тест Монте-Карло,
фронт вариантов по подушке ε, рекомендация по правилу."""
from __future__ import annotations

import copy
import math
import random
import time

from .engines import solve
from .model import Problem, fmt, hhmm
from .plan import build_plan, routes_from_plan
from .routing import Routes, simulate


# ---------------------------------------------------------------------------
def tolerance(p: Problem, k: str, route: list[str]) -> list[int]:
    """tol_i для каждой остановки: на сколько минут можно задержаться на i, чтобы ни одна
    последующая (и сама i) не вышла из окна / смены. Проход с конца маршрута."""
    e = p.engineers[k]
    stops, fail = simulate(p, e, route)
    assert fail is None
    tol = [0] * len(stops)
    # запас на самой последней точке: до конца окна ИЛИ до конца смены (что раньше)
    carry = math.inf
    for i in range(len(stops) - 1, -1, -1):
        st, r = stops[i], p.requests[stops[i].request_id]
        own = min(r.tw_end - st.start, e.shift_end - st.finish)
        wait_next = (stops[i + 1].start - stops[i + 1].arrive) if i + 1 < len(stops) else 0
        carry = min(own, carry + wait_next)       # задержка на i доходит до i+1 за вычетом ожидания там
        tol[i] = int(carry)
    return tol


def plan_tolerances(p: Problem, routes: Routes) -> dict[str, int]:
    out = {}
    for k, route in routes.items():
        if route:
            for rid, t in zip(route, tolerance(p, k, route)):
                out[rid] = t
    return out


# ---------------------------------------------------------------------------
def stress_test(p: Problem, routes: Routes, runs: int = 200, cv: float = 0.15, seed: int = 0) -> dict:
    """Прогоняем день `runs` раз со случайными задержками дороги и работы (лог-нормально, cv),
    по РЕАЛЬНЫМ (без подушки) временам. Каскад учитывается сам: задержка сдвигает всё дальше,
    ожидание начала окна её поглощает."""
    rng = random.Random(seed)
    sigma = math.sqrt(math.log(1 + cv * cv))
    mu = -sigma * sigma / 2                          # E[noise] = 1
    late_count = {}                                  # rid -> число прогонов с опозданием
    total_late, total_over, any_late = 0, 0.0, 0
    for _ in range(runs):
        run_late = 0
        for k, route in routes.items():
            e, t, cur = p.engineers[k], e_start(p, k), p.engineers[k].start_node
            for rid in route:
                r = p.requests[rid]
                leg = p.travel_raw(cur, rid, e.transport) * math.exp(rng.gauss(mu, sigma))
                start = max(t + leg, r.tw_start)
                if start > r.tw_end:
                    late_count[rid] = late_count.get(rid, 0) + 1
                    run_late += 1
                t = start + r.duration * math.exp(rng.gauss(mu, sigma))
                cur = rid
            if route:
                total_over += max(0.0, t - e.shift_end)
        total_late += run_late
        any_late += run_late > 0
    n_stops = sum(len(v) for v in routes.values())
    return {"runs": runs, "cv": cv,
            "expected_late": round(total_late / runs, 2),
            "p_any_late": round(any_late / runs, 2),
            "expected_overtime_min": round(total_over / runs, 1),
            "late_prob": {rid: round(c / runs, 2) for rid, c in sorted(late_count.items(), key=lambda x: -x[1])},
            "stops": n_stops}


def e_start(p: Problem, k: str) -> int:
    return p.engineers[k].available_from


# ---------------------------------------------------------------------------
def assess(p: Problem, routes: Routes, cfg: dict) -> dict:
    tol = plan_tolerances(p, routes)
    tight = [rid for rid, t in tol.items() if t < cfg.get("tol_min", 10)]
    st = stress_test(p, routes, cfg.get("stress_runs", 200), cfg.get("stress_cv", 0.15))
    used = sum(1 for v in routes.values() if v)
    return {"engineers_used": used, "min_tol": min(tol.values()) if tol else None,
            "tight_stops": tight, "tolerances": tol, "stress": st}


def frontier(ds: dict, engine: str = "ortools", time_limit: float = 3.0, eps_grid=None,
             base_routes: Routes | None = None) -> dict:
    """Варианты плана по подушке ε; для каждого — метрики, напряжение, время счёта."""
    cfg = ds.get("config", {}).get("robustness", {}).get("risk", {})
    eps_grid = eps_grid or cfg.get("eps_grid", [0, 0.1, 0.2, 0.3])
    variants = []
    rb0 = ds.get("config", {}).get("robustness", {})
    base_eps = max(rb0.get("work_factor", 0.0), rb0.get("travel_factor", 0.0), rb0.get("safety_factor", 0.0))
    for eps in eps_grid:
        d = copy.deepcopy(ds)
        is_base = base_routes is not None and abs(eps - base_eps) < 1e-9
        if not is_base:                                        # уровень запаса — на работу и дорогу одинаково
            rb = d["config"].setdefault("robustness", {})
            rb["work_factor"] = rb["travel_factor"] = eps
            rb.pop("safety_factor", None)
        p = Problem.from_dataset(d)                            # строка «текущий план» — в его собственной конфигурации
        t0 = time.time()
        if is_base:
            routes = {k: list(v) for k, v in base_routes.items()}
            unassigned = set(p.requests) - {rid for v in routes.values() for rid in v}
        else:
            routes, unassigned = solve(p, engine, time_limit=time_limit, initial=base_routes)
        t_solve = time.time() - t0
        t0 = time.time()
        a = assess(p, routes, cfg)
        t_assess = time.time() - t0
        km = sum(sum(s.leg_km for s in simulate(p, p.engineers[k], v)[0]) for k, v in routes.items() if v)
        variants.append({"eps": eps, "robustness": d["config"].get("robustness", {}), "engineers_used": a["engineers_used"], "assigned": sum(len(v) for v in routes.values()),
                         "unassigned": len(unassigned), "total_km": round(km, 1), "min_tol": a["min_tol"],
                         "tight_stops": len(a["tight_stops"]), "expected_late": a["stress"]["expected_late"],
                         "p_any_late": a["stress"]["p_any_late"], "expected_overtime_min": a["stress"]["expected_overtime_min"],
                         "t_solve_s": round(t_solve, 2), "t_assess_s": round(t_assess, 3), "routes": routes,
                         "unassigned_ids": sorted(unassigned)})
    thr = cfg.get("late_threshold", 0.5)
    base = next((v for v in variants if abs(v["eps"] - base_eps) < 1e-9), variants[0])
    if base["expected_late"] <= thr:                      # текущий план в норме — ничего не предлагаем
        rec = base
    else:                                                 # иначе — первый вариант с БОЛЬШИМ запасом, проходящий порог
        rec = next((v for v in variants if v["eps"] > base_eps + 1e-9 and v["expected_late"] <= thr
                    and v["assigned"] >= base["assigned"]), None)
    return {"engine": engine, "time_limit": time_limit, "variants": variants, "base_eps": base_eps,
            "recommended_eps": rec["eps"] if rec else None, "late_threshold": thr}


def recommendation_text(p: Problem, fr: dict, plan_names: dict[str, str] | None = None) -> str:
    v0 = next((v for v in fr["variants"] if abs(v["eps"] - fr.get("base_eps", 0)) < 1e-9), fr["variants"][0])
    rec = next((v for v in fr["variants"] if v["eps"] == fr["recommended_eps"]), None)
    s = (f"Текущий план: {v0['engineers_used']} инж., {v0['total_km']} км, остановок без запаса (< 10 мин): {v0['tight_stops']}, "
         f"ожидаемо опозданий в день: {v0['expected_late']} (хотя бы одно — с вероятностью {int(v0['p_any_late']*100)} %).")
    if rec is None:
        return s + (f" Ни один вариант с запасом до {int(fr['variants'][-1]['eps']*100)} % не снижает ожидаемые опоздания "
                    f"до {fr['late_threshold']} в день — нужен дополнительный инженер сверх штата или перенос части заявок.")
    if rec is v0:
        return s + " Напряжение в норме: план укладывается в допустимый уровень опозданий, усиление не требуется."
    d_eng, d_km = rec["engineers_used"] - v0["engineers_used"], round(rec["total_km"] - v0["total_km"], 1)
    return (s + f" Вариант с запасом {int(rec['eps']*100)} %: {rec['engineers_used']} инж. ({d_eng:+d}), {d_km:+.1f} км, "
            f"остановок без запаса {rec['tight_stops']}, ожидаемо опозданий {rec['expected_late']}. "
            + (f"Рекомендация: подключить ещё {d_eng} инж. — напряжение снимается." if d_eng > 0 else "Рекомендация: принять этот вариант — людей не добавляет."))

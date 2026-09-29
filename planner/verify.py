"""Независимая проверка plan.json против датасета: навык, транспорт, окно, смена, время в пути,
метрики. Не использует движки — только исходные данные и формулу времени в пути."""
from __future__ import annotations

from .model import Problem, hhmm


def verify(ds: dict, plan: dict) -> list[str]:
    ds["config"]["travel"]["mode"] = plan.get("travel_mode", "matrix")   # план мог быть посчитан в нормативном режиме
    ds["config"]["robustness"] = plan.get("robustness", {})
    p = Problem.from_dataset(ds)
    for ev in plan.get("events", []):                       # срочные заявки из событий
        if ev["type"] == "urgent_request" and ev["request"]["id"] not in p.requests:
            p.requests[ev["request"]["id"]] = p.new_request(dict(ev["request"], priority="urgent"))
    p.rebuild_matrix(ds.get("matrix"))
    errors: list[str] = []
    seen: dict[str, str] = {}
    for rt in plan["routes"]:
        e = p.engineers[rt["engineer_id"]]
        cur, t = e.id, e.shift_start
        for s in rt["stops"]:
            r = p.requests[s["request_id"]]
            if r.id in seen:
                errors.append(f"{r.id}: назначена дважды ({seen[r.id]}, {e.id})")
            seen[r.id] = e.id
            if r.skill not in e.skills:
                errors.append(f"{r.id}→{e.id}: навык {r.skill} не в {e.skills}")
            if r.required_transport and r.required_transport != e.transport:
                errors.append(f"{r.id}→{e.id}: транспорт {r.required_transport} ≠ {e.transport}")
            earliest = t + p.travel(cur, r.id, e.transport)
            arrive = hhmm(s["arrive"])
            if arrive < earliest:            # позже — можно (выехал позже, ждал); раньше — нельзя
                errors.append(f"{r.id}→{e.id}: прибытие {s['arrive']} раньше возможного {earliest // 60:02d}:{earliest % 60:02d}")
            start = hhmm(s["start"])
            if start < max(arrive, r.tw_start) or start > r.tw_end:
                errors.append(f"{r.id}→{e.id}: начало {s['start']} вне окна/раньше прибытия")
            if start + p.service(r) > e.shift_end:
                errors.append(f"{r.id}→{e.id}: конец {start + p.service(r)} позже смены {e.shift_end}")
            cur, t = r.id, start + p.service(r)
        km = round(sum(s["leg_km"] for s in rt["stops"]), 1)
        if abs(km - rt["total_km"]) > 0.11:
            errors.append(f"{e.id}: пробег {rt['total_km']} ≠ сумма плеч {km}")
    for rid, a in plan["assignments"].items():
        if a["engineer_id"] and seen.get(rid) != a["engineer_id"]:
            errors.append(f"{rid}: assignments говорит {a['engineer_id']}, маршруты — {seen.get(rid)}")
        if not a["engineer_id"] and rid in seen:
            errors.append(f"{rid}: помечена неназначенной, но есть в маршруте {seen[rid]}")
    m = plan["metrics"]
    if m["assigned"] != len(seen):
        errors.append(f"metrics.assigned {m['assigned']} ≠ {len(seen)}")
    used = len({v for v in seen.values()})
    if m["engineers_used"] != used:
        errors.append(f"metrics.engineers_used {m['engineers_used']} ≠ {used}")
    return errors

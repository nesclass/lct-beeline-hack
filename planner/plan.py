"""Сборка plan.json (backups/docs/model.md §2.2) из маршрутов любого движка."""
from __future__ import annotations

import uuid
from datetime import datetime

from .compat import compat
from .explain import text_assigned, text_unassigned, why_assigned, why_unassigned
from .model import Problem, fmt
from .routing import Routes, simulate


def stop_json(p: Problem, st, seq: int, locked: bool = False) -> dict:
    r = p.requests[st.request_id]
    return {"request_id": st.request_id, "seq": seq, "arrive": fmt(st.arrive), "start": fmt(st.start),
            "finish": fmt(st.finish), "wait_min": st.start - st.arrive, "leg_km": round(st.leg_km, 2),
            "leg_min": st.leg_min, "slack_min": r.tw_end - st.start, "locked": locked}


def build_plan(p_full: Problem, p: Problem, routes: Routes, unassigned: set[str], engine: str, *,
               dataset: str = "", solve_time: float = 0.0, locked: dict[str, list[dict]] | None = None,
               inactive: dict[str, str] | None = None, breaks: dict[str, list[tuple[int, int]]] | None = None,
               lost_codes: dict[str, str] | None = None,
               replan_of: str | None = None, events: list[dict] | None = None, now: int | None = None) -> dict:
    """p_full — все заявки/инженеры (для локов и подписей), p — то, что видел солвер."""
    locked, inactive, lost_codes = locked or {}, inactive or {}, lost_codes or {}
    plan_routes, assignments = [], {}
    for k, e_full in p_full.engineers.items():
        pre = locked.get(k, [])
        stops = [dict(s, seq=i + 1, locked=True) for i, s in enumerate(pre)]
        km = sum(s["leg_km"] for s in pre)
        work = sum(p_full.requests[s["request_id"]].duration for s in pre)
        travel = sum(s["leg_min"] for s in pre)
        if k in p.engineers and routes.get(k):
            sim, fail = simulate(p, p.engineers[k], routes[k])
            assert fail is None, f"недопустимый маршрут {k}: {fail}"
            for rid in routes[k]:
                c = compat(p, p.requests[rid], p.engineers[k])
                assert c is None, f"{rid} несовместима с {k}: {c}"
            for st in sim:
                stops.append(stop_json(p_full, st, len(stops) + 1))
                km += st.leg_km
                work += p.requests[st.request_id].duration
                travel += st.leg_min
        shift = e_full.shift_end - e_full.shift_start
        start_node = p.engineers[k].start_node if k in p.engineers else e_full.start_node
        rt = {"engineer_id": k, "name": e_full.name, "transport": e_full.transport,
              "shift": f"{fmt(e_full.shift_start)}–{fmt(e_full.shift_end)}",
              "start": {"node": start_node, "label": p_full.label(start_node)},
              "available_from": fmt(p.engineers[k].available_from if k in p.engineers else e_full.shift_start),
              "stops": stops, "total_km": round(km, 1), "total_work_min": work,
              "total_travel_min": travel, "utilization": round((work + travel) / shift, 2) if shift else 0}
        if k in inactive:
            rt["unavailable_from"] = inactive[k]
        if breaks and breaks.get(k):
            rt["breaks"] = [{"start": fmt(b), "end": fmt(en)} for b, en in breaks[k]]
        plan_routes.append(rt)
        for s in pre:
            assignments[s["request_id"]] = {"engineer_id": k, "locked": True,
                                            "reason": {"constraints_ok": ["SKILL", "TRANSPORT", "WINDOW", "SHIFT"],
                                                       "locked": True},
                                            "text": f"Заявка {s['request_id']} уже выполняется/выполнена инженером {e_full.name}."}
        for rid in routes.get(k, []) if k in p.engineers else []:
            reason = why_assigned(p, routes, rid, k)
            assignments[rid] = {"engineer_id": k, "locked": False, "reason": reason,
                                "text": text_assigned(p, rid, k, reason)}
    for rid in sorted(unassigned):
        reason = why_unassigned(p, routes, rid, lost_codes.get(rid))
        assignments[rid] = {"engineer_id": None, "reason": reason, "text": text_unassigned(p, rid, reason)}

    km_per = {rt["engineer_id"]: rt["total_km"] for rt in plan_routes}
    used = [k for k, v in km_per.items() if any(True for rt in plan_routes if rt["engineer_id"] == k and rt["stops"])]
    metrics = {
        "engineers_used": len(used), "engineers_total": len(p_full.engineers),
        "assigned": sum(1 for a in assignments.values() if a["engineer_id"]),
        "unassigned": len(unassigned),
        "urgent_unassigned": sum(1 for rid in unassigned if p.requests[rid].priority == "urgent"),
        "total_km": round(sum(km_per.values()), 1), "km_per_engineer": km_per,
        "total_travel_min": sum(rt["total_travel_min"] for rt in plan_routes),
        "total_wait_min": sum(s["wait_min"] for rt in plan_routes for s in rt["stops"]),
    }
    return {"plan_id": uuid.uuid4().hex[:8], "engine": engine, "dataset": dataset,
            "travel_mode": p.config["travel"].get("mode", "matrix"), "robustness": p.robustness,
            "created_at": datetime.now().isoformat(timespec="seconds"), "solve_time_s": round(solve_time, 2),
            "replan_of": replan_of, "events": events or [], "now": fmt(now) if now is not None else None,
            "routes": plan_routes, "assignments": assignments, "unassigned": sorted(unassigned),
            "metrics": metrics, "diff": None}


def routes_from_plan(plan: dict, include_locked: bool = True) -> Routes:
    return {rt["engineer_id"]: [s["request_id"] for s in rt["stops"] if include_locked or not s["locked"]]
            for rt in plan["routes"]}

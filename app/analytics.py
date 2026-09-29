"""Аналитика дня: текущий план против движка «по порядку поступления» на тех же вводных."""
from __future__ import annotations

from planner.model import hhmm

from . import planning, store
from .schema import Settings


def _overlap(a: int, b: int, x: int, y: int) -> int:
    return max(0, min(b, y) - max(a, x))


def _load(plan: dict, working: list[dict]) -> dict:
    """Минуты смены каждого работающего инженера: работа / дорога / ожидание / перерыв; остальное — свободно.
    Смена — с учётом ухода (укороченная); если инженер доделывает начатое после ухода — по последнему финишу."""
    routes = {rt["engineer_id"]: rt for rt in plan["routes"]}
    out = {}
    for e in working:
        a, b = hhmm(e["shift_start"]), hhmm(e["shift_end"])
        stops = routes.get(e["id"], {}).get("stops", [])
        b = max([b] + [hhmm(st["finish"]) for st in stops])
        out[e["id"]] = {"work": sum(hhmm(st["finish"]) - hhmm(st["start"]) for st in stops),
                        "travel": sum(st["leg_min"] for st in stops),
                        "wait": sum(st["wait_min"] for st in stops),
                        "break": sum(_overlap(a, b, hhmm(x), hhmm(y)) for x, y in e.get("breaks", [])),
                        "shift": b - a}
    return out


def _windows(plan: dict, requests: dict) -> list[dict]:
    """Где внутри окна клиента инженер приезжает: минуты от открытия окна (меньше нуля — ждёт открытия)
    и длина окна."""
    out = []
    for rt in plan["routes"]:
        for st in rt["stops"]:
            r = requests.get(st["request_id"])
            if r:
                out.append({"off": hhmm(st["arrive"]) - r["tw_start"], "len": r["tw_end"] - r["tw_start"]})
    return out


def _tol(plan: dict, risk: dict | None, since: str | None) -> list[int] | None:
    """Запас по времени (tol) по заявкам, которые ещё впереди: на сколько можно задержаться на заявке,
    чтобы не опоздать ни сюда, ни дальше по маршруту. После перепланирования начатые заявки не считаем —
    у текущего плана их в tol и нет, у базового (он на весь день) отрезаем по тому же времени."""
    if not risk or risk.get("tol") is None:
        return None
    t = hhmm(since) if since else -1
    start = {st["request_id"]: hhmm(st["start"]) for rt in plan["routes"] for st in rt["stops"]}
    return sorted(v for rid, v in risk["tol"].items() if start.get(rid, t) >= t)


def _summary(plan: dict, risk: dict | None, working: list[dict] | None = None, requests: dict | None = None,
             since: str | None = None) -> dict:
    m = plan["metrics"]
    extra = {}
    if working is not None:
        load = _load(plan, working)
        extra = {"load": load, "travel_min": sum(x["travel"] for x in load.values()),
                 "wait_min": sum(x["wait"] for x in load.values()),
                 "tol": _tol(plan, risk, since), "windows": _windows(plan, requests or {})}
    return {"assigned": m["assigned"], "total": m["assigned"] + m["unassigned"], "unassigned": m["unassigned"],
            "engineers_used": m["engineers_used"], "engineers_total": m["engineers_total"],
            "total_km": m["total_km"], "km_per_engineer": m["km_per_engineer"],
            "expected_late": risk["stress"]["expected_late"] if risk else None, **extra}


def baseline(con, sid: str) -> tuple[dict, dict | None]:
    """Как распределил бы заявки простой порядок поступления: те же заявки, те же люди и уходы."""
    s = store.session(con, sid)
    plan = planning.solve_whole_day(con, sid, Settings(**s["settings"]), engine="baseline")
    return plan, plan["risk"]


def report(con, sid: str) -> dict:
    s = store.session(con, sid)
    plan, _, risk = store.plan(con, sid, s["plan_id"])
    bplan, brisk = baseline(con, sid)
    view = planning.view(con, sid)
    lost = planning.unavailable_from(con, sid)
    working = planning.working_engineers({"engineers": store.engineers(con, sid)}, lost, planning.breaks_of(con, sid))
    hours = []
    for h in range(9, 22):
        a, b = h * 60, (h + 1) * 60
        # по инженерам, а не по остановкам: у кого в этот час работа, а не сколько у него остановок
        in_work = sum(1 for rt in plan["routes"]
                      if any(hhmm(st["start"]) < b and hhmm(st["finish"]) > a for st in rt["stops"]))
        # с учётом уходов и недоступности — не номинальная смена из справочника, а укороченная
        # час, целиком занятый перерывом, — не на смене; частичный перерыв час не снимает
        on_shift = sum(1 for e in working if hhmm(e["shift_start"]) < b and hhmm(e["shift_end"]) > a
                       and not any(hhmm(x) <= a and hhmm(y) >= b for x, y in e.get("breaks", [])))
        hours.append({"h": h, "in_work": in_work, "on_shift": on_shift})
    labels = view["dict"].get("skills", {})
    skills = []
    for k in ("local", "connect", "emergency"):
        ids = [rid for rid, r in view["requests"].items() if r["skill"] == k and rid in plan["assignments"]]
        skills.append({"skill": k, "label": labels.get(k, k), "total": len(ids),
                       "assigned": sum(1 for rid in ids if plan["assignments"][rid]["engineer_id"])})
    now = plan.get("now")
    return {"current": _summary(plan, risk, working, view["requests"], now),
            "baseline": _summary(bplan, brisk, working, view["requests"], now),
            "hours": hours, "skills": skills, "now": now}

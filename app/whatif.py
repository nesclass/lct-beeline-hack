"""Предпросмотры: что будет, если… Ничего не пишут. Снимок перепланирования на часы сессии и
пробная вставка (probe); для недоступности — ещё и быстрый расчёт перепланирования, чтобы
«возьмёт такой-то» совпадало с тем, что сделает «Перепланировать»."""
from __future__ import annotations

from planner.engines import drop_until_feasible
from planner.explain import probe
from planner.model import fmt, hhmm
from planner.replan import Snapshot, snapshot

from . import catalog, planning, store
from .schema import NewRequest, Unavailable


def _current(con, sid: str) -> tuple[dict, dict]:
    s = store.session(con, sid)
    return s, store.plan(con, sid, s["plan_id"])[0]


def snap(con, sid: str, extra: list[dict] = ()) -> tuple[Snapshot, dict]:
    """Снимок на часы сессии с учётом очереди и пробных событий extra."""
    s, old = _current(con, sid)
    ds = planning.dataset(con, sid)
    old = {**old, "robustness": ds["config"]["robustness"]}
    evs = store.events(con, sid, pending_only=True) + list(extra)
    return snapshot(ds, old, evs, now=s["clock_min"]), old


def unavailable_event(con, sid: str, eid: str, body: Unavailable) -> dict:
    """Документ события недоступности, как его запишет роутер. ValueError — время раньше часов."""
    s = store.session(con, sid)
    e = next(x for x in store.engineers(con, sid) if x["id"] == eid)
    if body.mode == "absent":
        return {"type": "engineer_unavailable", "time": e["shift_start"], "engineer_id": eid,
                "finish_current": False, "mode": "absent", "reason": body.reason}
    if body.mode == "break":
        if hhmm(body.time) < s["clock_min"]:
            raise ValueError("начало перерыва раньше часов сессии")
        return {"type": "engineer_break", "time": body.time, "until": body.until, "engineer_id": eid,
                "reason": body.reason}
    t = body.time or fmt(s["clock_min"])
    if hhmm(t) < s["clock_min"]:
        raise ValueError("время ухода раньше часов сессии")
    return {"type": "engineer_unavailable", "time": t, "engineer_id": eid,
            "finish_current": body.finish_current, "mode": "leave", "reason": body.reason}


def released(sn: Snapshot, old: dict, eid: str) -> tuple[dict | None, list[str]]:
    """Текущая заявка инженера и заявки, которые у него освободятся: после ухода или те,
    что из-за перерыва не помещаются в маршрут — по тому же правилу, что починка в solve
    (сдвиг за перерыв заявку не освобождает)."""
    t = hhmm(sn.leave[eid]) if eid in sn.leave else None
    e = sn.p.engineers.get(eid)
    lost_to_break = set(drop_until_feasible(sn.p, e, sn.initial.get(eid, []))[1]) if e and e.breaks else set()
    cur = None
    if sn.locked.get(eid) and hhmm(sn.locked[eid][-1]["finish"]) > sn.T:
        last = sn.locked[eid][-1]
        cur = {"request_id": last["request_id"], "finish": last["finish"]}
    rt = next(r for r in old["routes"] if r["engineer_id"] == eid)
    out = []
    for s in rt["stops"]:
        rid = s["request_id"]
        if rid not in sn.p.requests:                    # заморожена — остаётся за ним
            continue
        if eid in sn.gone or (t is not None and hhmm(s["finish"]) > t) or rid in lost_to_break:
            out.append(rid)
    return cur, out


def forecast(con, sid: str, ev: dict, rids: list[str]) -> tuple[dict[str, dict | None], list[dict]]:
    """Кому уйдут освободившиеся заявки по-настоящему: перепланирование с гипотетическим событием,
    быстрым движком, без записи. Прежняя жадная вставка по одной давала другие имена, чем потом
    давал пересчёт, — диспетчеру обещали одного инженера, а заявка уходила другому."""
    plan, old = planning._replan_plan(con, sid, "minimal", [{**ev, "id": "preview"}], engine="greedy")[:2]
    start = {s["request_id"]: s["start"] for rt in plan["routes"] for s in rt["stops"]}
    who = {rid: ({"engineer_id": a["engineer_id"], "start": start.get(rid)}
                 if (a := plan["assignments"].get(rid)) and a["engineer_id"] else None)
           for rid in rids}
    # что это значит для тех, кто берёт: пробег и конец дня до и после — чтобы на «а ему не тяжело?»
    # было чем ответить
    before = {rt["engineer_id"]: rt for rt in old["routes"]}
    load = []
    for rt in plan["routes"]:
        added = [rid for rid in rids if (who.get(rid) or {}).get("engineer_id") == rt["engineer_id"]]
        if not added:
            continue
        b = before.get(rt["engineer_id"], {"total_km": 0, "stops": []})
        load.append({"engineer_id": rt["engineer_id"], "added": added,
                     "km_before": round(b["total_km"], 1), "km_after": round(rt["total_km"], 1),
                     "stops_before": len(b["stops"]), "stops_after": len(rt["stops"]),
                     "finish_before": b["stops"][-1]["finish"] if b["stops"] else None,
                     "finish_after": rt["stops"][-1]["finish"] if rt["stops"] else None})
    return who, load


def unavailable_preview(con, sid: str, eid: str, body: Unavailable) -> dict:
    ev = unavailable_event(con, sid, eid, body)
    sn, old = snap(con, sid, [{**ev, "id": "preview"}])
    cur, rids = released(sn, old, eid)
    who, load = forecast(con, sid, ev, rids) if rids else ({}, [])
    names = {k: e.name for k, e in sn.p_full.engineers.items()}
    rows = [{"request_id": rid,
             "window": f"{fmt(sn.p_full.requests[rid].tw_start)}–{fmt(sn.p_full.requests[rid].tw_end)}",
             "taker": ({"engineer_id": w["engineer_id"], "name": names[w["engineer_id"]], "start": w["start"]}
                       if (w := who.get(rid)) else None)}
            for rid in sorted(rids, key=lambda x: sn.p_full.requests[x].tw_start)]
    for x in load:
        x["name"] = names[x["engineer_id"]]
    out = {"leave": ev["time"], "current": cur, "released": rows, "can_take": sum(1 for r in rows if r["taker"]),
           "takers": load}
    if "until" in ev:
        out["until"] = ev["until"]
    return out


def request_candidates(con, sid: str, body: NewRequest) -> dict:
    doc = catalog.draft_request(con, sid, body, "R-preview")
    out = {"skill": doc["skill"], "duration_min": doc["duration_min"], "candidates": None}
    if not store.session(con, sid)["plan_id"]:
        return out
    sn, _ = snap(con, sid, [{"id": "preview", "type": "urgent_request", "time": body.tw_start, "request": doc}])
    cands = []
    for k, e in sn.p.engineers.items():
        pr = probe(sn.p, sn.initial, doc["id"], k)
        if pr["feasible"]:
            cands.append({"engineer_id": k, "name": e.name, "start": pr["start"], "delta_km": pr["delta_km"]})
    out["candidates"] = sorted(cands, key=lambda c: (c["start"], c["delta_km"]))
    return out


def check_move(con, sid: str, rid: str, eid: str) -> str | None:
    """None — перенос допустим; иначе причина для диспетчера."""
    sn, old = snap(con, sid, [{"id": "preview", "type": "move_request", "time": "00:00", "request_id": rid, "engineer_id": eid}])
    if rid not in sn.p.requests:
        # заморожена (снимок): либо работа уже началась, либо инженер только выехал —
        # разница видна по времени начала в текущем плане относительно часов сессии
        started = any(hhmm(s["start"]) <= sn.T for rt in old["routes"] for s in rt["stops"] if s["request_id"] == rid)
        if started:
            return "заявка уже начата — переназначить нельзя"
        return "инженер уже выехал к заявке — переназначить нельзя"
    if eid not in sn.p.engineers:
        return f"{sn.p_full.engineers[eid].name} уже не работает"
    routes = {k: [x for x in v if x != rid] for k, v in sn.initial.items()}
    pr = probe(sn.p, routes, rid, eid)
    if pr["feasible"]:
        return None
    return f"нельзя отдать {sn.p_full.engineers[eid].name}: {pr['blocker']['text']}"


def impact(con, sid: str) -> dict:
    s, plan = _current(con, sid)
    pending = store.events(con, sid, pending_only=True)
    sn, old = snap(con, sid)
    orphaned: set[str] = set()
    for ev in pending:
        if ev["type"] in ("engineer_unavailable", "engineer_break"):
            orphaned |= set(released(sn, old, ev["engineer_id"])[1])
        elif ev["type"] == "new_request":
            orphaned.add(ev["request_id"])
        elif ev["type"] == "urgent_request":
            orphaned.add(ev["request"]["id"])
    risk = store.plan(con, sid, s["plan_id"])[2]
    # since — часы, на которые завели первое изменение (поле at), а не время самого события:
    # «уйдёт в 14:00», заведённое в 12:00, копится в очереди с 12:00
    since = min((ev.get("at", ev["time"]) for ev in pending), key=hhmm, default=None)
    return {"since": since,
            "orphaned": sorted(orphaned),
            "urgent_unassigned": sum(1 for ev in pending if ev["type"] == "urgent_request"),
            "expected_late": risk["stress"]["expected_late"] if risk else None}

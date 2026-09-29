"""Мост между базой приложения и пакетом planner.

Здесь собирается датасет сессии (с матрицей от гео-слоя), запускается движок и
складывается план. Экономики в у.е. тут нет и не должно появиться. Веса модели —
константы сценария, кроме F, который выбирается пресетом «что важнее».
"""
from __future__ import annotations

import copy
import time

from planner.engines import solve
from planner.model import Problem, hhmm
from planner.plan import build_plan, routes_from_plan
from planner.replan import replan as _replan
from planner.risk import assess

from . import catalog, geo, scenarios, store
from .schema import PRIORITY_F, Settings


def dataset(con, sid: str, drop_pending_cancels: bool = False) -> dict:
    """Датасет сессии: справочники сценария, живые инженеры и заявки, матрица гео-слоя."""
    s = store.session(con, sid)
    base = scenarios.load(s["scenario"])
    gone = catalog.cancelled_ids(con, sid, pending_too=drop_pending_cancels)
    ds = {"meta": dict(base.get("meta", {})), "config": copy.deepcopy(base["config"]),
          "dictionaries": base.get("dictionaries", {}),
          "engineers": store.engineers(con, sid),
          "requests": [r for r in store.requests(con, sid) if r["id"] not in gone],
          "events": []}

    points = {e["id"]: (e["start"]["lat"], e["start"]["lon"]) for e in base["engineers"]}
    points.update({r["id"]: (r["lat"], r["lon"]) for r in base["requests"]})
    # заявки, заведённые днём, досчитываются тем же /table: матрица сценария плюс их точки
    extra = {r["id"]: (r["lat"], r["lon"]) for r in store.requests(con, sid) if r["id"] not in points}
    points.update(extra)
    name = s["scenario"] + (f"+{geo.cache.key(extra)}" if extra else "")
    m = geo.matrix_for(name, points)                   # без новых заявок - общая на сценарий

    ds["matrix"] = m
    ds["config"]["travel"]["mode"] = "external"
    ds["meta"]["travel_source"] = m["source"]
    apply_settings(ds, Settings(**s["settings"]))
    return ds


def apply_settings(ds: dict, st: Settings) -> None:
    rb = ds["config"].setdefault("robustness", {})
    rb["work_factor"] = st.work_pct / 100
    rb["travel_factor"] = st.travel_pct / 100
    rb["travel_min"] = st.travel_min
    ds["config"]["weights"]["F"] = PRIORITY_F[st.priority]


def engine_of(st: Settings) -> tuple[str, dict, str]:
    """Движок, его аргументы и подпись для плана."""
    if st.engine == "ortools":
        return ("ortools", {"time_limit": st.time_limit, "warm_start": st.warm_start},
                "ortools" + (" (warm start greedy)" if st.warm_start else ""))
    return "greedy", {"time_limit": min(st.time_limit, 5)}, "greedy"


def _at_current_position(p: Problem, plan: dict) -> Problem:
    """Ставит инженеров туда, где их застал план: после перепланирования старт виртуальный —
    последняя замороженная заявка и момент освобождения; перерывы — тоже из плана. Без этого
    оценка риска считала бы день от депо и описывала бы не то расписание, которое исполняется."""
    for rt in plan["routes"]:
        e = p.engineers.get(rt["engineer_id"])
        if e is not None:
            e.start_node = rt["start"]["node"]
            e.available_from = hhmm(rt["available_from"])
            e.breaks = [(hhmm(x["start"]), hhmm(x["end"])) for x in rt.get("breaks", [])]
    return p


def assess_safe(p: Problem, routes: dict, cfg: dict) -> dict | None:
    """Оценка риска не должна ронять расчёт плана: при внутреннем несоответствии — None."""
    try:
        a = assess(p, routes, cfg)
    except AssertionError:
        return None
    return {"tol": a["tolerances"], "late_prob": a["stress"]["late_prob"],
            "stress": {k: v for k, v in a["stress"].items() if k != "late_prob"},
            "tight": a["tight_stops"], "min_tol": a["min_tol"]}


def unavailable_from(con, sid: str) -> dict[str, str]:
    """Инженер → самое раннее объявленное время ухода (любые события, принятые и нет)."""
    lost: dict[str, str] = {}
    for ev in store.events(con, sid):
        if ev["type"] == "engineer_unavailable":
            k = ev["engineer_id"]
            lost[k] = min(lost.get(k, ev["time"]), ev["time"], key=hhmm)
    return lost


def breaks_of(con, sid: str) -> dict[str, list[tuple[str, str]]]:
    """Инженер → перерывы (начало, конец) в ЧЧ:ММ по времени, из любых событий, принятых и нет."""
    out: dict[str, list[tuple[str, str]]] = {}
    for ev in store.events(con, sid):
        if ev["type"] == "engineer_break":
            v = out.setdefault(ev["engineer_id"], [])
            if (ev["time"], ev["until"]) not in v:
                v.append((ev["time"], ev["until"]))
    return {k: sorted(v, key=lambda x: hhmm(x[0])) for k, v in out.items()}


def working_engineers(ds: dict, lost: dict[str, str],
                      breaks: dict[str, list[tuple[str, str]]] | None = None) -> list[dict]:
    """Кто работает в день целиком: недоступный до начала смены — нет, уходящий — до ухода.
    Перерыв — не уход: инженер работает, но в перерыв ни работы, ни дороги."""
    breaks = breaks or {}
    out = []
    for e in ds["engineers"]:
        t = lost.get(e["id"])
        if e["id"] in breaks:
            e = dict(e, breaks=[list(x) for x in breaks[e["id"]]])
        if t is None:
            out.append(e)
        elif hhmm(t) > hhmm(e["shift_start"]):
            out.append(dict(e, shift_end=min(e["shift_end"], t, key=hhmm)))
    return out


def pending_pins(con, sid: str, p: Problem) -> dict[str, str]:
    """Переносы из очереди («Переназначить») как закрепления для расчёта на весь день:
    только заявки и инженеры, которые есть в задаче; более поздний перенос — главнее."""
    pins: dict[str, str] = {}
    for ev in store.events(con, sid, pending_only=True):
        if ev["type"] == "move_request" and ev["request_id"] in p.requests and ev["engineer_id"] in p.engineers:
            pins[ev["request_id"]] = ev["engineer_id"]
    return pins


def solve_whole_day(con, sid: str, st: Settings, engine: str | None = None) -> dict:
    """План на весь день по вводным сессии: отменённые (и в очереди) не идут, недоступные —
    по правилу working_engineers. engine="baseline" — движок по порядку поступления. Не сохраняет."""
    s = store.session(con, sid)
    lost, brk = unavailable_from(con, sid), breaks_of(con, sid)
    ds = dataset(con, sid, drop_pending_cancels=True)
    apply_settings(ds, st)
    p_full = Problem.from_dataset(ds)
    p = Problem.from_dataset({**ds, "engineers": working_engineers(ds, lost, brk)})
    pins = pending_pins(con, sid, p)
    p.pinned = dict(pins)
    name, kw, label = ("baseline", {}, "baseline") if engine == "baseline" else engine_of(st)
    t0 = time.time()
    routes, unassigned = solve(p, name, **kw)
    plan = build_plan(p_full, p, routes, unassigned, label,
                      dataset=s["scenario"], solve_time=time.time() - t0, inactive=lost,
                      breaks={k: [(hhmm(b), hhmm(e)) for b, e in v] for k, v in brk.items()})
    if pins:                                    # как перепланирование: закреплённое помечено ручным
        for rid, k in pins.items():
            a = plan["assignments"].get(rid)
            if a and a["engineer_id"] == k:
                a["manual"] = True
                a["reason"]["manual"] = True
        plan["pins"] = pins
    plan["risk"] = assess_safe(_at_current_position(p_full, plan),
                               routes_from_plan(plan, include_locked=False),
                               ds["config"]["robustness"]["risk"])
    return plan


def build(con, sid: str) -> dict:
    """Базовое расписание: решаем задачу целиком, сохраняем, гасим непринятые события.
    Инженер, объявленный недоступным до начала своей смены, в расчёт не идёт; объявленный
    на время позже — работает до него. Маршрут помечен unavailable_from, чтобы и
    перепланирования о нём помнили."""
    s = store.session(con, sid)
    st = Settings(**s["settings"])
    pending = store.events(con, sid, pending_only=True)   # гасим только их, не то, что придёт во время расчёта
    plan = solve_whole_day(con, sid, st)
    plan["accepted"], plan["accepted_at"] = True, time.time()
    with store.tx(con):
        store.save_plan(con, sid, plan, "base", st.model_dump(), risk=plan["risk"])
        store.set_plan(con, sid, plan["plan_id"])
        store.mark_events_applied(con, sid, plan["plan_id"], [e["id"] for e in pending])
    return plan


def _replan_plan(con, sid: str, mode: str = "minimal", extra: list | None = None,
                 engine: str | None = None) -> tuple[dict, dict, list, dict | None]:
    """Расчёт перепланирования без записи: (план, план-основа, события, заменяемый черновик).
    extra — гипотетические события поверх очереди (предпросмотр), engine — другой движок
    (для предпросмотра — быстрый, с тем же замораживанием и штрафом за перестановки)."""
    s = store.session(con, sid)
    st = Settings(**s["settings"])
    current = store.plan(con, sid, s["plan_id"])[0]
    stale = current if not current.get("accepted", True) else None
    if stale:
        old = store.plan(con, sid, stale["replan_of"])[0]
        events = store.events(con, sid, applied_to=stale["plan_id"]) + store.events(con, sid, pending_only=True)
    else:
        old = current
        events = store.events(con, sid, pending_only=True)
    ds = dataset(con, sid)
    # ядро берёт запас из старого плана (контракт §L); источник истины — текущие настройки
    old = {**old, "robustness": ds["config"]["robustness"]}
    name, kw, _ = engine_of(st if engine is None else st.model_copy(update={"engine": engine}))
    plan = _replan(ds, old, events + list(extra or []), name, now=s["clock_min"], stability=mode,
                   time_limit=kw["time_limit"], dataset_path=s["scenario"])
    return plan, old, events, stale


def replan_now(con, sid: str, mode: str = "minimal") -> dict:
    """Перепланирование от часов сессии: замораживаем сделанное, решаем остаток дня.
    Черновик — не рабочее расписание, пока его не приняли («Принять»). Перепланирование
    над непринятым черновиком не наращивает цепочку — оно заменяет черновик: считает от
    последнего принятого плана и объединяет события черновика с тем, что накопилось в
    очереди с тех пор, а сам черновик убирает."""
    s = store.session(con, sid)
    st = Settings(**s["settings"])
    plan, old, events, stale = _replan_plan(con, sid, mode)
    ds = dataset(con, sid)
    p_new = Problem.from_dataset({**ds, "config": {**ds["config"], "robustness": plan["robustness"]}})
    plan["risk"] = assess_safe(_at_current_position(p_new, plan),
                               routes_from_plan(plan, include_locked=False),
                               ds["config"]["robustness"]["risk"])
    plan["accepted"], plan["accepted_at"] = False, None
    with store.tx(con):
        store.save_plan(con, sid, plan, "replan", st.model_dump(), risk=plan["risk"], replan_of=old["plan_id"])
        store.set_plan(con, sid, plan["plan_id"])
        store.mark_events_applied(con, sid, plan["plan_id"], [e["id"] for e in events])
        if stale:
            store.delete_plan(con, sid, stale["plan_id"])
    return plan


def accept(con, sid: str) -> dict:
    """Принять черновик перепланирования: он становится рабочим расписанием дня."""
    s = store.session(con, sid)
    plan = store.plan(con, sid, s["plan_id"])[0]
    if plan.get("accepted", True):
        raise ValueError("принимать нечего — текущее расписание уже рабочее")
    plan["accepted"], plan["accepted_at"] = True, time.time()
    affected = sorted(k for k, v in (plan.get("diff") or {}).get("engineers", {}).items() if v["status"] != "unchanged")
    with store.tx(con):
        store.update_plan(con, sid, plan)
    return {"plan_id": plan["plan_id"], "affected": affected}


def rollback(con, sid: str) -> None:
    """Откатить непринятый черновик: сессия возвращается к прежнему плану, а события,
    учтённые черновиком, снова в очереди — вместе с тем, что завели после него."""
    s = store.session(con, sid)
    plan = store.plan(con, sid, s["plan_id"])[0]
    if plan.get("accepted", True) or not plan.get("replan_of"):
        raise ValueError("откатывать нечего — текущее расписание уже принято")
    with store.tx(con):
        store.unapply_events(con, sid, plan["plan_id"])
        store.set_plan(con, sid, plan["replan_of"])
        store.delete_plan(con, sid, plan["plan_id"])


def _previous(con, sid: str, plan_id: str) -> dict:
    prev, _, risk = store.plan(con, sid, plan_id)
    # «До» на диаграмме рисуется как обычный план: нужны и назначения (почему у этого инженера), и запас
    return {"plan_id": plan_id, "routes": prev["routes"], "metrics": prev["metrics"], "risk": risk,
            "replan_of": prev.get("replan_of"), "assignments": prev["assignments"], "unassigned": prev["unassigned"]}


def history(con, sid: str) -> list[dict]:
    """Цепочка планов дня: от базового (или утверждённого варианта) до текущего."""
    chain, pid = [], store.session(con, sid)["plan_id"]
    while pid:
        plan, params, _ = store.plan(con, sid, pid)
        kind = store.plan_kind(con, sid, pid)
        m = plan["metrics"]
        changes = (sum(1 for v in plan["diff"]["requests"].values() if v["status"] != "unchanged")
                   if plan.get("diff") else None)
        chain.append({"plan_id": pid, "kind": kind, "at": plan.get("now"), "label": params.get("variant_label"),
                      "events": plan.get("events", []), "assigned": m["assigned"],
                      "total": m["assigned"] + m["unassigned"], "total_km": m["total_km"],
                      "engineers_used": m["engineers_used"], "changes": changes, "accepted": plan.get("accepted", True)})
        pid = plan.get("replan_of")
    return chain[::-1]


def view(con, sid: str) -> dict:
    """План и всё, что нужно интерфейсу, чтобы его нарисовать."""
    s = store.session(con, sid)
    got = store.plan(con, sid, s["plan_id"])
    plan, _, risk = got
    ds = dataset(con, sid)
    p = Problem.from_dataset(ds)
    return {
        "plan": plan, "risk": risk, "dict": p.dictionaries, "meta": ds["meta"],
        "previous": (_previous(con, sid, plan["replan_of"]) if plan.get("replan_of") else None),
        "travel_source": ds["meta"].get("travel_source", "haversine"),
        "engineers": {k: {"id": k, "name": e.name, "transport": e.transport, "skills": e.skills,
                          "shift_start": e.shift_start, "shift_end": e.shift_end,
                          "lat": e.lat, "lon": e.lon, "start": e.start_label}
                      for k, e in p.engineers.items()},
        "requests": {r.id: {"id": r.id, "type": r.type, "district": r.district, "address": r.address,
                            "lat": r.lat, "lon": r.lon, "skill": r.skill, "duration": r.duration,
                            "duration_text": r.duration_text, "tw_start": r.tw_start, "tw_end": r.tw_end,
                            "priority": r.priority, "required_transport": r.required_transport}
                     for r in p.requests.values()},
    }

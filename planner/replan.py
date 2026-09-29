"""Перепланирование (backups/docs/model.md §1.5 L1–L6, §3): снимок на момент T, применение событий,
решение остатка дня тем же движком с членом стабильности, diff со старым планом.

Снимок вынесен отдельно: по нему же приложение считает предпросмотры («кто успеет взять»,
«что освободится»), не запуская движок."""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

from .engines import solve
from .model import Problem, hhmm
from .plan import build_plan


@dataclass
class Snapshot:
    p_full: Problem                          # все заявки и инженеры — для подписей и замороженного
    p: Problem                               # что видит движок: незамороженные заявки, работающие инженеры
    initial: dict[str, list[str]]            # прежние маршруты по заявкам из p — тёплый старт и probe
    locked: dict[str, list[dict]]            # замороженные остановки по инженерам
    leave: dict[str, str]                    # инженер → ЧЧ:ММ ухода (раньше — значит раньше)
    gone: set[str]                           # кто уже не работает к T
    pins: dict[str, str]                     # заявка → инженер, закреплённые диспетчером
    lost_codes: dict[str, str] = field(default_factory=dict)
    cancelled: set[str] = field(default_factory=set)
    T: int = 0
    breaks: dict[str, list[tuple[int, int]]] = field(default_factory=dict)   # все, и прошедшие — план их помнит


def snapshot(ds: dict, old: dict, events: list[dict], *, now: int | None = None,
             stability: str = "minimal") -> Snapshot:
    ds = copy.deepcopy(ds)
    for ev in events:                                   # срочные заявки — в общий список (L5)
        if ev["type"] == "urgent_request":
            ds["requests"].append(dict(ev["request"], priority="urgent"))
    if stability == "full":
        ds["config"]["weights"]["G"] = 0
    ds["config"]["travel"]["mode"] = old.get("travel_mode", "matrix")
    ds["config"]["robustness"] = old.get("robustness", {})
    p_full = Problem.from_dataset(ds)
    T = now if now is not None else max(hhmm(ev["time"]) for ev in events)

    # кто и когда уходит: погашенное прошлыми перепланированиями живёт в маршрутах старого плана,
    # новое — в событиях; повторное объявление время не сдвигает вперёд
    leave: dict[str, str] = {rt["engineer_id"]: rt["unavailable_from"]
                             for rt in old["routes"] if "unavailable_from" in rt}
    for ev in events:
        if ev["type"] == "engineer_unavailable":
            k = ev["engineer_id"]
            leave[k] = min(leave.get(k, ev["time"]), ev["time"], key=hhmm)
    gone = {k for k, t in leave.items() if hhmm(t) <= T}

    # закрепления: живущие в старом плане (и те, что тогда не поместились), прежние пометки manual
    # и новые переносы; держим до явного «открепить» (§4.0), за ушедшим не держим
    pins = {rid: a["engineer_id"] for rid, a in old["assignments"].items() if a.get("manual") and a["engineer_id"]}
    pins.update(old.get("pins", {}))
    for ev in events:
        if ev["type"] == "move_request":
            pins[ev["request_id"]] = ev["engineer_id"]
    pins = {rid: k for rid, k in pins.items() if k not in gone}

    # --- снимок (L1–L2): что уже сделано / в работе, где инженер и когда освободится
    locked: dict[str, list[dict]] = {}
    pool: list[str] = []
    prev_owner: dict[str, str] = {}
    engineers = {k: copy.copy(e) for k, e in p_full.engineers.items()}
    prev_routes: dict[str, list[str]] = {}
    for rt in old["routes"]:
        k = rt["engineer_id"]
        e = engineers[k]
        locked[k], prev_routes[k] = [], []
        for s in rt["stops"]:
            # замораживаем начатые/выполненные; для работающего инженера — и ту, к которой он уже выехал
            # (выезд = прибытие − дорога): развернуть его в пути прототип не пытается
            started = hhmm(s["start"]) <= T
            departed = hhmm(s["arrive"]) - s["leg_min"] <= T
            if started or (departed and k not in gone):
                locked[k].append(dict(s))
            else:
                pool.append(s["request_id"])
                prev_owner[s["request_id"]] = k
                prev_routes[k].append(s["request_id"])
        if locked[k]:
            last = locked[k][-1]
            e.start_node, e.available_from = last["request_id"], max(T, hhmm(last["finish"]))
        else:
            e.start_node, e.available_from = e.id, max(T, e.shift_start)
    pool += [rid for rid in old["unassigned"]]
    known = {s["request_id"] for rt in old["routes"] for s in rt["stops"]} | set(old["unassigned"])
    pool += [rid for rid in p_full.requests if rid not in known]   # заведены после плана (L5)
    cancelled: set[str] = set()
    lost_codes: dict[str, str] = {}

    # --- события (L3–L5)
    for ev in events:
        if ev["type"] == "engineer_unavailable":
            k = ev["engineer_id"]
            if k in gone and not ev.get("finish_current", True) and locked[k] and hhmm(locked[k][-1]["finish"]) > T:
                s = locked[k].pop()                     # бросает текущую — она снова в пуле
                pool.append(s["request_id"])
            for rid, o in prev_owner.items():
                if o == k:
                    lost_codes[rid] = "ENGINEER_LOST"
        elif ev["type"] == "cancel_request":
            rid = ev["request_id"]
            cancelled.add(rid)
            if rid in pool:
                pool.remove(rid)
            for k, stops in locked.items():
                for s in stops:
                    if s["request_id"] == rid and hhmm(s["finish"]) > T:   # была в работе → инженер свободен (L4)
                        stops.remove(s)
                        e = engineers[k]
                        e.start_node, e.available_from = rid, T
        elif ev["type"] == "urgent_request":
            pool.append(ev["request"]["id"])
    for k, t in leave.items():                          # уйдёт позже T — работает до ухода
        if k not in gone:
            # уход может прийтись раньше, чем он освободится от замороженного (уже
            # делает/едет к заявке, которая кончается позже ухода): для движка смена
            # тогда кончается в момент освобождения — иначе available_from > shift_end
            # и OR-Tools получает пустой диапазон старта (docs task-5c). Замороженное
            # доделывается, новых заявок после ухода нет.
            engineers[k].shift_end = max(min(engineers[k].shift_end, hhmm(t)), engineers[k].available_from)
    for e in engineers.values():                        # смена уже кончилась (часы позже неё) — свободен с T,
        e.shift_end = max(e.shift_end, e.available_from)  # но новых заявок нет: пустое окно, а не пустой диапазон для OR-Tools
    # перерывы (§4.2): прежние живут в маршрутах старого плана, новые — в событиях
    brk: dict[str, list[tuple[int, int]]] = {rt["engineer_id"]: [(hhmm(x["start"]), hhmm(x["end"])) for x in rt["breaks"]]
                                             for rt in old["routes"] if rt.get("breaks")}
    for ev in events:
        if ev["type"] == "engineer_break":
            v = brk.setdefault(ev["engineer_id"], [])
            x = (hhmm(ev["time"]), hhmm(ev["until"]))
            if x not in v:
                v.append(x)
    brk = {k: sorted(v) for k, v in brk.items() if k in engineers}
    for k, v in brk.items():
        engineers[k].breaks = [x for x in v if x[1] > T]

    # --- редуцированная задача
    order = [rid for rid in p_full.requests if rid in pool]
    p = Problem({rid: p_full.requests[rid] for rid in order},
                {k: e for k, e in engineers.items() if k not in gone},
                p_full.config, p_full.dictionaries, prev_owner)
    p._pos, p._km, p._min = p_full._pos, p_full._km, p_full._min
    p.pinned = {rid: k for rid, k in pins.items() if rid in p.requests}
    initial = {k: [rid for rid in v if rid in p.requests] for k, v in prev_routes.items() if k in p.engineers}
    return Snapshot(p_full, p, initial, locked, leave, gone, pins, lost_codes, cancelled, T, brk)


def replan(ds: dict, old: dict, events: list[dict], engine: str, *, now: int | None = None,
           stability: str = "minimal", time_limit: float = 10.0, dataset_path: str = "") -> dict:
    s = snapshot(ds, old, events, now=now, stability=stability)
    p = s.p
    t0 = time.time()
    routes, unassigned = solve(p, engine, time_limit=time_limit, initial=s.initial)
    lost_codes = dict(s.lost_codes)
    urgent_placed = any(p.requests[x].priority == "urgent" for v in routes.values() for x in v)
    for rid in unassigned:
        if p.requests[rid].priority != "urgent" and rid not in lost_codes and old["assignments"].get(rid, {}).get("engineer_id"):
            lost_codes[rid] = "DISPLACED" if urgent_placed else "BUSY"
    new = build_plan(s.p_full, p, routes, unassigned, engine, dataset=dataset_path, solve_time=time.time() - t0,
                     locked=s.locked, inactive=s.leave, breaks=s.breaks, lost_codes=lost_codes, replan_of=old["plan_id"],
                     events=events, now=s.T)
    for rid, k in p.pinned.items():
        a = new["assignments"].get(rid)
        if a and a["engineer_id"] == k:
            a["manual"] = True
            a["reason"]["manual"] = True
    new["pins"] = {rid: k for rid, k in s.pins.items() if rid not in s.cancelled}
    new["stability"] = stability
    new["diff"] = diff(old, new, s.cancelled)
    return new


def _index(plan: dict) -> dict[str, dict]:
    out = {}
    for rt in plan["routes"]:
        for s in rt["stops"]:
            out[s["request_id"]] = {"engineer_id": rt["engineer_id"], "seq": s["seq"], "start": s["start"]}
    return out


def _rank(plan: dict, common: set[str]) -> dict[str, int]:
    out = {}
    for rt in plan["routes"]:
        seq = [s["request_id"] for s in rt["stops"] if s["request_id"] in common]
        out.update({rid: i for i, rid in enumerate(seq)})
    return out


def _off(plan: dict, rt: dict) -> bool:
    """Инженер уже не работает в этом плане: уход наступил к его моменту. У базового плана
    момента нет: там снят только недоступный с начала смены, а уходящий позже работает до
    ухода — снятым его покажет первое перепланирование, чьи часы до ухода дошли."""
    if "unavailable_from" not in rt:
        return False
    t = hhmm(rt["unavailable_from"])
    if plan.get("now") is None:
        shift = rt.get("shift")
        return shift is None or t <= hhmm(shift.split("–")[0].strip())
    return t <= hhmm(plan["now"])


def diff(old: dict, new: dict, cancelled: set[str] = frozenset()) -> dict:
    oi, ni = _index(old), _index(new)
    common = {rid for rid in oi if rid in ni and oi[rid]["engineer_id"] == ni[rid]["engineer_id"]}
    orank, nrank = _rank(old, common), _rank(new, common)
    reqs = {}
    for rid in sorted(set(old["assignments"]) | set(new["assignments"]) | cancelled):
        o, n = oi.get(rid), ni.get(rid)
        if rid in cancelled:
            reqs[rid] = {"status": "removed"}
        elif o is None and n is None:
            reqs[rid] = {"status": "unchanged" if rid in old["assignments"] else "newly_unassigned",
                         **({"reason": new["assignments"][rid]["reason"]["code"]} if rid in new["assignments"] else {})}
        elif o is None:
            reqs[rid] = {"status": "newly_assigned", "engineer_id": n["engineer_id"]}
        elif n is None:
            reqs[rid] = {"status": "newly_unassigned", "from": o["engineer_id"],
                         "reason": new["assignments"][rid]["reason"]["code"]}
        else:
            shift = hhmm(n["start"]) - hhmm(o["start"])
            if o["engineer_id"] != n["engineer_id"]:
                reqs[rid] = {"status": "moved", "from": o["engineer_id"], "to": n["engineer_id"], "shift_min": shift}
            elif orank[rid] != nrank[rid]:
                reqs[rid] = {"status": "reordered", "engineer_id": n["engineer_id"],
                             "from_seq": o["seq"], "to_seq": n["seq"], "shift_min": shift}
            elif abs(shift) > 5:
                reqs[rid] = {"status": "shifted", "engineer_id": n["engineer_id"], "shift_min": shift}
            else:
                reqs[rid] = {"status": "unchanged"}
    engs = {}
    okm = {rt["engineer_id"]: rt for rt in old["routes"]}
    for rt in new["routes"]:
        k = rt["engineer_id"]
        o = okm[k]
        oseq = [s["request_id"] for s in o["stops"]]
        nseq = [s["request_id"] for s in rt["stops"]]
        newly_lost = _off(new, rt) and not _off(old, o)
        status = "removed" if newly_lost else ("changed" if oseq != nseq else "unchanged")
        engs[k] = {"status": status, "delta_km": round(rt["total_km"] - o["total_km"], 1),
                   "delta_stops": len(nseq) - len(oseq)}
    counts = {}
    for v in reqs.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    summary = dict(counts, delta_total_km=round(new["metrics"]["total_km"] - old["metrics"]["total_km"], 1),
                   delta_engineers_used=new["metrics"]["engineers_used"] - old["metrics"]["engineers_used"])
    return {"requests": reqs, "engineers": engs, "summary": summary}


def unused_request(p: Problem, rid: str) -> Request:
    return p.requests[rid]

"""Артефакты объяснений (backups/docs/model.md §2.3–2.4): probe, why_assigned, why_unassigned,
plan_summary и шаблонный текст без ЛЛМ."""
from __future__ import annotations

from .compat import compat, compat_map
from .model import REASON_TEXT, Problem, fmt
from .routing import Routes, route_km, simulate


# ---------------------------------------------------------------------------
# probe: вставить заявку rid в лучшее место маршрута инженера k
# ---------------------------------------------------------------------------
def probe(p: Problem, routes: Routes, rid: str, k: str) -> dict:
    r, e = p.requests[rid], p.engineers[k]
    route = [x for x in routes.get(k, []) if x != rid]
    code = compat(p, r, e)
    if code:
        return {"engineer_id": k, "feasible": False,
                "blocker": {"code": code, "text": REASON_TEXT[code]}}
    base_km = route_km(p, e, route)
    best, fails = None, []
    for pos in range(len(route) + 1):
        cand = route[:pos] + [rid] + route[pos:]
        stops, fail = simulate(p, e, cand)
        if fail is None:
            d = route_km(p, e, cand) - base_km
            if best is None or d < best[0]:
                best = (d, pos, stops[pos])
        else:
            fails.append((pos, fail))
    if best:
        d, pos, st = best
        return {"engineer_id": k, "feasible": True, "delta_km": round(d, 1), "best_position": pos,
                "arrive": fmt(st.arrive), "start": fmt(st.start)}
    # недопустимо везде — объясняем через попытку «в хвост» и лучший конфликт в середине
    tail = next(f for pos, f in fails if pos == len(route))
    blocker = {"code": "BUSY", "conflict_request_id": None, "earliest_arrive": fmt(tail.arrive)}
    prev = route[-1] if route else None
    if tail.request_id == rid and tail.code == "WINDOW":
        after = f"после {prev} (до {fmt(simulate(p, e, route)[0][-1].finish)}) " if prev else ""
        blocker["text"] = f"{after}доедет только к {fmt(tail.arrive)}, окно закрывается в {fmt(r.tw_end)}"
    elif tail.request_id == rid:
        blocker["text"] = (f"закончил бы в {fmt(max(tail.arrive, r.tw_start) + p.service(r))}, "
                           f"смена до {fmt(e.shift_end)}")
    else:
        blocker["text"] = "маршрут инженера уже не допускает вставку"
    conflict = next((f for pos, f in fails if f.request_id != rid), None)
    if conflict:
        blocker["conflict_request_id"] = conflict.request_id
        cr = p.requests[conflict.request_id]
        blocker["text"] += (f"; если поставить раньше — {conflict.request_id} "
                            f"(окно до {fmt(cr.tw_end)}) не успеет, приедет к {fmt(conflict.arrive)}")
    return {"engineer_id": k, "feasible": False, "blocker": blocker}


# ---------------------------------------------------------------------------
def why_assigned(p: Problem, routes: Routes, rid: str, k: str) -> dict:
    r, e = p.requests[rid], p.engineers[k]
    stops, _ = simulate(p, e, routes[k])
    i = routes[k].index(rid)
    st = stops[i]
    alts = [probe(p, routes, rid, k2) for k2 in p.engineers if k2 != k]
    return {
        "constraints_ok": ["SKILL", "TRANSPORT", "WINDOW", "SHIFT"],
        "position": {"seq": i + 1, "prev_request_id": routes[k][i - 1] if i else None,
                     "next_request_id": routes[k][i + 1] if i + 1 < len(routes[k]) else None},
        "arrive": fmt(st.arrive), "start": fmt(st.start), "finish": fmt(st.finish), "wait_min": st.start - st.arrive,
        "slack_min": r.tw_end - st.start, "leg_km": round(st.leg_km, 1),
        "delta_km": round(route_km(p, e, routes[k]) - route_km(p, e, [x for x in routes[k] if x != rid]), 1),
        "alternatives": alts,
    }


def why_unassigned(p: Problem, routes: Routes, rid: str, code: str | None = None) -> dict:
    cm = compat_map(p, p.requests[rid])
    cands = [k for k, c in cm.items() if c is None]
    out = {"no_candidates": not cands, "compat": cm,
           "probes": [probe(p, routes, rid, k) for k in cands]}
    if code:
        out["code"] = code
    elif not cands:
        out["code"] = _dominant_code(cm)
    else:
        out["code"] = "BUSY"
    return out


_STAGE = ["PINNED", "SKILL", "TRANSPORT", "WINDOW_REACH", "SHIFT_FIT"]


def _dominant_code(cm: dict[str, str | None]) -> str:
    """Самая «глубокая» стадия, до которой дошёл хоть кто-то: если кто-то прошёл навык и
    транспорт, причина — время, а не навык. Нет ни одного доступного инженера — причина
    в людях, а не в заявке."""
    if not cm:
        return "ENGINEER_LOST"
    return max(cm.values(), key=_STAGE.index)


# ---------------------------------------------------------------------------
def plan_summary(plan: dict, p: Problem) -> dict:
    tight = [s["request_id"] for rt in plan["routes"] for s in rt["stops"] if s["slack_min"] < 15]
    busy = [rt["engineer_id"] for rt in plan["routes"] if rt["utilization"] > 0.85]
    skills = {}
    for s in p.dictionaries.get("skills", {}):
        demand = sum(r.skill == s for r in p.requests.values())
        supply = sum(s in e.skills for e in p.engineers.values())
        skills[s] = {"requests": demand, "engineers": supply}
    reasons = {}
    for rid in plan["unassigned"]:
        c = plan["assignments"][rid]["reason"]["code"]
        reasons[c] = reasons.get(c, 0) + 1
    return {"metrics": plan["metrics"], "bottlenecks": {"tight_requests": tight, "busy_engineers": busy,
                                                         "skills": skills, "unassigned_by_reason": reasons}}


# ---------------------------------------------------------------------------
# Шаблонный текст (обязательный fallback без ЛЛМ)
# ---------------------------------------------------------------------------
def _name(p: Problem, k: str) -> str:
    e = p.engineers[k]
    return f"{e.name} ({k})"


def _alt_text(p: Problem, pr: dict) -> str:
    who = _name(p, pr["engineer_id"])
    if pr["feasible"]:
        d = pr["delta_km"]
        return f"{who} — мог бы, но это +{d} км" if d > 0 else f"{who} — мог бы ({d:+.1f} км)"
    return f"{who} — {pr['blocker']['text']}"


def text_assigned(p: Problem, rid: str, k: str, reason: dict) -> str:
    r, e = p.requests[rid], p.engineers[k]
    skill = p.dictionaries.get("skills", {}).get(r.skill, r.skill)
    pos = reason["position"]
    parts = [f"Заявка {rid} ({r.type}, {r.district}) назначена инженеру {_name(p, k)}: "
             f"навык «{skill}» есть"]
    if r.required_transport:
        parts.append(f"транспорт «{p.dictionaries.get('transport', {}).get(e.transport, e.transport)}» подходит")
    parts.append(f"окно {fmt(r.tw_start)}–{fmt(r.tw_end)} соблюдено — прибытие {reason['arrive']}, "
                 f"начало {reason['start']}" + (f" (ожидание {reason['wait_min']} мин)" if reason["wait_min"] else "")
                 + f", запас {reason['slack_min']} мин, работа {r.duration_text} — освободится в {reason['finish']}")
    s = ", ".join(parts) + f". Это точка №{pos['seq']} маршрута"
    s += f", {reason['leg_km']} км от {pos['prev_request_id'] or 'старта'}."
    alts = reason["alternatives"]
    feas = [a for a in alts if a["feasible"]]
    infeas = [a for a in alts if not a["feasible"]]
    if feas:
        s += " Альтернативы: " + "; ".join(_alt_text(p, a) for a in sorted(feas, key=lambda a: a["delta_km"])[:3]) + "."
    else:
        s += " Других подходящих свободных инженеров нет."
    hard = [a for a in infeas if a["blocker"]["code"] in ("SKILL", "TRANSPORT")]
    busy = [a for a in infeas if a["blocker"]["code"] not in ("SKILL", "TRANSPORT")]
    if busy:
        s += " Заняты: " + "; ".join(_alt_text(p, a) for a in busy[:3]) + "."
    if hard:
        s += f" Не подходят по навыку/транспорту: {len(hard)} инж."
    return s


def text_unassigned(p: Problem, rid: str, reason: dict) -> str:
    r = p.requests[rid]
    skill = p.dictionaries.get("skills", {}).get(r.skill, r.skill)
    tr = p.dictionaries.get("transport", {}).get(r.required_transport, r.required_transport)
    head = f"Заявка {rid} ({r.type}, {r.district}, окно {fmt(r.tw_start)}–{fmt(r.tw_end)}) не назначена: "
    code = reason["code"]
    if not reason["compat"]:
        return head + "в этот день нет ни одного доступного инженера."
    if code == "ENGINEER_LOST":
        return head + "инженер стал недоступен, а у остальных нет места в окне. " + _probes_text(p, reason)
    if code == "DISPLACED":
        return head + "вытеснена срочной заявкой, свободного места у других нет. " + _probes_text(p, reason)
    pin = p.pinned.get(rid)
    if pin is not None and pin in p.engineers:
        s = head + f"закреплена за {_name(p, pin)}, но в его маршруте больше нет места в окне."
        return s + (" " + _probes_text(p, reason) if reason["probes"] else "")
    if reason["no_candidates"]:
        need = f"с навыком «{skill}»" + (f" и транспортом «{tr}»" if r.required_transport else "")
        if code == "SHIFT_FIT":
            why = f"работа {r.duration_text} не помещается ни в одну смену при окне {fmt(r.tw_start)}–{fmt(r.tw_end)}"
        elif code == "WINDOW_REACH":
            why = "никто не успевает доехать до конца окна"
        else:
            why = f"нет инженера {need}"
        groups: dict[str, list[str]] = {}
        for k, c in reason["compat"].items():
            groups.setdefault(c, []).append(p.engineers[k].name)
        by = "; ".join(f"{REASON_TEXT[c]}: {', '.join(groups[c])}" for c in _STAGE if c in groups)
        return head + why + ". По инженерам — " + by + "."
    feas = [pr for pr in reason["probes"] if pr["feasible"]]
    if feas:   # движок не оптимизирует (baseline: только в хвост) — место при перестановке есть
        return (head + "по правилу «в конец маршрута» никто не успевает; при перестановке могли бы взять: "
                + "; ".join(_alt_text(p, pr) for pr in sorted(feas, key=lambda x: x["delta_km"])[:3]) + ".")
    return head + f"все {len(reason['probes'])} подходящих инженера заняты. " + _probes_text(p, reason)


def _probes_text(p: Problem, reason: dict, limit: int = 4) -> str:
    prs = reason["probes"]
    s = "; ".join(_alt_text(p, pr) for pr in prs[:limit])
    if len(prs) > limit:
        s += f"; и ещё {len(prs) - limit} инж. аналогично"
    return s + "."

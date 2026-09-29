"""Сборка ризонинга: компактные бандлы фактов для ЛЛМ и шаблонные тексты без ЛЛМ.

Принцип: ЛЛМ получает только то, что здесь собрано. Бандл — это plan.json, отжатый до
того, что нужно для ответа на один вопрос («почему эта заявка», «что за план»,
«что изменилось»), с человекочитаемыми подписями вместо голых ID.
"""
from __future__ import annotations

from .model import REASON_TEXT, Problem
from .plan import routes_from_plan

STATUS_TEXT = {
    "moved": "переназначена", "reordered": "изменён порядок", "shifted": "сдвинуто время",
    "newly_unassigned": "снята с плана", "newly_assigned": "добавлена в план", "removed": "отменена",
}


def _eng(p: Problem, k: str) -> dict:
    e = p.engineers[k]
    return {"id": k, "name": e.name, "transport": p.dictionaries["transport"].get(e.transport, e.transport),
            "shift": f"{e.shift_start // 60:02d}:{e.shift_start % 60:02d}–{e.shift_end // 60:02d}:{e.shift_end % 60:02d}",
            "skills": [p.dictionaries["skills"].get(s, s) for s in e.skills]}


def _req(p: Problem, rid: str) -> dict:
    r = p.requests[rid]
    return {"id": rid, "type": r.type, "district": r.district, "address": r.address,
            "skill": p.dictionaries["skills"].get(r.skill, r.skill), "duration": r.duration_text,
            "window": f"{r.tw_start // 60:02d}:{r.tw_start % 60:02d}–{r.tw_end // 60:02d}:{r.tw_end % 60:02d}",
            "priority": p.dictionaries["priority"].get(r.priority, r.priority),
            "required_transport": p.dictionaries["transport"].get(r.required_transport) if r.required_transport else None}


def _probe_line(p: Problem, pr: dict, idle: set[str] = frozenset()) -> dict:
    out = {"engineer": p.engineers[pr["engineer_id"]].name, "id": pr["engineer_id"], "feasible": pr["feasible"]}
    if pr["feasible"]:
        out.update(delta_km=pr["delta_km"], would_start=pr.get("start"))
        if pr["engineer_id"] in idle:             # булев флаг mini-модели пропускают, текст — нет
            out["cost"] = "сейчас БЕЗ ЗАЯВОК: отдать ему = задействовать ещё одного инженера (+1 к главной метрике), это дороже любого пробега"
        else:
            out["cost"] = f"уже работает, добавит +{pr['delta_km']} км к своему маршруту"
    else:
        out.update(reason=pr["blocker"]["code"], detail=pr["blocker"]["text"])
    return out


# ---------------------------------------------------------------------------
def bundle_request(plan: dict, p: Problem, rid: str, top: int = 4) -> dict:
    """Факты для вопроса «почему заявка назначена так / не назначена»."""
    a = plan["assignments"][rid]
    idle = {rt["engineer_id"] for rt in plan["routes"] if not rt["stops"]}
    b = {"request": _req(p, rid)}
    if a["engineer_id"]:
        k, reason = a["engineer_id"], a["reason"]
        rt = next(r for r in plan["routes"] if r["engineer_id"] == k)
        b["assigned_to"] = _eng(p, k)
        b["locked"] = a.get("locked", False)
        if not a.get("locked"):
            pos = reason["position"]
            b["timing"] = {"arrive": reason["arrive"], "start": reason["start"], "finish": reason.get("finish"), "wait_min": reason["wait_min"],
                           "slack_min": reason["slack_min"], "leg_km": reason["leg_km"]}
            b["route_position"] = {"seq": pos["seq"], "of": len(rt["stops"]),
                                   "prev": pos["prev_request_id"], "next": pos["next_request_id"]}
            alts = reason["alternatives"]
            feas = sorted((x for x in alts if x["feasible"]), key=lambda x: x["delta_km"])
            busy = [x for x in alts if not x["feasible"] and x["blocker"]["code"] == "BUSY"]
            hard = [x for x in alts if not x["feasible"] and x["blocker"]["code"] != "BUSY"]
            b["alternatives"] = {
                "could_take": [_probe_line(p, x, idle) for x in feas[:top]],
                "busy": [_probe_line(p, x) for x in busy[:top]],
                "incompatible": {REASON_TEXT[c]: [p.engineers[x["engineer_id"]].name for x in hard if x["blocker"]["code"] == c]
                                 for c in {x["blocker"]["code"] for x in hard}},
            }
    else:
        reason = a["reason"]
        b["unassigned"] = {"code": reason["code"], "code_text": REASON_TEXT.get(reason["code"], reason["code"]),
                           "no_candidates": reason["no_candidates"]}
        groups: dict[str, list[str]] = {}
        for k, c in reason["compat"].items():
            groups.setdefault(REASON_TEXT[c] if c else "совместим", []).append(p.engineers[k].name)
        b["unassigned"]["by_engineer"] = groups
        b["unassigned"]["why_compatible_cannot"] = [_probe_line(p, x) for x in reason["probes"][:top]]
        if len(reason["probes"]) > top:
            b["unassigned"]["more_similar"] = len(reason["probes"]) - top
    b["template_text"] = a["text"]
    return b


def bundle_plan(plan: dict, p: Problem, baseline: dict | None = None) -> dict:
    """Факты для саммари плана: метрики, сравнение, нагрузка, узкие места."""
    m = plan["metrics"]
    engineers = []
    for rt in plan["routes"]:
        if not rt["stops"]:
            continue
        stops = rt["stops"]
        engineers.append({**_eng(p, rt["engineer_id"]), "stops": len(stops), "km": rt["total_km"],
                          "utilization": rt["utilization"], "first": stops[0]["start"], "last": stops[-1]["finish"],
                          "wait_min": sum(s["wait_min"] for s in stops),
                          "districts": sorted({p.requests[s["request_id"]].district for s in stops})})
    idle = [{"id": rt["engineer_id"], "name": p.engineers[rt["engineer_id"]].name} for rt in plan["routes"] if not rt["stops"]]
    unassigned = {}
    for rid in plan["unassigned"]:
        code = plan["assignments"][rid]["reason"]["code"]
        unassigned.setdefault(REASON_TEXT.get(code, code), []).append({**_req(p, rid), "template_text": plan["assignments"][rid]["text"]})
    tight = [{"id": s["request_id"], "engineer": p.engineers[rt["engineer_id"]].name, "slack_min": s["slack_min"]}
             for rt in plan["routes"] for s in rt["stops"] if s["slack_min"] < 15]
    long_legs = sorted(({"to": s["request_id"], "engineer": p.engineers[rt["engineer_id"]].name, "leg_km": s["leg_km"]}
                        for rt in plan["routes"] for s in rt["stops"]), key=lambda x: -x["leg_km"])[:3]
    skills = {}
    for s, label in p.dictionaries["skills"].items():
        skills[label] = {"requests": sum(r.skill == s for r in p.requests.values()),
                         "engineers": sum(s in e.skills for e in p.engineers.values())}
    b = {"engine": plan["engine"], "metrics": {k: v for k, v in m.items() if k != "km_per_engineer"},
         "engineers": engineers, "idle_engineers": idle, "unassigned_by_reason": unassigned,
         "bottlenecks": {"tight_windows": tight, "longest_legs": long_legs, "skill_supply": skills}}
    if baseline:
        bm = baseline["metrics"]
        b["vs_baseline"] = {"baseline": "заявки по порядку поступления первому подходящему инженеру, в конец маршрута (ТЗ §2.3)",
                            "engineers_used": [bm["engineers_used"], m["engineers_used"]],
                            "assigned": [bm["assigned"], m["assigned"]],
                            "total_km": [bm["total_km"], m["total_km"]]}
    return b


def bundle_diff(plan: dict, p: Problem) -> dict:
    """Факты для объяснения перепланирования: события, что заморожено, что изменилось и почему."""
    d = plan["diff"]
    events = []
    for ev in plan["events"]:
        t = ev["type"]
        if t == "urgent_request":
            events.append({"type": "срочная заявка", "time": ev["time"], "request": _req(p, ev["request"]["id"])})
        elif t == "cancel_request":
            events.append({"type": "отмена заявки", "time": ev["time"], "request_id": ev["request_id"]})
        elif t == "new_request":
            events.append({"type": "новая заявка", "time": ev["time"], "request_id": ev["request_id"]})
        elif t == "move_request":
            events.append({"type": "перенос заявки", "time": ev["time"], "request_id": ev["request_id"],
                           "engineer": _eng(p, ev["engineer_id"])})
        elif t == "engineer_break":
            events.append({"type": "перерыв", "time": ev["time"], "until": ev["until"], "engineer": _eng(p, ev["engineer_id"])})
        else:
            events.append({"type": "инженер недоступен", "time": ev["time"], "engineer": _eng(p, ev["engineer_id"]),
                           "finishes_current": ev.get("finish_current", True)})
    changes: dict[str, list] = {}
    for rid, v in d["requests"].items():
        if v["status"] == "unchanged":
            continue
        item = {"id": rid, **{k: x for k, x in v.items() if k != "status"}}
        if v["status"] in ("moved",):
            item["from"], item["to"] = p.engineers[v["from"]].name, p.engineers[v["to"]].name
        if v["status"] == "newly_unassigned":
            item["reason_text"] = REASON_TEXT.get(v.get("reason", ""), v.get("reason"))
            item["template_text"] = plan["assignments"].get(rid, {}).get("text")
        if v["status"] == "newly_assigned":
            item["engineer"] = p.engineers[v["engineer_id"]].name
        changes.setdefault(STATUS_TEXT[v["status"]], []).append(item)
    locked = sum(1 for rt in plan["routes"] for s in rt["stops"] if s["locked"])
    return {"now": plan["now"], "stability_mode": plan.get("stability"), "events": events,
            "frozen_stops": locked, "changes": changes,
            "engineers_changed": {p.engineers[k].name: v for k, v in d["engineers"].items() if v["status"] != "unchanged"},
            "summary": d["summary"], "metrics_after": {k: v for k, v in plan["metrics"].items() if k != "km_per_engineer"}}


# ---------------------------------------------------------------------------
# Шаблонные тексты (fallback без ЛЛМ)
# ---------------------------------------------------------------------------
def template_summary(b: dict) -> str:
    m = b["metrics"]
    s = (f"План ({b['engine']}): назначено {m['assigned']} заявок, не назначено {m['unassigned']}, "
         f"задействовано {m['engineers_used']} из {m['engineers_total']} инженеров, суммарный пробег {m['total_km']} км.")
    if "vs_baseline" in b:
        v = b["vs_baseline"]
        s += (f" Базовый вариант: {v['assigned'][0]} заявок, {v['engineers_used'][0]} инженеров, {v['total_km'][0]} км — "
              f"выигрыш {v['assigned'][1] - v['assigned'][0]:+d} заявок, {v['engineers_used'][1] - v['engineers_used'][0]:+d} инженеров, "
              f"{v['total_km'][1] - v['total_km'][0]:+.1f} км.")
    if b["idle_engineers"]:
        s += f" Без заявок: {', '.join(e['name'] for e in b['idle_engineers'])}."
    for reason, items in b["unassigned_by_reason"].items():
        s += f" Не назначены ({reason}): {', '.join(x['id'] for x in items)}."
    top = sorted(b["engineers"], key=lambda e: -e["utilization"])[:2]
    s += " Самые загруженные: " + ", ".join(f"{e['name']} ({int(e['utilization'] * 100)} %, {e['km']} км)" for e in top) + "."
    return s


def template_diff(b: dict) -> str:
    ev = "; ".join(f"{e['type']} в {e['time']}" + (f" ({e['engineer']['name']})" if "engineer" in e else "")
                   + (f" ({e['request']['id']})" if "request" in e else "") + (f" ({e['request_id']})" if "request_id" in e else "")
                   for e in b["events"])
    s = f"Перепланирование на {b['now']}: {ev}. Заморожено {b['frozen_stops']} выполняемых/выполненных заявок."
    for status, items in b["changes"].items():
        s += f" {status.capitalize()}: " + ", ".join(
            x["id"] + (f" ({x['from']} → {x['to']})" if "to" in x else "") + (f" — {x['reason_text']}" if "reason_text" in x else "")
            for x in items) + "."
    sm = b["summary"]
    s += f" Итог: пробег {sm['delta_total_km']:+.1f} км, инженеров {sm['delta_engineers_used']:+d}."
    return s

"""Варианты плана на весь день: базовый (по порядку поступления) и три запаса.
Ничего не утверждают — утверждение отдельным запросом."""
from __future__ import annotations

import time

from . import planning, scenarios, store
from .schema import MARGIN_LABEL, MARGINS, Settings

DESC = {"baseline": "по порядку, первому подходящему", "econom": "без запаса"}


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def recommend(rows: list[dict], threshold: float) -> str:
    """Терпимо к отсутствию оценки риска (expected_late=None у любой строки): такие строки
    не выбираются, пока есть строка с оценкой, но не роняют расчёт."""
    cand = [r for r in rows if r["key"] != "baseline"]
    top = max(r["assigned"] for r in cand)
    cand = [r for r in cand if r["assigned"] == top]
    ok = [r for r in cand if r["expected_late"] is not None and r["expected_late"] <= threshold]
    if not ok:
        return min(cand, key=lambda r: (r["expected_late"] is None, r["expected_late"] or 0))["key"]
    return min(ok, key=lambda r: (r["engineers_used"], r["total_km"]))["key"]


def insight(rows: list[dict], rec: str) -> str:
    """Терпимо к отсутствию оценки риска: «оценки опозданий нет» вместо числа, сравнение
    с более экономным вариантом — только когда обе оценки есть."""
    by = {r["key"]: r for r in rows}
    r, b = by[rec], by["baseline"]
    clauses = []
    d_eng = b["engineers_used"] - r["engineers_used"]
    if d_eng > 0:
        clauses.append(f"на {d_eng} меньше")
    d_km = round(b["total_km"] - r["total_km"])
    if d_km > 0:
        clauses.append(f"на {d_km} км короче")
    head = f"«{r['name']}» назначает {r['assigned']} из {r['total']} на {r['engineers_used']} инженерах"
    head += (" — " + " и ".join(clauses) + " базового.") if clauses else "."
    late = ("оценки опозданий нет." if r["expected_late"] is None
            else f"Ожидаемо {_num(r['expected_late'])} опоздания за день.")
    s = f"{head} {late}"
    fewer = [x for x in rows if x["key"] not in ("baseline", rec) and x["engineers_used"] < r["engineers_used"]]
    if fewer and r["expected_late"] not in (None, 0):
        x = min(fewer, key=lambda x: x["engineers_used"])
        if x["expected_late"] is not None:
            k = round(x["expected_late"] / r["expected_late"])
            if k >= 2:
                d = r["engineers_used"] - x["engineers_used"]
                word = "одного" if d == 1 else str(d)
                s += f" «{x['name']}» освобождает ещё {word}, но опозданий станет в {k} раза больше."
    return s


def _row(key: str, plan: dict) -> dict:
    m, risk = plan["metrics"], plan.get("risk")
    return {"key": key, "name": "Базовый" if key == "baseline" else MARGIN_LABEL[key],
            "desc": DESC.get(key) or f"запас {MARGINS[key][0]} %", "plan_id": plan["plan_id"],
            "assigned": m["assigned"], "total": m["assigned"] + m["unassigned"],
            "engineers_used": m["engineers_used"], "engineers_total": m["engineers_total"], "total_km": m["total_km"],
            "expected_late": risk["stress"]["expected_late"] if risk else None,
            "overtime_min": round(risk["stress"]["expected_overtime_min"]) if risk else None}


def compute(con, sid: str) -> dict:
    s = store.session(con, sid)
    st = Settings(**s["settings"])
    run = store.new_id()
    based_on = s["plan_id"]                                  # каким расписанием были вводные на момент расчёта
    queued = [e["id"] for e in store.events(con, sid, pending_only=True)]   # что видят варианты
    t0 = time.time()
    rows, saves = [], []
    budget = max(1.0, st.time_limit / 3)
    for key in ("baseline", "econom", "balanced", "reliable"):
        w, t, m = MARGINS.get(key, MARGINS["econom"])
        vs = st.model_copy(update={"work_pct": w, "travel_pct": t, "travel_min": m,
                                   "margin": "econom" if key == "baseline" else key, "time_limit": budget})
        plan = planning.solve_whole_day(con, sid, vs, engine="baseline" if key == "baseline" else None)
        plan["accepted"], plan["accepted_at"] = False, None
        params = {**vs.model_dump(), "run_id": run, "variant": key, "events": queued, "based_on": based_on,
                  "variant_label": "Базовый" if key == "baseline" else MARGIN_LABEL[key]}
        saves.append((plan, params))
        rows.append(_row(key, plan))
    with store.tx(con):                                       # все четыре варианта — одной транзакцией
        for plan, params in saves:
            store.save_plan(con, sid, plan, "variant", params, risk=plan["risk"])
    thr = scenarios.load(s["scenario"])["config"]["robustness"]["risk"].get("late_threshold", 0.5)
    rec = recommend(rows, thr)
    return {"run_id": run, "elapsed_s": round(time.time() - t0, 1), "variants": rows, "recommended": rec,
            "text": insight(rows, rec)}


def latest(con, sid: str) -> dict | None:
    got = store.plans_of(con, sid, "variant")
    if not got:
        return None
    run = got[0][1]["run_id"]
    rows = [(_row(pa["variant"], doc), pa) for doc, pa, _ in reversed(got) if pa["run_id"] == run]
    order = ["baseline", "econom", "balanced", "reliable"]
    rows = sorted((r for r, _ in rows), key=lambda r: order.index(r["key"]))
    s = store.session(con, sid)
    thr = scenarios.load(s["scenario"])["config"]["robustness"]["risk"].get("late_threshold", 0.5)
    rec = recommend(rows, thr)
    return {"run_id": run, "elapsed_s": None, "variants": rows, "recommended": rec, "text": insight(rows, rec)}


def approve(con, sid: str, plan_id: str) -> None:
    got = store.plans_of(con, sid, "variant")
    run = got[0][1]["run_id"] if got else None
    hit = next(((doc, pa) for doc, pa, _ in got if doc["plan_id"] == plan_id), None)
    if hit is None or hit[1]["run_id"] != run:
        raise ValueError("варианты пересчитаны — выберите из новых")
    doc, params = hit
    s = store.session(con, sid)
    if s["plan_id"] != params.get("based_on"):
        raise ValueError("расписание изменилось после расчёта вариантов — пересчитайте")
    doc["accepted"], doc["accepted_at"] = True, time.time()
    # запас варианта — в настройки сессии; time_limit, engine, priority, warm_start — не трогаем
    st = Settings(**s["settings"]).model_copy(update={"work_pct": params["work_pct"],
                                                       "travel_pct": params["travel_pct"],
                                                       "travel_min": params["travel_min"],
                                                       "margin": params["margin"]})
    open_ids = {e["id"] for e in store.events(con, sid, pending_only=True)}
    seen = [x for x in params["events"] if x in open_ids]     # пришедшее после расчёта вариант не видел
    with store.tx(con):
        store.update_plan(con, sid, doc)
        store.set_settings(con, sid, st.model_dump())
        store.set_plan(con, sid, plan_id)
        store.mark_events_applied(con, sid, plan_id, seen)

"""Правила справочников сессии: как заводится новая заявка и как выводится состояние
существующих. Роутер этим не занимается — он принимает запрос и отдаёт ответ."""
from __future__ import annotations

from planner.model import fmt, hhmm

from . import scenarios, store
from .schema import NewRequest

REQUEST_EVENTS = ("new_request", "urgent_request", "cancel_request", "move_request")
SKILL_OF = {"connect_base": "connect", "equipment": "connect", "local_repair": "local", "emergency": "emergency"}


def _event_request(ev: dict) -> str | None:
    return ev["request"]["id"] if ev["type"] == "urgent_request" else ev.get("request_id")


def assignments(con, sid: str) -> dict[str, str | None]:
    """Кто какую заявку получил в текущем плане. Пусто, если плана ещё нет."""
    s = store.session(con, sid)
    if not s["plan_id"]:
        return {}
    plan = store.plan(con, sid, s["plan_id"])[0]
    return {rid: a["engineer_id"] for rid, a in plan["assignments"].items()}


def next_request_id(existing: list[dict]) -> str:
    """Номер заводимой заявки: следующий за длиной списка, с обходом уже занятых."""
    taken = {r["id"] for r in existing}
    n = len(existing) + 1
    while f"R{n:03d}" in taken:
        n += 1
    return f"R{n:03d}"


def draft_request(con, sid: str, body: NewRequest, rid: str) -> dict:
    """Заявка со сроком работы по нормативу сценария. В базу не пишет."""
    norms = scenarios.load(store.session(con, sid)["scenario"])["dictionaries"]["norms"]
    n = norms[body.work_type]
    return {**body.model_dump(), "id": rid, "duration_min": n["tech_min"] + n["docs_min"]}


def new_request(con, sid: str, body: NewRequest) -> dict:
    """Заявка со следующим свободным номером. Событие пишет вызывающий."""
    return draft_request(con, sid, body, next_request_id(store.requests(con, sid)))


def cancelled_ids(con, sid: str, pending_too: bool) -> set[str]:
    """Заявки с принятой отменой; с pending_too — и с отменой в очереди."""
    open_ids = {e["id"] for e in store.events(con, sid, pending_only=True)}
    return {e["request_id"] for e in store.events(con, sid)
            if e["type"] == "cancel_request" and (pending_too or e["id"] not in open_ids)}


def drop_event(con, sid: str, event_id: str) -> None:
    """Убрать событие из очереди. Вызывать внутри транзакции. Заведённую событием заявку — тоже,
    и все непринятые события, ссылающиеся на неё (иначе освобождённый номер заявки унаследует
    следующая новая заявка вместе с чужой отменой или переносом)."""
    st = store.event_state(con, sid, event_id)
    if st is None:
        raise LookupError(event_id)
    if st != "pending":
        raise PermissionError(event_id)
    ev = next(e for e in store.events(con, sid, pending_only=True) if e["id"] == event_id)
    if ev["type"] in ("new_request", "urgent_request"):
        rid = _event_request(ev)
        store.delete_request(con, sid, rid)
        for other in store.events(con, sid, pending_only=True):
            if other["id"] != event_id and _event_request(other) == rid:
                store.delete_event(con, sid, other["id"])
    store.delete_event(con, sid, event_id)


def with_status(con, sid: str) -> list[dict]:
    """Заявки сессии с тем, кому они достались: new — план её ещё не рассматривал
    (плана нет или заявка заведена после него), unassigned — рассмотрел и не назначил,
    cancelled — отмена принята перепланированием. by_dispatcher — заявки нет в файле
    сценария: время в пути до неё — оценка по прямой. pending — какие непринятые
    события на неё ссылаются."""
    s = store.session(con, sid)
    got = assignments(con, sid)
    base = {r["id"] for r in scenarios.load(s["scenario"])["requests"]}
    open_ids = {e["id"] for e in store.events(con, sid, pending_only=True)}
    pending: dict[str, list[str]] = {}
    cancelled: set[str] = set()
    for ev in store.events(con, sid):
        if ev["type"] not in REQUEST_EVENTS:
            continue
        rid = _event_request(ev)
        if ev["id"] in open_ids:
            pending.setdefault(rid, []).append(ev["type"])
        elif ev["type"] == "cancel_request":
            cancelled.add(rid)
    out = []
    for r in store.requests(con, sid):
        who = got.get(r["id"])
        st = "cancelled" if r["id"] in cancelled else (
            "new" if r["id"] not in got else ("assigned" if who else "unassigned"))
        out.append({**r, "assigned_to": who, "by_dispatcher": r["id"] not in base,
                    "pending": pending.get(r["id"], []), "status": st})
    return out


def form_catalog(con, sid: str) -> dict:
    """Всё, что нужно форме новой заявки: из чего выбирать и чем подставлять координаты."""
    ds = scenarios.load(store.session(con, sid)["scenario"])
    norms = ds["dictionaries"]["norms"]
    types, seen = [], set()
    for r in ds["requests"]:
        k = (r["type"], r["work_type"])
        if k not in seen:
            seen.add(k)
            types.append({"type": r["type"], "work_type": r["work_type"], "skill": SKILL_OF[r["work_type"]]})
    for wt, n in norms.items():
        if not any(t["work_type"] == wt for t in types):
            types.append({"type": n["label"], "work_type": wt, "skill": SKILL_OF[wt]})
    by: dict[str, list[tuple[float, float]]] = {}
    for r in ds["requests"]:
        if r.get("district"):
            by.setdefault(r["district"], []).append((r["lat"], r["lon"]))
    districts = [{"name": k, "lat": round(sum(p[0] for p in v) / len(v), 5),
                  "lon": round(sum(p[1] for p in v) / len(v), 5)} for k, v in sorted(by.items())]
    starts = [hhmm(e["shift_start"]) for e in ds["engineers"]]
    ends = [hhmm(e["shift_end"]) for e in ds["engineers"]]
    return {"types": types, "districts": districts, "norms": norms,
            "skills": ds["dictionaries"]["skills"], "transport": ds["dictionaries"]["transport"],
            "date": ds.get("meta", {}).get("date"), "day": [fmt(min(starts)), fmt(max(ends))]}

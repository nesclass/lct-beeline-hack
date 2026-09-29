"""Справочники сессии и действия, которые делают её требующей перепланирования."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from planner.model import fmt, hhmm

from .. import catalog, session, state, store, whatif
from ..geo.geocode import geocode
from ..schema import NewRequest, Unavailable
from .sessions import require

router = APIRouter(prefix="/api/sessions")


@router.get("/{sid}/engineers")
def engineers(sid: str):
    con = state.con()
    require(sid)
    lost: dict[str, str] = {}
    for e in store.events(con, sid):
        if e["type"] == "engineer_unavailable":
            k = e["engineer_id"]
            lost[k] = min(lost.get(k, e["time"]), e["time"], key=hhmm)
    return [{**e, "unavailable_from": lost.get(e["id"])} for e in store.engineers(con, sid)]


def _replace(con, sid: str, event_id: str | None, allowed: tuple[str, ...], eid: str | None = None) -> None:
    """Заменить непринятое событие: только того же рода (и, для недоступности, того же
    инженера) — иначе диспетчер случайно снял бы что-то совсем другое из очереди."""
    if not event_id:
        return
    st = store.event_state(con, sid, event_id)
    if st is None:
        raise HTTPException(404, "нет такого события")
    if st != "pending":
        raise HTTPException(409, "событие уже учтено в расписании — изменить его нельзя")
    ev = next(e for e in store.events(con, sid, pending_only=True) if e["id"] == event_id)
    if ev["type"] not in allowed or (eid is not None and ev.get("engineer_id") != eid):
        raise HTTPException(409, "это событие так заменить нельзя")
    catalog.drop_event(con, sid, event_id)


@router.post("/{sid}/engineers/{eid}/unavailable")
def unavailable(sid: str, eid: str, body: Unavailable = Unavailable(), replace: str | None = None):
    con = state.con()
    with state.lock:
        s = require(sid)
        if not any(e["id"] == eid for e in store.engineers(con, sid)):
            raise HTTPException(404, "нет такого инженера")
        try:
            ev = whatif.unavailable_event(con, sid, eid, body)
        except ValueError as e:
            raise HTTPException(409, str(e))
        with store.tx(con):
            _replace(con, sid, replace, ("engineer_unavailable", "engineer_break"), eid=eid)
            store.add_event(con, sid, {**ev, "at": fmt(s["clock_min"])})
        return session.brief(con, sid)


@router.get("/{sid}/requests")
def requests(sid: str):
    require(sid)
    return catalog.with_status(state.con(), sid)


@router.post("/{sid}/requests")
def add_request(sid: str, body: NewRequest, replace: str | None = None):
    con = state.con()
    at = geocode(body.address)                  # до замка: сеть не должна держать расчёты
    if at is not None:
        body = body.model_copy(update={"lat": at[0], "lon": at[1]})
    with state.lock:
        s = require(sid)
        with store.tx(con):
            _replace(con, sid, replace, ("new_request", "urgent_request"))
            doc = catalog.new_request(con, sid, body)
            store.put_request(con, sid, doc)
            if body.priority == "urgent":
                store.add_event(con, sid, {"type": "urgent_request", "time": fmt(s["clock_min"]),
                                           "at": fmt(s["clock_min"]), "request": doc})
            else:
                store.add_event(con, sid, {"type": "new_request", "time": fmt(s["clock_min"]),
                                           "at": fmt(s["clock_min"]), "request_id": doc["id"]})
        return {"request": doc, "session": session.brief(con, sid)}


@router.get("/{sid}/catalog")
def form_catalog(sid: str):
    require(sid)
    return catalog.form_catalog(state.con(), sid)

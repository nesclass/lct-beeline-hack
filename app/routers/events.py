"""Очередь изменений: отмена, перенос, удаление непринятого, «если оставить как есть»."""
from fastapi import APIRouter, HTTPException

from planner.model import fmt

from .. import catalog, session, state, store, whatif
from ..schema import Cancel, Move
from .planning import with_plan
from .sessions import require

router = APIRouter(prefix="/api/sessions")


def _request(con, sid: str, rid: str) -> dict:
    r = next((x for x in store.requests(con, sid) if x["id"] == rid), None)
    if r is None:
        raise HTTPException(404, "нет такой заявки")
    return r


@router.post("/{sid}/requests/{rid}/cancel")
def cancel(sid: str, rid: str, body: Cancel = Cancel()):
    con = state.con()
    with state.lock:
        s = require(sid)
        _request(con, sid, rid)
        if rid in catalog.cancelled_ids(con, sid, pending_too=True):
            raise HTTPException(409, "отмена этой заявки уже в очереди или принята")
        now = fmt(s["clock_min"])
        with store.tx(con):
            store.add_event(con, sid, {"type": "cancel_request", "time": now, "at": now,
                                       "request_id": rid, "reason": body.reason})
        return session.brief(con, sid)


@router.post("/{sid}/requests/{rid}/move")
def move(sid: str, rid: str, body: Move):
    con = state.con()
    with state.lock:
        s = with_plan(sid)
        _request(con, sid, rid)
        if not any(e["id"] == body.engineer_id for e in store.engineers(con, sid)):
            raise HTTPException(404, "нет такого инженера")
        if rid in catalog.cancelled_ids(con, sid, pending_too=True):
            raise HTTPException(409, "заявка отменена")
        why = whatif.check_move(con, sid, rid, body.engineer_id)
        if why:
            raise HTTPException(409, why)
        owner = store.plan(con, sid, s["plan_id"])[0]["assignments"].get(rid, {}).get("engineer_id")
        now = fmt(s["clock_min"])
        with store.tx(con):
            for ev in store.events(con, sid, pending_only=True):
                if ev["type"] == "move_request" and ev["request_id"] == rid:
                    store.delete_event(con, sid, ev["id"])
            store.add_event(con, sid, {"type": "move_request", "time": now, "at": now, "request_id": rid,
                                       "engineer_id": body.engineer_id, "from": owner})
        return session.brief(con, sid)


@router.delete("/{sid}/events/{eid}")
def delete(sid: str, eid: str):
    con = state.con()
    with state.lock:
        require(sid)
        try:
            with store.tx(con):
                catalog.drop_event(con, sid, eid)
        except LookupError:
            raise HTTPException(404, "нет такого события")
        except PermissionError:
            raise HTTPException(409, "событие уже учтено в расписании — убрать его нельзя")
        return session.brief(con, sid)


@router.get("/{sid}/impact")
def impact(sid: str):
    with_plan(sid)
    return whatif.impact(state.con(), sid)

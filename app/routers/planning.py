from fastapi import APIRouter, HTTPException

from .. import planning, session, state, store
from ..schema import ReplanBody
from .sessions import require

router = APIRouter(prefix="/api/sessions")


def with_plan(sid: str) -> dict:
    s = require(sid)
    if not s["plan_id"]:
        raise HTTPException(409, "сначала постройте базовое расписание")
    return s


@router.post("/{sid}/plan")
def build(sid: str):
    require(sid)
    with state.lock:
        s = require(sid)
        if s["plan_id"]:
            plan = store.plan(state.con(), sid, s["plan_id"])[0]
            if not plan.get("accepted", True):
                raise HTTPException(409, "сначала примите или откатите перепланирование")
            if plan["replan_of"]:
                raise HTTPException(409, "день уже перепланирован — пересборка с нуля выбросит сделанное; "
                                         "начните новую сессию")
            if session.day_started(state.con(), sid):
                raise HTTPException(409, session.DAY_STARTED)
        return planning.build(state.con(), sid)


@router.get("/{sid}/plan")
def view(sid: str):
    with_plan(sid)
    return planning.view(state.con(), sid)


@router.post("/{sid}/replan")
def replan(sid: str, body: ReplanBody = ReplanBody()):
    with_plan(sid)
    with state.lock:
        if not store.events(state.con(), sid, pending_only=True):
            raise HTTPException(409, "вводные не менялись — перепланировать нечего")
        return planning.replan_now(state.con(), sid, body.mode)


@router.post("/{sid}/plan/accept")
def accept(sid: str):
    with_plan(sid)
    with state.lock:
        try:
            return planning.accept(state.con(), sid)
        except ValueError as e:
            raise HTTPException(409, str(e))


@router.post("/{sid}/plan/rollback")
def rollback(sid: str):
    with_plan(sid)
    with state.lock:
        try:
            planning.rollback(state.con(), sid)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return session.brief(state.con(), sid)


@router.get("/{sid}/history")
def history(sid: str):
    with_plan(sid)
    return planning.history(state.con(), sid)


@router.get("/{sid}/explain/{rid}")
def explain(sid: str, rid: str):
    s = with_plan(sid)
    plan = store.plan(state.con(), sid, s["plan_id"])[0]
    a = plan["assignments"].get(rid)
    if a is None:
        raise HTTPException(404, "нет такой заявки в этом плане")
    return {"request_id": rid, "engineer_id": a["engineer_id"], "text": a["text"], "reason": a["reason"]}

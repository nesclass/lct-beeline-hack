from fastapi import APIRouter, HTTPException

from .. import session, state, store, variants
from .sessions import require

router = APIRouter(prefix="/api/sessions")


def _day_not_started(sid: str) -> None:
    s = require(sid)
    if s["plan_id"]:
        plan = store.plan(state.con(), sid, s["plan_id"])[0]
        if plan.get("replan_of") or not plan.get("accepted", True):
            raise HTTPException(409, "день уже перепланирован — варианты на весь день больше не строятся")
        if session.day_started(state.con(), sid):
            raise HTTPException(409, session.DAY_STARTED)


@router.post("/{sid}/variants")
def compute(sid: str):
    with state.lock:
        _day_not_started(sid)
        return variants.compute(state.con(), sid)


@router.get("/{sid}/variants")
def latest(sid: str):
    require(sid)
    got = variants.latest(state.con(), sid)
    if got is None:
        raise HTTPException(404, "варианты ещё не считались")
    return got


@router.post("/{sid}/variants/{pid}/approve")
def approve(sid: str, pid: str):
    with state.lock:
        _day_not_started(sid)
        try:
            variants.approve(state.con(), sid, pid)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return session.brief(state.con(), sid)

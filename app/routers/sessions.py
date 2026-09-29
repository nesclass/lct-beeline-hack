from fastapi import APIRouter, HTTPException

from planner.model import hhmm

from .. import session, state, store
from ..schema import Clock, NewSession, Settings

router = APIRouter(prefix="/api/sessions")


def require(sid: str) -> dict:
    s = store.session(state.con(), sid)
    if not s:
        raise HTTPException(404, "нет такой сессии")
    return s


@router.post("")
def create(body: NewSession):
    with state.lock:
        try:
            sid = session.create(state.con(), body.scenario)
        except KeyError:
            raise HTTPException(404, f"нет такого сценария: {body.scenario}")
        return {"session_id": sid}


@router.get("")
def listing():
    con = state.con()
    out = []
    for s in store.list_sessions(con):
        try:
            b = session.brief(con, s["id"])
        except KeyError:                       # сценарий сессии удалён с диска — сессию не показываем
            continue
        out.append({"session_id": s["id"], "scenario": s["scenario"], "title": b["title"], "clock": b["clock"],
                    "status": b["status"], "pending": len(b["pending_events"]),
                    "created_at": s["created_at"], "updated_at": s["updated_at"]})
    return out


@router.get("/{sid}")
def brief(sid: str):
    require(sid)
    return session.brief(state.con(), sid)


@router.get("/{sid}/settings", response_model=Settings)
def get_settings(sid: str):
    return Settings(**require(sid)["settings"])


@router.put("/{sid}/settings", response_model=Settings)
def put_settings(sid: str, body: Settings):
    with state.lock:
        require(sid)
        with store.tx(state.con()):
            store.set_settings(state.con(), sid, body.model_dump())
        return body


@router.put("/{sid}/clock")
def put_clock(sid: str, body: Clock):
    with state.lock:
        s = require(sid)
        minutes = hhmm(body.time)
        # перепланирование заморозило сделанное к своему now; часы раньше разморозили бы его
        now = store.plan(state.con(), sid, s["plan_id"])[0]["now"] if s["plan_id"] else None
        if now is not None and minutes < hhmm(now):
            raise HTTPException(409, f"расписание уже перепланировано на {now} — часы раньше этого не ставятся")
        with store.tx(state.con()):
            store.set_clock(state.con(), sid, minutes)
        return session.brief(state.con(), sid)

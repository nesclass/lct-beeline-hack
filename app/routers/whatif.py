from fastapi import APIRouter, HTTPException

from .. import state, store, whatif
from ..schema import NewRequest, Unavailable
from .planning import with_plan
from .sessions import require

router = APIRouter(prefix="/api/sessions")


@router.post("/{sid}/preview/request")
def preview_request(sid: str, body: NewRequest):
    require(sid)
    return whatif.request_candidates(state.con(), sid, body)


@router.post("/{sid}/preview/unavailable/{eid}")
def preview_unavailable(sid: str, eid: str, body: Unavailable = Unavailable()):
    with_plan(sid)
    if not any(e["id"] == eid for e in store.engineers(state.con(), sid)):
        raise HTTPException(404, "нет такого инженера")
    try:
        return whatif.unavailable_preview(state.con(), sid, eid, body)
    except ValueError as e:
        raise HTTPException(409, str(e))

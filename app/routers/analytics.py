from fastapi import APIRouter

from .. import analytics, state
from .planning import with_plan

router = APIRouter(prefix="/api/sessions")


@router.get("/{sid}/analytics")
def report(sid: str):
    with_plan(sid)
    return analytics.report(state.con(), sid)

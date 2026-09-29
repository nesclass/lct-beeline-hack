from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .. import assistant, state, store
from ..schema import AskBody, Unavailable
from .planning import with_plan
from .sessions import require

router = APIRouter(prefix="/api/sessions")


@router.post("/{sid}/assistant")
def ask(sid: str, body: AskBody):
    ctx = body.context.model_dump()
    if ctx["kind"] == "variants":
        require(sid)
    else:
        with_plan(sid)
    if ctx["kind"] in ("request", "engineer") and not ctx.get("id"):
        raise HTTPException(422, "в контексте нужен id заявки или инженера")
    con = state.con()
    if ctx["kind"] == "engineer":
        if not any(e["id"] == ctx["id"] for e in store.engineers(con, sid)):
            raise HTTPException(404, "нет такого инженера")
        try:
            Unavailable(**(ctx.get("params") or {}))
        except ValidationError as e:
            raise HTTPException(422, str(e))
    if ctx["kind"] == "request":
        if not any(r["id"] == ctx["id"] for r in store.requests(con, sid)):
            raise HTTPException(404, "нет такой заявки")
    return assistant.ask(con, sid, ctx, body.question, body.history)

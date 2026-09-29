"""Матрица совместимости C_ik с кодами причин (backups/docs/model.md §1.2)."""
from __future__ import annotations

from .model import Engineer, Problem, Request


def compat(p: Problem, r: Request, e: Engineer) -> str | None:
    """None — совместимы; иначе ReasonCode: PINNED | SKILL | TRANSPORT | WINDOW_REACH | SHIFT_FIT."""
    pin = p.pinned.get(r.id)
    if pin is not None and pin != e.id:
        return "PINNED"
    if r.skill not in e.skills:
        return "SKILL"
    if r.required_transport and r.required_transport != e.transport:
        return "TRANSPORT"
    arrive = e.available_from + p.travel(e.start_node, r.id, e.transport)
    start = max(arrive, r.tw_start)
    if start > r.tw_end:
        return "WINDOW_REACH"
    if start + p.service(r) > e.shift_end:
        return "SHIFT_FIT"
    return None


def compat_map(p: Problem, r: Request) -> dict[str, str | None]:
    return {e.id: compat(p, r, e) for e in p.engineers.values()}


def candidates(p: Problem, r: Request) -> list[str]:
    return [e.id for e in p.engineers.values() if compat(p, r, e) is None]

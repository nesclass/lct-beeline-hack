"""Жизненный цикл сессии: создание из сценария, состояние, часы.

Состояние не хранится: оно выводится из наличия плана и непринятых событий.
"""
from __future__ import annotations

from planner.model import fmt, hhmm

from . import scenarios, store
from .schema import Settings


DAY_STARTED = "день уже начался — варианты и пересборка на весь день недоступны; используйте перепланирование"


def start_of_day(ds: dict) -> int:
    return min(hhmm(e["shift_start"]) for e in ds["engineers"])


def create(con, scenario: str) -> str:
    """Копия сценария в новой сессии. События сценария не копируются — их создаёт диспетчер."""
    ds = scenarios.load(scenario)
    sid = store.new_id()
    with store.tx(con):
        store.create_session(con, sid, scenario, start_of_day(ds), Settings().model_dump())
        for e in ds["engineers"]:
            store.put_engineer(con, sid, e)
        for r in ds["requests"]:
            store.put_request(con, sid, r)
    return sid


def status(con, sid: str) -> str:
    s = store.session(con, sid)
    if not s or not s["plan_id"]:
        return "new"
    if store.events(con, sid, pending_only=True):
        return "dirty"
    return "planned" if store.plan(con, sid, s["plan_id"])[0].get("accepted", True) else "draft"


def day_started(con, sid: str) -> bool:
    """День начался: в текущем плане есть работа, начало которой уже наступило по часам сессии.
    После этого план на весь день (варианты, пересборка) переписал бы сделанное — только
    перепланирование."""
    s = store.session(con, sid)
    if not s or not s["plan_id"]:
        return False
    plan = store.plan(con, sid, s["plan_id"])[0]
    return any(hhmm(st["start"]) <= s["clock_min"] for rt in plan["routes"] for st in rt["stops"])


def brief(con, sid: str) -> dict:
    s = store.session(con, sid)
    meta = scenarios.load(s["scenario"])
    return {"session_id": sid, "scenario": s["scenario"], "title": meta["title"],
            "clock": fmt(s["clock_min"]), "clock_min": s["clock_min"],
            "status": status(con, sid), "plan_id": s["plan_id"], "day_started": day_started(con, sid),
            "pending_events": store.events(con, sid, pending_only=True),
            "counts": {"engineers": len(store.engineers(con, sid)),
                       "requests": len(store.requests(con, sid))}}

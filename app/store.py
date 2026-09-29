"""Слой данных приложения. Единственное место, где есть SQL.

Все сущности лежат в одной базе и разделены колонкой session_id. Поэтому каждая функция
принимает sid: фильтр по сессии нельзя забыть, потому что писать WHERE снаружи негде.
Документы хранятся как JSON — схемы ещё двигаются, ORM тут только мешал бы.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "out" / "app.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions  (id TEXT PRIMARY KEY, scenario TEXT NOT NULL,
                                      created_at REAL NOT NULL, clock_min INTEGER NOT NULL,
                                      settings TEXT NOT NULL, plan_id TEXT);
CREATE TABLE IF NOT EXISTS engineers (session_id TEXT NOT NULL, id TEXT NOT NULL, doc TEXT NOT NULL,
                                      ord INTEGER NOT NULL, PRIMARY KEY (session_id, id));
CREATE TABLE IF NOT EXISTS requests  (session_id TEXT NOT NULL, id TEXT NOT NULL, doc TEXT NOT NULL,
                                      status TEXT NOT NULL DEFAULT 'new', ord INTEGER NOT NULL,
                                      PRIMARY KEY (session_id, id));
CREATE TABLE IF NOT EXISTS events    (session_id TEXT NOT NULL, id TEXT NOT NULL, doc TEXT NOT NULL,
                                      applied_plan_id TEXT, ord INTEGER NOT NULL,
                                      PRIMARY KEY (session_id, id));
CREATE TABLE IF NOT EXISTS plans     (session_id TEXT NOT NULL, id TEXT NOT NULL,
                                      created_at REAL NOT NULL, kind TEXT NOT NULL, doc TEXT NOT NULL,
                                      params TEXT NOT NULL, risk TEXT, replan_of TEXT,
                                      PRIMARY KEY (session_id, id));
CREATE INDEX IF NOT EXISTS plans_by_session ON plans (session_id, created_at DESC);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 30000")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    return con


@contextmanager
def tx(con: sqlite3.Connection):
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise


def _next_ord(con, table: str, sid: str) -> int:
    row = con.execute(f"SELECT COALESCE(MAX(ord), 0) + 1 AS n FROM {table} WHERE session_id = ?", (sid,)).fetchone()
    return row["n"]


# -- сессия ---------------------------------------------------------------------------
def create_session(con, sid: str, scenario: str, clock_min: int, settings: dict) -> None:
    con.execute("INSERT INTO sessions (id, scenario, created_at, clock_min, settings, plan_id)"
                " VALUES (?, ?, ?, ?, ?, NULL)",
                (sid, scenario, time.time(), clock_min, json.dumps(settings, ensure_ascii=False)))


def session(con, sid: str) -> dict | None:
    r = con.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "scenario": r["scenario"], "created_at": r["created_at"],
            "clock_min": r["clock_min"], "settings": json.loads(r["settings"]), "plan_id": r["plan_id"]}


def set_clock(con, sid: str, minutes: int) -> None:
    con.execute("UPDATE sessions SET clock_min = ? WHERE id = ?", (minutes, sid))


def set_settings(con, sid: str, settings: dict) -> None:
    con.execute("UPDATE sessions SET settings = ? WHERE id = ?",
                (json.dumps(settings, ensure_ascii=False), sid))


def set_plan(con, sid: str, plan_id: str) -> None:
    con.execute("UPDATE sessions SET plan_id = ? WHERE id = ?", (plan_id, sid))


def list_sessions(con, limit: int = 20) -> list[dict]:
    """Заголовки последних сессий. Единственная функция без sid: она ничего не читает
    из справочников и событий сессий, только их шапки."""
    rows = con.execute(
        "SELECT s.id, s.scenario, s.created_at, s.clock_min, s.plan_id,"
        " MAX(s.created_at, COALESCE((SELECT MAX(p.created_at) FROM plans p WHERE p.session_id = s.id), 0))"
        " AS updated_at FROM sessions s ORDER BY updated_at DESC, s.created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


# -- справочники ----------------------------------------------------------------------
def engineers(con, sid: str) -> list[dict]:
    return [json.loads(r["doc"]) for r in
            con.execute("SELECT doc FROM engineers WHERE session_id = ? ORDER BY ord", (sid,))]


def put_engineer(con, sid: str, doc: dict) -> None:
    n = _next_ord(con, "engineers", sid)
    con.execute("INSERT INTO engineers (session_id, id, doc, ord) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (session_id, id) DO UPDATE SET doc = excluded.doc",
                (sid, doc["id"], json.dumps(doc, ensure_ascii=False), n))


def requests(con, sid: str) -> list[dict]:
    return [json.loads(r["doc"]) for r in
            con.execute("SELECT doc FROM requests WHERE session_id = ? ORDER BY ord", (sid,))]


def put_request(con, sid: str, doc: dict, status: str = "new") -> None:
    n = _next_ord(con, "requests", sid)
    con.execute("INSERT INTO requests (session_id, id, doc, status, ord) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (session_id, id) DO UPDATE SET doc = excluded.doc, status = excluded.status",
                (sid, doc["id"], json.dumps(doc, ensure_ascii=False), status, n))


def delete_request(con, sid: str, request_id: str) -> None:
    con.execute("DELETE FROM requests WHERE session_id = ? AND id = ?", (sid, request_id))


# -- события --------------------------------------------------------------------------
def events(con, sid: str, pending_only: bool = False, applied_to: str | None = None) -> list[dict]:
    q = "SELECT doc FROM events WHERE session_id = ?"
    params: list = [sid]
    if pending_only:
        q += " AND applied_plan_id IS NULL"
    if applied_to is not None:
        q += " AND applied_plan_id = ?"
        params.append(applied_to)
    return [json.loads(r["doc"]) for r in con.execute(q + " ORDER BY ord", params)]


def add_event(con, sid: str, doc: dict) -> str:
    n = _next_ord(con, "events", sid)
    doc = dict(doc)
    doc.setdefault("id", f"EV{n}")
    con.execute("INSERT INTO events (session_id, id, doc, applied_plan_id, ord) VALUES (?, ?, ?, NULL, ?)"
                " ON CONFLICT (session_id, id) DO UPDATE SET doc = excluded.doc",
                (sid, doc["id"], json.dumps(doc, ensure_ascii=False), n))
    return doc["id"]


def mark_events_applied(con, sid: str, plan_id: str, ids: list[str]) -> None:
    """Помечает учтёнными ровно те события, что ушли в расчёт. Список обязателен:
    огульное «всё, что не погашено» пометило бы и событие, заведённое во время расчёта."""
    if not ids:
        return
    marks = ", ".join("?" * len(ids))
    con.execute(f"UPDATE events SET applied_plan_id = ? WHERE session_id = ? AND id IN ({marks})",
                [plan_id, sid, *ids])


def delete_event(con, sid: str, event_id: str) -> None:
    con.execute("DELETE FROM events WHERE session_id = ? AND id = ?", (sid, event_id))


def event_state(con, sid: str, event_id: str) -> str | None:
    """None — нет такого события; 'pending' — ещё не учтено; иначе id плана, который его учёл."""
    r = con.execute("SELECT applied_plan_id FROM events WHERE session_id = ? AND id = ?", (sid, event_id)).fetchone()
    if not r:
        return None
    return r["applied_plan_id"] or "pending"


# -- планы ----------------------------------------------------------------------------
def save_plan(con, sid: str, plan: dict, kind: str, params: dict,
              risk: dict | None = None, replan_of: str | None = None) -> None:
    con.execute("INSERT OR REPLACE INTO plans (session_id, id, created_at, kind, doc, params, risk, replan_of)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, plan["plan_id"], time.time(), kind, json.dumps(plan, ensure_ascii=False),
                 json.dumps(params, ensure_ascii=False),
                 json.dumps(risk, ensure_ascii=False) if risk else None, replan_of))


def plan(con, sid: str, plan_id: str) -> tuple[dict, dict, dict | None] | None:
    r = con.execute("SELECT doc, params, risk FROM plans WHERE session_id = ? AND id = ?",
                    (sid, plan_id)).fetchone()
    if not r:
        return None
    return json.loads(r["doc"]), json.loads(r["params"]), json.loads(r["risk"]) if r["risk"] else None


def update_plan(con, sid: str, plan: dict) -> None:
    con.execute("UPDATE plans SET doc = ? WHERE session_id = ? AND id = ?",
                (json.dumps(plan, ensure_ascii=False), sid, plan["plan_id"]))


def delete_plan(con, sid: str, plan_id: str) -> None:
    con.execute("DELETE FROM plans WHERE session_id = ? AND id = ?", (sid, plan_id))


def plan_kind(con, sid: str, plan_id: str) -> str | None:
    r = con.execute("SELECT kind FROM plans WHERE session_id = ? AND id = ?", (sid, plan_id)).fetchone()
    return r["kind"] if r else None


def plans_of(con, sid: str, kind: str) -> list[tuple[dict, dict, dict | None]]:
    """Планы вида kind, новые сначала."""
    return [(json.loads(r["doc"]), json.loads(r["params"]), json.loads(r["risk"]) if r["risk"] else None)
            for r in con.execute("SELECT doc, params, risk FROM plans WHERE session_id = ? AND kind = ?"
                                 " ORDER BY created_at DESC", (sid, kind))]


def set_plan_kind(con, sid: str, plan_id: str, kind: str) -> None:
    con.execute("UPDATE plans SET kind = ? WHERE session_id = ? AND id = ?", (kind, sid, plan_id))


def unapply_events(con, sid: str, plan_id: str) -> None:
    """Вернуть в очередь события, учтённые планом plan_id (откат черновика)."""
    con.execute("UPDATE events SET applied_plan_id = NULL WHERE session_id = ? AND applied_plan_id = ?",
                (sid, plan_id))


def new_id() -> str:
    return uuid.uuid4().hex[:8]

import pytest

from app import scenarios, store


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "test.sqlite")


def seed(con, sid, ident="normal"):
    ds = scenarios.load(ident)
    with store.tx(con):
        store.create_session(con, sid, ident, 9 * 60, {"engine": "greedy"})
        for e in ds["engineers"]:
            store.put_engineer(con, sid, e)
        for r in ds["requests"]:
            store.put_request(con, sid, r)
    return ds


def test_session_round_trip(con):
    seed(con, "s1")
    s = store.session(con, "s1")
    assert s["scenario"] == "normal"
    assert s["clock_min"] == 540
    assert s["settings"] == {"engine": "greedy"}
    assert s["plan_id"] is None


def test_unknown_session_is_none(con):
    assert store.session(con, "нет-такой") is None


def test_two_sessions_do_not_see_each_other(con):
    seed(con, "s1")
    seed(con, "s2")
    with store.tx(con):
        store.put_engineer(con, "s1", dict(store.engineers(con, "s1")[0], name="Изменённый"))
    assert store.engineers(con, "s1")[0]["name"] == "Изменённый"
    assert store.engineers(con, "s2")[0]["name"] != "Изменённый"


def test_counts_are_per_session(con):
    seed(con, "s1")
    seed(con, "s2", "short-staffed")
    assert len(store.engineers(con, "s1")) == 12
    assert len(store.engineers(con, "s2")) == 8


def test_events_start_pending_and_become_applied(con):
    seed(con, "s1")
    with store.tx(con):
        eid = store.add_event(con, "s1", {"type": "engineer_unavailable", "time": "14:00",
                                          "engineer_id": "E01", "finish_current": True})
    assert len(store.events(con, "s1", pending_only=True)) == 1
    with store.tx(con):
        store.mark_events_applied(con, "s1", "PLAN1", [eid])
    assert store.events(con, "s1", pending_only=True) == []
    assert len(store.events(con, "s1")) == 1


def test_applied_events_of_one_session_do_not_touch_another(con):
    seed(con, "s1")
    seed(con, "s2")
    with store.tx(con):
        eid = store.add_event(con, "s1", {"type": "cancel_request", "time": "12:00", "request_id": "R001"})
        store.add_event(con, "s2", {"type": "cancel_request", "time": "12:00", "request_id": "R001"})
        store.mark_events_applied(con, "s1", "PLAN1", [eid])
    assert store.events(con, "s1", pending_only=True) == []
    assert len(store.events(con, "s2", pending_only=True)) == 1


def test_mark_events_applied_only_touches_the_given_events(con):
    """Событие, которого не было в расчёте, обязано остаться непринятым."""
    seed(con, "s1")
    with store.tx(con):
        a = store.add_event(con, "s1", {"type": "cancel_request", "time": "12:00", "request_id": "R001"})
        b = store.add_event(con, "s1", {"type": "cancel_request", "time": "12:30", "request_id": "R002"})
        store.mark_events_applied(con, "s1", "PLAN1", [a])
    assert [e["id"] for e in store.events(con, "s1", pending_only=True)] == [b]


def test_plan_round_trip(con):
    seed(con, "s1")
    with store.tx(con):
        store.save_plan(con, "s1", {"plan_id": "P1", "engine": "greedy"}, "base",
                        {"engine": "greedy"}, risk={"min_tol": 5})
    doc, params, risk = store.plan(con, "s1", "P1")
    assert doc["engine"] == "greedy"
    assert params == {"engine": "greedy"}
    assert risk == {"min_tol": 5}


def test_two_sessions_may_hold_plans_with_the_same_id(con):
    """plan_id — восемь шестнадцатеричных знаков; совпадение маловероятно, но запись
    одной сессии не должна иметь физической возможности затереть чужую строку."""
    seed(con, "s1")
    seed(con, "s2")
    with store.tx(con):
        store.save_plan(con, "s1", {"plan_id": "P1", "engine": "greedy"}, "base", {})
        store.save_plan(con, "s2", {"plan_id": "P1", "engine": "ortools"}, "base", {})
    assert store.plan(con, "s1", "P1")[0]["engine"] == "greedy"
    assert store.plan(con, "s2", "P1")[0]["engine"] == "ortools"


def test_plan_of_another_session_is_not_readable(con):
    seed(con, "s1")
    seed(con, "s2")
    with store.tx(con):
        store.save_plan(con, "s1", {"plan_id": "P1", "engine": "greedy"}, "base", {})
    assert store.plan(con, "s2", "P1") is None


def test_rollback_leaves_nothing_behind(con):
    seed(con, "s1")
    with pytest.raises(RuntimeError):
        with store.tx(con):
            store.add_event(con, "s1", {"type": "cancel_request", "time": "12:00", "request_id": "R001"})
            raise RuntimeError("boom")
    assert store.events(con, "s1") == []

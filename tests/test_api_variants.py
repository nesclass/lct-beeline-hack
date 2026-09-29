import pytest

from app import planning, state, store, variants
from app.schema import MARGINS, PRIORITY_F, Settings
from app.variants import insight, recommend

NEW = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3", "district": "Царицыно",
       "type": "Нет линка", "skill": "local", "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}


@pytest.fixture
def quick(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    return sid


def test_priority_sets_the_engineer_weight(client, sid):
    for key, f in PRIORITY_F.items():
        client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "priority": key})
        ds = planning.dataset(state.con(), sid)
        assert ds["config"]["weights"]["F"] == f
        assert ds["config"]["weights"]["P"] > f * len(ds["engineers"]) + 1000   # строгий порядок


def test_variants_are_baseline_and_three_margins(client, quick):
    r = client.post(f"/api/sessions/{quick}/variants").json()
    assert [v["key"] for v in r["variants"]] == ["baseline", "econom", "balanced", "reliable"]
    assert r["recommended"] in ("econom", "balanced", "reliable")
    by = {v["key"]: v for v in r["variants"]}
    assert by["baseline"]["engineers_used"] >= by["econom"]["engineers_used"]
    assert by["reliable"]["expected_late"] <= by["econom"]["expected_late"]
    assert client.get(f"/api/sessions/{quick}").json()["plan_id"] is None, "расчёт вариантов плана не утверждает"
    assert client.get(f"/api/sessions/{quick}/variants").json()["run_id"] == r["run_id"]


def test_approving_a_variant_makes_it_the_plan(client, quick):
    r = client.post(f"/api/sessions/{quick}/variants").json()
    v = next(x for x in r["variants"] if x["key"] == "reliable")
    s = client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve").json()
    assert s["plan_id"] == v["plan_id"] and s["status"] == "planned"
    st = client.get(f"/api/sessions/{quick}/settings").json()
    assert (st["margin"], st["work_pct"], st["travel_pct"], st["travel_min"]) == ("reliable", *MARGINS["reliable"])
    h = client.get(f"/api/sessions/{quick}/history").json()
    assert (h[0]["kind"], h[0]["label"]) == ("variant", "Надёжный")


def test_stale_variant_cannot_be_approved(client, quick):
    old = client.post(f"/api/sessions/{quick}/variants").json()["variants"][1]["plan_id"]
    client.post(f"/api/sessions/{quick}/variants")
    assert client.post(f"/api/sessions/{quick}/variants/{old}/approve").status_code == 409


def test_variants_are_refused_once_the_day_is_replanned(client, quick):
    client.post(f"/api/sessions/{quick}/plan")
    client.put(f"/api/sessions/{quick}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{quick}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{quick}/replan")
    assert client.post(f"/api/sessions/{quick}/variants").status_code == 409


def test_variants_are_refused_after_an_accepted_replan(client, quick):
    """Тот же запрет, но по ветке replan_of, а не «непринятый черновик»: перепланирование
    приняли, а варианты на весь день всё равно больше не строятся."""
    client.post(f"/api/sessions/{quick}/plan")
    client.put(f"/api/sessions/{quick}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{quick}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{quick}/replan")
    client.post(f"/api/sessions/{quick}/plan/accept")
    assert client.post(f"/api/sessions/{quick}/variants").status_code == 409


def test_approve_keeps_time_limit_engine_priority_and_warm_start(client, sid):
    """Утверждение варианта переносит только запас (work_pct/travel_pct/travel_min/margin) —
    не бюджет времени расчёта варианта (time_limit/3) и не остальные настройки."""
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 9, "warm_start": False, "priority": "fewer"})
    r = client.post(f"/api/sessions/{sid}/variants").json()
    v = next(x for x in r["variants"] if x["key"] == "balanced")
    client.post(f"/api/sessions/{sid}/variants/{v['plan_id']}/approve")
    st = client.get(f"/api/sessions/{sid}/settings").json()
    assert st["time_limit"] == 9
    assert st["engine"] == "greedy" and st["warm_start"] is False and st["priority"] == "fewer"
    assert (st["margin"], st["work_pct"], st["travel_pct"], st["travel_min"]) == ("balanced", *MARGINS["balanced"])


def test_approving_baseline_sets_margin_to_econom(client, quick):
    r = client.post(f"/api/sessions/{quick}/variants").json()
    v = next(x for x in r["variants"] if x["key"] == "baseline")
    client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve")
    assert client.get(f"/api/sessions/{quick}/settings").json()["margin"] == "econom"


def test_approve_applies_only_events_seen_at_compute_time(client, quick):
    client.post(f"/api/sessions/{quick}/engineers/E01/unavailable", json={})
    r = client.post(f"/api/sessions/{quick}/variants").json()
    client.post(f"/api/sessions/{quick}/requests", json=NEW)      # пришло уже после расчёта вариантов
    v = next(x for x in r["variants"] if x["key"] == "balanced")
    s = client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve").json()
    assert [e["type"] for e in s["pending_events"]] == ["new_request"]


def test_approving_after_the_plan_changed_since_compute_is_409(client, quick):
    """compute -> новое событие -> «Построить план» (принимает его без вариантов) -> утвердить
    старый вариант — он не видел построенный план, поэтому тихо потерял бы событие."""
    r = client.post(f"/api/sessions/{quick}/variants").json()
    v = next(x for x in r["variants"] if x["key"] == "balanced")
    client.post(f"/api/sessions/{quick}/requests", json=NEW)
    client.post(f"/api/sessions/{quick}/plan")
    resp = client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve")
    assert resp.status_code == 409
    assert "пересчитайте" in resp.json()["detail"]


def test_variants_save_is_all_or_nothing(monkeypatch, client, quick):
    """Срыв на третьем варианте не должен оставить в базе первые два — вся четвёрка в одной
    транзакции."""
    calls = {"n": 0}
    orig_save = store.save_plan

    def flaky(con, sid, plan, kind, params, risk=None, replan_of=None):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return orig_save(con, sid, plan, kind, params, risk=risk, replan_of=replan_of)

    monkeypatch.setattr(store, "save_plan", flaky)
    with pytest.raises(RuntimeError):
        variants.compute(state.con(), quick)
    assert store.plans_of(state.con(), quick, "variant") == []


def _row(key, asg, eng, km, late):
    return {"key": key, "name": {"baseline": "Базовый", "econom": "Экономный", "balanced": "Сбалансированный",
                                 "reliable": "Надёжный"}[key],
            "assigned": asg, "total": 50, "engineers_used": eng, "total_km": km, "expected_late": late}


ROWS = [_row("baseline", 46, 11, 247.0, 0.9), _row("econom", 48, 8, 174.0, 1.6),
        _row("balanced", 48, 9, 185.0, 0.4), _row("reliable", 47, 10, 199.0, 0.1)]


def test_recommendation_prefers_on_time_then_fewer_people():
    assert recommend(ROWS, 0.5) == "balanced"
    assert recommend([ROWS[0], ROWS[1]], 0.5) == "econom"          # порог не прошёл никто — меньше опозданий


def test_insight_names_the_gain_and_the_trade_off():
    assert insight(ROWS, "balanced") == (
        "«Сбалансированный» назначает 48 из 50 на 9 инженерах — на 2 меньше и на 62 км короче базового. "
        "Ожидаемо 0,4 опоздания за день. «Экономный» освобождает ещё одного, но опозданий станет в 4 раза больше.")


def test_recommend_tolerates_a_missing_risk_estimate():
    rows = [_row("baseline", 46, 11, 247.0, 0.9), _row("econom", 48, 8, 174.0, None),
            _row("balanced", 48, 9, 185.0, None)]
    assert recommend(rows, 0.5) in ("econom", "balanced")


def test_insight_tolerates_a_missing_risk_estimate():
    rows = [_row("baseline", 46, 11, 247.0, 0.9), _row("econom", 48, 8, 174.0, None),
            _row("balanced", 48, 9, 185.0, None)]
    text = insight(rows, "balanced")
    assert "оценки опозданий нет" in text
    assert "раза больше" not in text                      # сравнение без оценки риска не строим


def test_insight_drops_the_no_better_clauses():
    rows = [_row("baseline", 48, 8, 150.0, 0.4), _row("econom", 48, 8, 150.0, 0.4),
            _row("balanced", 48, 9, 200.0, 0.3), _row("reliable", 47, 10, 220.0, 0.1)]
    text = insight(rows, "econom")                         # не меньше людей и не короче базового
    assert text.startswith("«Экономный» назначает 48 из 50 на 8 инженерах.")
    assert "меньше" not in text and "короче" not in text


def test_insight_skips_a_small_trade_off():
    rows = [_row("baseline", 46, 11, 247.0, 0.9), _row("econom", 48, 8, 174.0, 0.5),
            _row("balanced", 48, 9, 185.0, 0.4), _row("reliable", 47, 10, 199.0, 0.1)]
    text = insight(rows, "balanced")                       # 0,5 / 0,4 округляется до 1 — разница не заметна
    assert "раза больше" not in text


def test_insight_names_more_than_one_engineer_freed():
    rows = [_row("baseline", 46, 12, 260.0, 0.9), _row("econom", 48, 7, 170.0, 2.0),
            _row("balanced", 48, 10, 190.0, 0.4), _row("reliable", 47, 11, 205.0, 0.1)]
    assert "освобождает ещё 3" in insight(rows, "balanced")


# -- день уже начался (C1) и очередь переносов при расчёте на весь день (I1) --

DAY_STARTED = "день уже начался"


def _first_start(plan: dict) -> str:
    return min(s["start"] for rt in plan["routes"] for s in rt["stops"])


def _minus_one(t: str) -> str:
    m = int(t[:2]) * 60 + int(t[3:]) - 1
    return f"{m // 60:02d}:{m % 60:02d}"


def test_whole_day_actions_are_refused_once_the_first_job_has_started(client, quick):
    plan = client.post(f"/api/sessions/{quick}/plan").json()
    r = client.post(f"/api/sessions/{quick}/variants").json()
    v = next(x for x in r["variants"] if x["key"] == "balanced")
    client.put(f"/api/sessions/{quick}/clock", json={"time": _first_start(plan)})
    assert client.get(f"/api/sessions/{quick}").json()["day_started"] is True
    for resp in (client.post(f"/api/sessions/{quick}/variants"),
                 client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve"),
                 client.post(f"/api/sessions/{quick}/plan")):
        assert resp.status_code == 409, resp.text
        assert DAY_STARTED in resp.json()["detail"]
    assert client.get(f"/api/sessions/{quick}").json()["plan_id"] == plan["plan_id"]


def test_variants_still_work_before_the_first_job_starts(client, quick):
    plan = client.post(f"/api/sessions/{quick}/plan").json()
    client.put(f"/api/sessions/{quick}/clock", json={"time": _minus_one(_first_start(plan))})
    assert client.get(f"/api/sessions/{quick}").json()["day_started"] is False
    r = client.post(f"/api/sessions/{quick}/variants")
    assert r.status_code == 200
    v = next(x for x in r.json()["variants"] if x["key"] == "balanced")
    assert client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve").status_code == 200
    assert client.post(f"/api/sessions/{quick}/plan").status_code == 200


def test_new_session_is_not_started(client, sid):
    assert client.get(f"/api/sessions/{sid}").json()["day_started"] is False


def _movable(plan: dict) -> tuple[str, str]:
    """Заявка не первая в маршруте, у которой есть допустимый другой инженер."""
    for rt in plan["routes"]:
        for s in rt["stops"][1:]:
            alt = next((x for x in plan["assignments"][s["request_id"]]["reason"]["alternatives"]
                        if x["feasible"]), None)
            if alt:
                return s["request_id"], alt["engineer_id"]
    raise AssertionError("в плане нет заявки с допустимой альтернативой")


def test_queued_move_survives_approving_a_variant(client, quick):
    plan = client.post(f"/api/sessions/{quick}/plan").json()
    rid, k = _movable(plan)
    assert client.post(f"/api/sessions/{quick}/requests/{rid}/move", json={"engineer_id": k}).status_code == 200
    r = client.post(f"/api/sessions/{quick}/variants").json()
    v = next(x for x in r["variants"] if x["key"] == "econom")
    s = client.post(f"/api/sessions/{quick}/variants/{v['plan_id']}/approve").json()
    assert s["pending_events"] == [] and s["status"] == "planned"
    got = client.get(f"/api/sessions/{quick}/plan").json()["plan"]
    assert got["assignments"][rid]["engineer_id"] == k
    assert got["assignments"][rid]["manual"] is True
    assert got["pins"] == {rid: k}


def test_queued_move_survives_rebuilding_the_plan(client, quick):
    plan = client.post(f"/api/sessions/{quick}/plan").json()
    rid, k = _movable(plan)
    client.post(f"/api/sessions/{quick}/requests/{rid}/move", json={"engineer_id": k})
    new = client.post(f"/api/sessions/{quick}/plan").json()
    assert new["assignments"][rid]["engineer_id"] == k
    assert new["assignments"][rid]["manual"] is True
    assert new["pins"] == {rid: k}
    assert client.get(f"/api/sessions/{quick}").json()["pending_events"] == []

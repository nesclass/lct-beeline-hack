import pytest

from planner.model import hhmm

NEW = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3", "district": "Царицыно",
       "type": "Нет линка", "skill": "local", "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}


@pytest.fixture
def planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    return sid


def _pending(client, sid):
    return client.get(f"/api/sessions/{sid}").json()["pending_events"]


# -- недоступность ------------------------------------------------------------------
def test_leave_in_the_future_is_queued_with_its_time_and_reason(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:45"})
    r = client.post(f"/api/sessions/{planned}/engineers/E01/unavailable",
                    json={"mode": "leave", "time": "14:00", "finish_current": True, "reason": "семейные обстоятельства"})
    assert r.status_code == 200
    ev = _pending(client, planned)[0]
    assert (ev["time"], ev["mode"], ev["reason"]) == ("14:00", "leave", "семейные обстоятельства")


def test_leave_before_the_clock_is_refused(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:45"})
    r = client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"mode": "leave", "time": "13:00"})
    assert r.status_code == 409
    assert "раньше часов" in r.json()["detail"]


def test_absent_means_from_the_start_of_the_shift(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E05/unavailable", json={"mode": "absent"})
    ev = _pending(client, planned)[0]
    shift = next(e for e in client.get(f"/api/sessions/{planned}/engineers").json() if e["id"] == "E05")["shift_start"]
    assert (ev["time"], ev["finish_current"]) == (shift, False)


def test_replace_swaps_the_queued_event(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "14:00"})
    old = _pending(client, planned)[0]["id"]
    r = client.post(f"/api/sessions/{planned}/engineers/E01/unavailable?replace={old}", json={"time": "15:00"})
    assert r.status_code == 200
    evs = _pending(client, planned)
    assert [e["time"] for e in evs] == ["15:00"]


# -- удаление из очереди --------------------------------------------------------------
def test_deleting_a_queued_new_request_removes_the_request(client, planned):
    rid = client.post(f"/api/sessions/{planned}/requests", json=NEW).json()["request"]["id"]
    ev = _pending(client, planned)[0]["id"]
    assert client.delete(f"/api/sessions/{planned}/events/{ev}").json()["status"] == "planned"
    assert rid not in {r["id"] for r in client.get(f"/api/sessions/{planned}/requests").json()}


def test_applied_event_cannot_be_deleted(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    ev = _pending(client, planned)[0]["id"]
    client.post(f"/api/sessions/{planned}/replan")
    assert client.delete(f"/api/sessions/{planned}/events/{ev}").status_code == 409
    assert client.delete(f"/api/sessions/{planned}/events/EV999").status_code == 404


def test_deleting_a_new_request_event_clears_its_dangling_cancel(client, planned):
    """Освобождённый номер заявки не должен наследовать чужую отмену/перенос из очереди
    (регресс из ревью: add R060 → cancel R060 → удалить new_request → новая заявка с тем же
    номером не должна оказаться «отменённой»)."""
    rid = client.post(f"/api/sessions/{planned}/requests", json=NEW).json()["request"]["id"]
    assert client.post(f"/api/sessions/{planned}/requests/{rid}/cancel", json={}).status_code == 200
    new_ev = next(e for e in _pending(client, planned) if e["type"] == "new_request")
    assert client.delete(f"/api/sessions/{planned}/events/{new_ev['id']}").status_code == 200
    assert _pending(client, planned) == [], "отмена той же заявки должна уйти вместе с ней"
    reused = client.post(f"/api/sessions/{planned}/requests", json=NEW).json()["request"]["id"]
    assert reused == rid, "номер должен быть переиспользован"
    assert client.post(f"/api/sessions/{planned}/requests/{reused}/cancel", json={}).status_code == 200, \
        "новая заявка с переиспользованным номером не должна тащить за собой старую отмену"


def test_replacing_a_new_request_event_clears_its_dangling_move(client, planned):
    """Аналогичный регресс через ?replace=: add → move → replace add → перенос не должен
    остаться висеть в очереди на чужую (новую) заявку с тем же номером."""
    k = client.post(f"/api/sessions/{planned}/preview/request", json=NEW).json()["candidates"][0]["engineer_id"]
    rid = client.post(f"/api/sessions/{planned}/requests", json=NEW).json()["request"]["id"]
    assert client.post(f"/api/sessions/{planned}/requests/{rid}/move", json={"engineer_id": k}).status_code == 200
    new_ev = next(e for e in _pending(client, planned) if e["type"] == "new_request")
    r = client.post(f"/api/sessions/{planned}/requests?replace={new_ev['id']}", json=NEW)
    assert r.status_code == 200, r.text
    assert not any(e["type"] == "move_request" and e["request_id"] == rid for e in _pending(client, planned))


# -- замена (?replace=) на событие другого рода -----------------------------------------
def test_replacing_a_request_event_refuses_an_unrelated_event(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "14:00"})
    ev = _pending(client, planned)[0]["id"]
    r = client.post(f"/api/sessions/{planned}/requests?replace={ev}", json=NEW)
    assert r.status_code == 409
    assert "так заменить нельзя" in r.json()["detail"]


def test_replacing_an_unavailable_event_refuses_an_unrelated_event(client, planned):
    client.post(f"/api/sessions/{planned}/requests", json=NEW)
    ev = _pending(client, planned)[0]["id"]
    r = client.post(f"/api/sessions/{planned}/engineers/E01/unavailable?replace={ev}", json={"time": "14:00"})
    assert r.status_code == 409
    assert "так заменить нельзя" in r.json()["detail"]


def test_replacing_an_unavailable_event_refuses_another_engineers_event(client, planned):
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "14:00"})
    ev = _pending(client, planned)[0]["id"]
    r = client.post(f"/api/sessions/{planned}/engineers/E05/unavailable?replace={ev}", json={"time": "15:00"})
    assert r.status_code == 409
    assert "так заменить нельзя" in r.json()["detail"]


# -- отмена -----------------------------------------------------------------------------
def test_cancelled_request_stays_out_of_later_replans(client, planned):
    view = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    rid = next(s["request_id"] for rt in view["routes"] for s in rt["stops"] if s["start"] >= "15:00")
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    assert client.post(f"/api/sessions/{planned}/requests/{rid}/cancel", json={}).status_code == 200
    assert client.post(f"/api/sessions/{planned}/requests/{rid}/cancel", json={}).status_code == 409
    client.post(f"/api/sessions/{planned}/replan")
    client.post(f"/api/sessions/{planned}/requests", json=NEW)          # любое новое событие
    new = client.post(f"/api/sessions/{planned}/replan").json()
    assert rid not in new["assignments"], "отменённая заявка вернулась в расписание"
    row = next(r for r in client.get(f"/api/sessions/{planned}/requests").json() if r["id"] == rid)
    assert row["status"] == "cancelled"


def test_cancelled_before_the_plan_is_not_planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/requests/R001/cancel", json={})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    assert "R001" not in plan["assignments"]


# -- перенос ----------------------------------------------------------------------------
def _alternative(view):
    """Незамороженная заявка не первая в маршруте и допустимый другой инженер для неё."""
    for rt in view["routes"]:
        for s in rt["stops"][1:]:
            a = view["assignments"][s["request_id"]]
            alt = next((x for x in a["reason"]["alternatives"] if x["feasible"]), None)
            if alt and s["start"] >= "11:00":
                return s["request_id"], alt["engineer_id"]
    raise AssertionError("в плане нет заявки с допустимой альтернативой")


def test_move_is_queued_and_lands_after_replan(client, planned):
    rid, k = _alternative(client.get(f"/api/sessions/{planned}/plan").json()["plan"])
    r = client.post(f"/api/sessions/{planned}/requests/{rid}/move", json={"engineer_id": k})
    assert r.status_code == 200, r.text
    ev = _pending(client, planned)[0]
    assert (ev["type"], ev["request_id"], ev["engineer_id"]) == ("move_request", rid, k)
    new = client.post(f"/api/sessions/{planned}/replan").json()
    assert new["assignments"][rid]["engineer_id"] == k
    assert new["assignments"][rid]["manual"] is True


def test_move_to_an_engineer_without_the_skill_is_refused(client, planned):
    # часы сессии по умолчанию совпадают с началом дня — первая остановка маршрута
    # уже «в пути» к этому моменту (выезд = прибытие − дорога = начало дня); отводим
    # часы раньше начала дня, чтобы искомая (любая) заявка не была заморожена по времени.
    client.put(f"/api/sessions/{planned}/clock", json={"time": "00:00"})
    view = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    rid, a = next((rid, a) for rid, a in view["assignments"].items()
                  if a["engineer_id"] and any(x["blocker"]["code"] == "SKILL"
                                              for x in a["reason"].get("alternatives", []) if not x["feasible"]))
    k = next(x["engineer_id"] for x in a["reason"]["alternatives"] if not x["feasible"] and x["blocker"]["code"] == "SKILL")
    r = client.post(f"/api/sessions/{planned}/requests/{rid}/move", json={"engineer_id": k})
    assert r.status_code == 409
    assert "нет нужного навыка" in r.json()["detail"]
    assert _pending(client, planned) == []


def test_started_request_cannot_be_moved(client, planned):
    view = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    rt = next(r for r in view["routes"] if r["stops"])
    first = rt["stops"][0]
    client.put(f"/api/sessions/{planned}/clock", json={"time": first["start"]})
    other = next(r["engineer_id"] for r in view["routes"] if r["engineer_id"] != rt["engineer_id"])
    r = client.post(f"/api/sessions/{planned}/requests/{first['request_id']}/move", json={"engineer_id": other})
    assert r.status_code == 409
    assert "уже начата" in r.json()["detail"]


def test_departed_request_cannot_be_moved_either_with_a_different_reason(client, planned):
    """Инженер уже выехал к первой остановке (выезд = прибытие − дорога), но работу ещё не
    начал — на часах сессии по умолчанию (начало дня) это обычно так для первой остановки
    маршрута. Причина диспетчеру должна отличаться от «уже начата»."""
    view = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    now = hhmm(client.get(f"/api/sessions/{planned}").json()["clock"])
    rid, owner = next((s["request_id"], rt["engineer_id"])
                       for rt in view["routes"] if rt["stops"]
                       for s in [rt["stops"][0]]
                       if hhmm(s["arrive"]) - s["leg_min"] <= now < hhmm(s["start"]))
    other = next(r["engineer_id"] for r in view["routes"] if r["engineer_id"] != owner)
    r = client.post(f"/api/sessions/{planned}/requests/{rid}/move", json={"engineer_id": other})
    assert r.status_code == 409
    assert "уже выехал" in r.json()["detail"]


# -- предпросмотры ----------------------------------------------------------------------
def test_request_preview_lists_who_can_take_it_after_the_clock(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:30"})
    body = {**NEW, "type": "Обрыв магистрали", "skill": "emergency", "work_type": "emergency",
            "tw_start": "13:30", "tw_end": "15:30", "priority": "urgent"}
    r = client.post(f"/api/sessions/{planned}/preview/request", json=body).json()
    assert r["skill"] == "emergency" and r["duration_min"] == 80
    assert r["candidates"], "в обычном дне хоть кто-то успевает"
    starts = [c["start"] for c in r["candidates"]]
    assert starts == sorted(starts) and all(s >= "13:30" for s in starts)
    assert _pending(client, planned) == [], "предпросмотр ничего не пишет"


def test_request_preview_without_a_plan_has_no_candidates(client, sid):
    assert client.post(f"/api/sessions/{sid}/preview/request", json=NEW).json()["candidates"] is None


def test_unavailable_preview_matches_the_impact(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    pre = client.post(f"/api/sessions/{planned}/preview/unavailable/E01", json={"time": "13:00"}).json()
    assert pre["leave"] == "13:00"
    view = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    after = {s["request_id"] for rt in view["routes"] if rt["engineer_id"] == "E01" for s in rt["stops"]
             if s["finish"] > "13:00" and s["arrive"] > "12:00"}
    assert {x["request_id"] for x in pre["released"]} >= after - {x["request_id"] for x in [pre["current"] or {"request_id": ""}]}
    assert pre["can_take"] == sum(1 for x in pre["released"] if x["taker"])
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "13:00"})
    imp = client.get(f"/api/sessions/{planned}/impact").json()
    assert imp["since"] == "12:00"
    assert set(imp["orphaned"]) == {x["request_id"] for x in pre["released"]}


def test_impact_counts_queued_urgent_requests(client, planned):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:30"})
    client.post(f"/api/sessions/{planned}/requests", json={**NEW, "priority": "urgent", "tw_start": "14:00", "tw_end": "16:00"})
    imp = client.get(f"/api/sessions/{planned}/impact").json()
    assert imp["urgent_unassigned"] == 1
    assert isinstance(imp["expected_late"], float)


def test_impact_needs_a_plan(client, sid):
    assert client.get(f"/api/sessions/{sid}/impact").status_code == 409


def test_unavailable_preview_names_the_engineers_the_replan_will_use(client, planned):
    """Регресс: предпросмотр вставлял освободившиеся заявки жадно по одной и обещал «возьмёт Саламатин»,
    а «Перепланировать» отдавало заявку Макарову. Теперь предпросмотр — тот же расчёт без записи."""
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    pre = client.post(f"/api/sessions/{planned}/preview/unavailable/E01", json={"time": "13:00"}).json()
    assert pre["released"]
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "13:00"})
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    for x in pre["released"]:
        got = plan["assignments"][x["request_id"]]["engineer_id"]
        assert (x["taker"] or {}).get("engineer_id") == got, x
        if x["taker"]:
            stop = next(s for rt in plan["routes"] for s in rt["stops"] if s["request_id"] == x["request_id"])
            assert x["taker"]["start"] == stop["start"]


def test_late_evening_replan_with_ortools_when_shifts_are_over(client, sid):
    """Регресс (сессия 882d2621): часы 20:15, отмена заявки — у тех, чья смена кончилась в 18:00,
    «свободен с» оказывалось позже конца смены, OR-Tools падал «CP Solver fail», /replan отдавал 500."""
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "ortools", "time_limit": 2})
    client.post(f"/api/sessions/{sid}/plan")
    plan = client.get(f"/api/sessions/{sid}/plan").json()["plan"]
    client.put(f"/api/sessions/{sid}/clock", json={"time": "20:15"})
    rid = next(s["request_id"] for rt in plan["routes"] for s in rt["stops"] if s["start"] > "20:15")
    assert client.post(f"/api/sessions/{sid}/requests/{rid}/cancel", json={}).status_code == 200
    r = client.post(f"/api/sessions/{sid}/replan")
    assert r.status_code == 200, r.text
    assert r.json()["diff"]["requests"][rid]["status"] == "removed"


def test_new_request_gets_road_distances_from_the_geo_layer(client, planned, monkeypatch):
    from app import geo, planning, state
    from test_api_plan import ConstantRoads
    monkeypatch.setattr(geo, "_provider", ConstantRoads())
    rid = client.post(f"/api/sessions/{planned}/requests", json=NEW).json()["request"]["id"]
    ds = planning.dataset(state.con(), planned)
    assert rid in ds["matrix"]["ids"], "заявка, заведённая днём, не попала в матрицу гео-слоя"
    assert ds["meta"]["travel_source"] == "osrm"

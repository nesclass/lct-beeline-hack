import pytest

NEW = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3",
       "district": "Царицыно", "type": "Нет линка", "skill": "local",
       "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}


@pytest.fixture
def fast(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    return sid


def test_engineers_are_listed_with_skills(client, sid):
    people = client.get(f"/api/sessions/{sid}/engineers").json()
    assert len(people) == 12
    e = next(x for x in people if x["id"] == "E01")
    assert set(e["skills"]) == {"local", "connect", "emergency"}
    assert e["transport"] == "car"
    assert e["unavailable_from"] is None


def test_declaring_unavailable_creates_a_pending_event(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    client.put(f"/api/sessions/{fast}/clock", json={"time": "14:00"})
    r = client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={"finish_current": True})
    assert r.status_code == 200
    assert r.json()["status"] == "dirty"
    ev = r.json()["pending_events"]
    assert len(ev) == 1
    assert ev[0]["type"] == "engineer_unavailable"
    assert ev[0]["engineer_id"] == "E01"
    assert ev[0]["time"] == "14:00"


def test_unavailable_shows_up_on_the_engineer(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={"finish_current": True})
    e = next(x for x in client.get(f"/api/sessions/{fast}/engineers").json() if x["id"] == "E01")
    assert e["unavailable_from"] == "09:00"


def test_unknown_engineer_is_404(client, sid):
    r = client.post(f"/api/sessions/{sid}/engineers/E99/unavailable", json={})
    assert r.status_code == 404
    # без этой строки тест проходил бы и при отсутствующем маршруте: 404 вернулся бы сам собой
    assert "инженер" in r.json()["detail"]


def test_requests_show_who_got_them(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    rows = client.get(f"/api/sessions/{fast}/requests").json()
    assert len(rows) == 59
    assert any(r["assigned_to"] for r in rows)
    assert all(r["status"] in ("assigned", "unassigned") for r in rows)


def test_requests_before_the_plan_have_no_assignment(client, sid):
    rows = client.get(f"/api/sessions/{sid}/requests").json()
    assert all(r["assigned_to"] is None and r["status"] == "new" for r in rows)


def test_regular_request_is_added_and_makes_the_session_dirty(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    r = client.post(f"/api/sessions/{fast}/requests", json=NEW)
    assert r.status_code == 200
    assert r.json()["session"]["status"] == "dirty"
    assert len(client.get(f"/api/sessions/{fast}/requests").json()) == 60


def test_urgent_request_also_creates_an_event_with_the_clock_time(client, fast):
    client.post(f"/api/sessions/{fast}/plan")
    client.put(f"/api/sessions/{fast}/clock", json={"time": "13:30"})
    body = client.post(f"/api/sessions/{fast}/requests",
                       json={**NEW, "priority": "urgent", "tw_start": "13:30", "tw_end": "15:30"}).json()
    ev = body["session"]["pending_events"]
    assert [e["type"] for e in ev] == ["urgent_request"]
    assert ev[0]["time"] == "13:30"
    assert ev[0]["request"]["priority"] == "urgent"


def test_new_request_gets_norm_duration(client, fast):
    body = client.post(f"/api/sessions/{fast}/requests", json=NEW).json()
    assert body["request"]["duration_min"] == 30       # local_repair: 30 техработ + 0 документов


def test_request_with_broken_window_is_422(client, sid):
    assert client.post(f"/api/sessions/{sid}/requests", json={**NEW, "tw_start": "четверг"}).status_code == 422


def test_events_of_one_session_do_not_leak(client, fast):
    assert client.post(f"/api/sessions/{fast}/plan").status_code == 200
    assert client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={}).status_code == 200
    # если событие не завелось и в своей сессии, «не протекло в чужую» ничего не значит
    assert len(client.get(f"/api/sessions/{fast}").json()["pending_events"]) == 1
    other = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
    assert client.get(f"/api/sessions/{other}").json()["pending_events"] == []


def test_next_request_id_skips_taken_numbers():
    from app.catalog import next_request_id
    rows = [{"id": "R001"}, {"id": "R002"}, {"id": "R003"}]
    assert next_request_id(rows) == "R004"
    # номер, который дала бы длина списка, уже занят — берём следующий свободный
    assert next_request_id([{"id": "R001"}, {"id": "R003"}, {"id": "R002"}, {"id": "R004"}]) == "R005"
    assert next_request_id([{"id": "R002"}]) == "R003"


def test_request_filed_after_the_plan_is_new(client, fast):
    """Заявка, которой в плане нет вовсе, ещё не рассматривалась — это new, а не unassigned."""
    client.post(f"/api/sessions/{fast}/plan")
    rid = client.post(f"/api/sessions/{fast}/requests", json=NEW).json()["request"]["id"]
    row = next(r for r in client.get(f"/api/sessions/{fast}/requests").json() if r["id"] == rid)
    assert row["status"] == "new" and row["assigned_to"] is None


def test_request_status_follows_the_plan(client, fast):
    plan = client.post(f"/api/sessions/{fast}/plan").json()
    rows = {r["id"]: r for r in client.get(f"/api/sessions/{fast}/requests").json()}
    assert plan["unassigned"], "нечего проверять: в плане всё назначено"
    for rid, a in plan["assignments"].items():
        assert rows[rid]["assigned_to"] == a["engineer_id"]
        assert rows[rid]["status"] == ("assigned" if a["engineer_id"] else "unassigned")


def test_new_request_duration_includes_paperwork(client, fast):
    body = client.post(f"/api/sessions/{fast}/requests",
                       json={**NEW, "skill": "connect", "work_type": "connect_base"}).json()
    assert body["request"]["duration_min"] == 70       # connect_base: 60 техработ + 10 документов


def test_earliest_unavailability_wins(client, fast):
    """До плана часы можно отвести назад, и порядок записи событий перестаёт совпадать
    с порядком времени. Считается самое раннее — и в карточке, и в плане."""
    client.put(f"/api/sessions/{fast}/clock", json={"time": "13:00"})
    client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={"finish_current": True})
    client.put(f"/api/sessions/{fast}/clock", json={"time": "10:00"})
    client.post(f"/api/sessions/{fast}/engineers/E01/unavailable", json={"finish_current": True})
    card = next(e for e in client.get(f"/api/sessions/{fast}/engineers").json() if e["id"] == "E01")
    assert card["unavailable_from"] == "10:00"
    plan = client.post(f"/api/sessions/{fast}/plan").json()
    rt = next(r for r in plan["routes"] if r["engineer_id"] == "E01")
    assert rt["unavailable_from"] == "10:00"


def test_window_must_end_after_it_starts(client, sid):
    r = client.post(f"/api/sessions/{sid}/requests", json={**NEW, "tw_start": "15:00", "tw_end": "15:00"})
    assert r.status_code == 422
    assert "конец окна должен быть позже начала" in r.text


def test_point_outside_the_agglomeration_is_rejected(client, sid):
    r = client.post(f"/api/sessions/{sid}/requests", json={**NEW, "lat": 59.93, "lon": 30.33})
    assert r.status_code == 422
    assert "вне Московской агломерации" in r.text


def test_requests_say_who_created_them_and_what_waits(client, sid):
    rid = client.post(f"/api/sessions/{sid}/requests", json=NEW).json()["request"]["id"]
    rows = {r["id"]: r for r in client.get(f"/api/sessions/{sid}/requests").json()}
    assert rows[rid]["by_dispatcher"] is True
    assert rows[rid]["pending"] == ["new_request"]
    assert sum(not r["by_dispatcher"] for r in rows.values()) == 59
    assert rows["R001"]["pending"] == []


def test_form_catalog_lists_types_districts_and_norms(client, sid):
    c = client.get(f"/api/sessions/{sid}/catalog").json()
    kinds = {(t["type"], t["work_type"]) for t in c["types"]}
    assert ("Обрыв магистрали", "emergency") in kinds
    assert all(t["skill"] in ("local", "connect", "emergency") for t in c["types"])
    tsar = next(d for d in c["districts"] if d["name"] == "Царицыно")
    assert 55.5 < tsar["lat"] < 55.7 and 37.5 < tsar["lon"] < 37.8
    assert c["norms"]["emergency"]["tech_min"] == 80
    assert c["day"] == ["09:00", "22:00"]
    assert c["date"] == "2026-08-17"

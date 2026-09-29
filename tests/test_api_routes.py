import pytest


@pytest.fixture
def planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings",
               json={"engine": "greedy", "time_limit": 5, "warm_start": False,
                     "work_pct": 0, "travel_pct": 0, "travel_min": 0})
    client.post(f"/api/sessions/{sid}/plan")
    return sid


def test_routes_are_returned_for_working_engineers(client, planned):
    body = client.get(f"/api/sessions/{planned}/routes").json()
    assert body["source"] in ("osrm", "haversine")
    assert body["routes"]
    assert all(r["points"] for r in body["routes"])


def test_first_point_is_the_engineer_start(client, planned):
    r = client.get(f"/api/sessions/{planned}/routes").json()["routes"][0]
    assert r["points"][0]["request_id"] is None
    assert r["points"][0]["seq"] == 0


def test_points_follow_the_plan_order(client, planned):
    body = client.get(f"/api/sessions/{planned}/routes").json()
    plan = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    by_id = {rt["engineer_id"]: rt for rt in plan["routes"]}
    for r in body["routes"]:
        expected = [s["request_id"] for s in by_id[r["engineer_id"]]["stops"]]
        assert [p["request_id"] for p in r["points"][1:]] == expected


def test_every_leg_has_a_line_with_both_ends(client, planned):
    for r in client.get(f"/api/sessions/{planned}/routes").json()["routes"]:
        assert len(r["legs"]) == len(r["points"]) - 1
        for leg in r["legs"]:
            assert len(leg["line"]) >= 2


def test_idle_engineers_are_not_returned(client, planned):
    body = client.get(f"/api/sessions/{planned}/routes").json()
    plan = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    working = {rt["engineer_id"] for rt in plan["routes"] if rt["stops"]}
    assert {r["engineer_id"] for r in body["routes"]} == working


def test_routes_before_the_plan_are_409(client, sid):
    assert client.get(f"/api/sessions/{sid}/routes").status_code == 409


def test_leg_line_connects_the_actual_points(client, planned):
    """Проверка `len(line) >= 2` тождественно верна в тестовой среде (geo.line всегда
    отдаёт прямой отрезок из двух точек), поэтому отдельно сверяем сами координаты:
    линия обязана начинаться и заканчиваться в точках самого маршрута, а не где попало."""
    body = client.get(f"/api/sessions/{planned}/routes").json()
    for r in body["routes"]:
        for i, leg in enumerate(r["legs"]):
            frm, to = r["points"][i], r["points"][i + 1]
            assert leg["line"][0] == [frm["lat"], frm["lon"]]
            assert leg["line"][-1] == [to["lat"], to["lon"]]


def test_repeated_pairs_are_fetched_once(client, planned, monkeypatch):
    """Одна и та же пара (a, b, mode) не должна дважды идти в geo.line за один запрос —
    подменяем planning.view синтетическим планом с гарантированно общим отрезком у двух
    инженеров (иначе в реальном сценарии совпадение пар не гарантировано)."""
    from app.routers import geo as geo_router

    calls = []

    def fake_view(con, sid):
        stops = [
            {"request_id": "R001", "seq": 1, "arrive": "09:00", "start": "09:00",
             "finish": "09:30", "locked": False},
            {"request_id": "R002", "seq": 2, "arrive": "10:00", "start": "10:00",
             "finish": "10:30", "locked": False},
        ]
        route = lambda eid, name: {  # noqa: E731
            "engineer_id": eid, "name": name, "transport": "car",
            "start": {"node": eid, "label": "депо"}, "available_from": "09:00", "stops": stops,
        }
        return {
            "travel_source": "osrm",      # при оценке по прямой geo.line не зовётся вовсе
            "plan": {"routes": [route("E01", "Иванов"), route("E02", "Петров")]},
            "engineers": {
                "E01": {"id": "E01", "name": "Иванов", "transport": "car", "lat": 55.0, "lon": 37.0,
                       "start": "депо"},
                "E02": {"id": "E02", "name": "Петров", "transport": "car", "lat": 55.0, "lon": 37.0,
                       "start": "депо"},
            },
            "requests": {
                "R001": {"id": "R001", "lat": 55.1, "lon": 37.1, "address": "Адрес 1"},
                "R002": {"id": "R002", "lat": 55.2, "lon": 37.2, "address": "Адрес 2"},
            },
        }

    def fake_line(a, b, mode):
        calls.append((a, b, mode))
        return [a, b]

    monkeypatch.setattr(geo_router.planning, "view", fake_view)
    monkeypatch.setattr(geo_router.geo, "line", fake_line)

    body = client.get(f"/api/sessions/{planned}/routes").json()

    assert len(body["routes"]) == 2
    # 4 отрезка в ответе (по 2 на инженера), но различных пар — только 2
    assert sum(len(r["legs"]) for r in body["routes"]) == 4
    assert len(calls) == 2


def test_base_plan_current_position_is_the_depot(client, planned):
    depot_by_id = {e["id"]: e for e in client.get(f"/api/sessions/{planned}/engineers").json()}
    for r in client.get(f"/api/sessions/{planned}/routes").json()["routes"]:
        e = depot_by_id[r["engineer_id"]]
        assert r["current"] == {"node": e["id"], "lat": e["start"]["lat"], "lon": e["start"]["lon"],
                                "available_from": e["shift_start"]}


def test_after_replan_route_starts_at_depot_and_current_is_the_last_frozen_stop(client, planned):
    """После перепланирования `points` по-прежнему содержат все замороженные остановки
    с утра, поэтому линия обязана начинаться в депо — иначе теряется переезд депо→первая
    заявка и рисуется прыжок назад. Где инженер сейчас, говорит отдельное поле `current`.
    Сверяем с независимыми источниками: /requests и /engineers, а не с самим /routes."""
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    new = {"lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3",
           "district": "Царицыно", "type": "Нет линка", "skill": "local",
           "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"}
    client.post(f"/api/sessions/{planned}/requests", json=new)
    plan = client.post(f"/api/sessions/{planned}/replan").json()
    frozen = [rt for rt in plan["routes"] if any(s["locked"] for s in rt["stops"])]
    assert frozen, "нечего проверять: перепланирование никого не заморозило"

    depot_by_id = {e["id"]: e for e in client.get(f"/api/sessions/{planned}/engineers").json()}
    request_by_id = {r["id"]: r for r in client.get(f"/api/sessions/{planned}/requests").json()}
    routes_by_id = {r["engineer_id"]: r for r in client.get(f"/api/sessions/{planned}/routes").json()["routes"]}

    for rt in frozen:
        got = routes_by_id[rt["engineer_id"]]
        depot = depot_by_id[rt["engineer_id"]]["start"]
        assert (got["points"][0]["lat"], got["points"][0]["lon"]) == (depot["lat"], depot["lon"])
        last = [s for s in rt["stops"] if s["locked"]][-1]
        where = request_by_id[last["request_id"]]
        assert got["current"] == {"node": last["request_id"], "lat": where["lat"], "lon": where["lon"],
                                  "available_from": rt["available_from"]}


def test_unknown_start_node_is_an_error(client, planned, monkeypatch):
    """Узел старта, который не инженер и не заявка, — несогласованный план; молча рисовать
    инженера в депо нельзя."""
    from app.routers import geo as geo_router

    real = geo_router.planning.view

    def broken(con, sid):
        data = real(con, sid)
        rt = next(rt for rt in data["plan"]["routes"] if rt["stops"])
        rt["start"]["node"] = "R999"
        return data

    monkeypatch.setattr(geo_router.planning, "view", broken)
    with pytest.raises(KeyError):
        client.get(f"/api/sessions/{planned}/routes")


def test_estimated_matrix_draws_straight_legs_without_asking_osrm(client, planned, monkeypatch):
    """Матрица по прямой значит, что OSRM недоступен: спрашивать у него линии незачем."""
    from app.routers import geo as geo_router

    def no_line(a, b, mode):
        raise AssertionError("geo.line не должен вызываться при оценке по прямой")

    monkeypatch.setattr(geo_router.geo, "line", no_line)
    body = client.get(f"/api/sessions/{planned}/routes").json()
    assert body["source"] == "haversine"
    for r in body["routes"]:
        for i, leg in enumerate(r["legs"]):
            frm, to = r["points"][i], r["points"][i + 1]
            assert leg["line"] == [[frm["lat"], frm["lon"]], [to["lat"], to["lon"]]]


def test_routes_survive_cancelling_the_request_in_progress(client, planned):
    """Регресс: отменили заявку, на которой инженер стоит, и перепланировали — он остаётся в её
    точке, а заявки в виде уже нет; карта падала с 500 и пустела."""
    plan = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    rid, eid = next((s["request_id"], rt["engineer_id"]) for rt in plan["routes"] for s in rt["stops"]
                    if s["start"] <= "12:00" < s["finish"])
    assert client.post(f"/api/sessions/{planned}/requests/{rid}/cancel", json={}).status_code == 200
    assert client.post(f"/api/sessions/{planned}/replan").status_code == 200
    r = client.get(f"/api/sessions/{planned}/routes")
    assert r.status_code == 200
    ids = {p["request_id"] for rt in r.json()["routes"] for p in rt["points"]}
    assert rid not in ids

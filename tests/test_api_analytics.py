def test_analytics_compares_with_the_fifo_baseline(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    a = client.get(f"/api/sessions/{sid}/analytics").json()
    cur, base = a["current"], a["baseline"]
    assert cur["total"] == base["total"] == 59
    assert cur["assigned"] >= base["assigned"]
    assert cur["engineers_used"] <= base["engineers_used"]
    assert set(cur["km_per_engineer"]) == set(base["km_per_engineer"])
    assert isinstance(base["expected_late"], float)


def test_hours_and_skills_add_up(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    a = client.get(f"/api/sessions/{sid}/analytics").json()
    assert [x["h"] for x in a["hours"]] == list(range(9, 22))
    assert all(x["on_shift"] >= 0 and x["in_work"] >= 0 for x in a["hours"])
    assert sum(x["assigned"] for x in a["skills"]) == plan["metrics"]["assigned"]
    assert sum(x["total"] for x in a["skills"]) == 59
    assert {x["skill"] for x in a["skills"]} == {"local", "connect", "emergency"}


def test_analytics_needs_a_plan(client, sid):
    assert client.get(f"/api/sessions/{sid}/analytics").status_code == 409


def test_hours_reflect_an_unavailable_engineer(client):
    """on_shift должен учитывать уходы и недоступность, а не номинальную смену из справочника:
    инженер, объявленный недоступным до плана, пропадает из on_shift ровно в те часы, где он был
    бы на смене, и не влияет на часы, где его и так не было."""
    def hours_for(declare_leave: bool) -> list[dict]:
        sid = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
        client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
        if declare_leave:
            client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={})
        client.post(f"/api/sessions/{sid}/plan")
        return client.get(f"/api/sessions/{sid}/analytics").json()["hours"]

    before, after = hours_for(False), hours_for(True)
    changed = 0
    for b, a in zip(before, after):
        assert a["on_shift"] in (b["on_shift"], b["on_shift"] - 1)
        assert a["in_work"] <= a["on_shift"]
        changed += a["on_shift"] == b["on_shift"] - 1
    assert changed > 0, "E01 должен быть на смене хотя бы в один час дня"


def test_hours_reflect_a_break(client):
    """Час, целиком занятый перерывом, инженер не на смене; частичный перерыв час не снимает."""
    def hours_for(brk: dict | None) -> list[dict]:
        sid = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
        client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
        if brk:
            client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={"mode": "break", **brk})
        client.post(f"/api/sessions/{sid}/plan")
        return {x["h"]: x["on_shift"] for x in client.get(f"/api/sessions/{sid}/analytics").json()["hours"]}

    before = hours_for(None)
    full = hours_for({"time": "13:00", "until": "15:00"})
    part = hours_for({"time": "13:30", "until": "14:00"})
    assert {h: before[h] - full[h] for h in before} == {h: int(h in (13, 14)) for h in before}
    assert part == before


def test_load_splits_each_shift(client, sid):
    """Загрузка: работа + дорога + ожидание + перерыв не больше смены; итоги дороги и ожидания сходятся
    с маршрутами; у инженера без заявок вся смена свободна. Для базового — те же поля."""
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    a = client.get(f"/api/sessions/{sid}/analytics").json()
    for key in ("current", "baseline"):
        load = a[key]["load"]
        assert len(load) == 12
        for x in load.values():
            assert x["work"] + x["travel"] + x["wait"] + x["break"] <= x["shift"]
        assert a[key]["travel_min"] == sum(x["travel"] for x in load.values())
        assert a[key]["wait_min"] == sum(x["wait"] for x in load.values())
    routes = {rt["engineer_id"]: rt for rt in plan["routes"]}
    for k, x in a["current"]["load"].items():
        assert x["travel"] == routes[k]["total_travel_min"]
        if not routes[k]["stops"]:
            assert (x["work"], x["travel"], x["wait"]) == (0, 0, 0) and x["shift"] > 0


def test_load_follows_leave_and_break(client):
    """Ушедший инженер — смена до ухода; перерыв — отдельной частью смены."""
    sid = client.post("/api/sessions", json={"scenario": "normal"}).json()["session_id"]
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={"mode": "break", "time": "13:00", "until": "14:00"})
    client.post(f"/api/sessions/{sid}/engineers/E02/unavailable", json={"time": "15:00"})
    client.post(f"/api/sessions/{sid}/plan")
    load = client.get(f"/api/sessions/{sid}/analytics").json()["current"]["load"]
    assert load["E01"]["break"] == 60
    assert load["E02"]["shift"] < load["E03"]["shift"]


def test_slack_and_windows(client, sid):
    """Запас по времени и приезд в окно — по каждой остановке обоих планов."""
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    plan = client.post(f"/api/sessions/{sid}/plan").json()
    a = client.get(f"/api/sessions/{sid}/analytics").json()
    cur, base = a["current"], a["baseline"]
    assert len(cur["tol"]) == len(cur["windows"]) == plan["metrics"]["assigned"]
    assert len(base["tol"]) == len(base["windows"]) == base["assigned"]
    assert cur["tol"] == sorted(cur["tol"]) and min(cur["tol"]) >= 0
    for w in cur["windows"] + base["windows"]:
        assert w["len"] > 0 and w["off"] <= w["len"]
    assert a["now"] is None


def test_slack_after_replan_counts_only_what_is_ahead(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    client.put(f"/api/sessions/{sid}/clock", json={"time": "14:00"})
    client.post(f"/api/sessions/{sid}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{sid}/replan")
    a = client.get(f"/api/sessions/{sid}/analytics").json()
    assert a["now"] == "14:00"
    assert len(a["current"]["tol"]) < len(a["current"]["windows"])
    assert len(a["baseline"]["tol"]) <= len(a["baseline"]["windows"])
    assert a["current"]["load"]["E01"]["shift"] < a["current"]["load"]["E02"]["shift"]
    h = client.get(f"/api/sessions/{sid}/history").json()
    assert [x["kind"] for x in h] == ["base", "replan"]
    assert all(isinstance(x["engineers_used"], int) for x in h)

import json
from pathlib import Path

import pytest

from app import scenarios

NORMAL = Path(__file__).resolve().parent.parent / "data" / "scenarios" / "normal.json"
CSV = ("id;lat;lon;address;district;type;work_type;tw_start;tw_end\n"
       "R1;55.617;37.660;Царицыно, ул. Бакинская, 3;Царицыно;Нет линка;local_repair;10:00;12:00\n"
       ";55.60;37.66;Бирюлёво, Харьковская, 5;Бирюлёво Западное;Обрыв магистрали;emergency;13:00;15:00\n")


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(scenarios, "UPLOADED", tmp_path / "scenarios")


def test_csv_of_requests_becomes_a_scenario(client):
    r = client.post("/api/scenarios/upload", json={"filename": "day.csv", "content": CSV, "title": "Мой день"})
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["uploaded"] is True and card["id"].startswith("u-")
    assert (card["title"], card["requests"], card["engineers"]) == ("Мой день", 2, 12)
    sid = client.post("/api/sessions", json={"scenario": card["id"]}).json()["session_id"]
    reqs = client.get(f"/api/sessions/{sid}/requests").json()
    assert [x["id"] for x in reqs] == ["R1", "R002"]
    assert reqs[1]["skill"] == "emergency" and reqs[1]["duration_min"] == 80
    assert card["id"] in {x["id"] for x in client.get("/api/scenarios").json()}


def test_full_json_is_accepted(client):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    del d["config"], d["dictionaries"]
    r = client.post("/api/scenarios/upload", json={"filename": "x.json", "content": json.dumps(d, ensure_ascii=False)})
    assert r.status_code == 200
    assert r.json()["requests"] == 59


@pytest.mark.parametrize("content,needle", [
    ("{не json", "не удалось прочитать"),
    ("id;lat\nR1;55.6\n", "нет колонок"),
    ("lat;lon;address;district;type;work_type;tw_start;tw_end\n55.6;37.6;a;b;c;local_repair;18:00;10:00\n",
     "строка 2: конец окна должен быть позже начала"),
    ("lat;lon;address;district;type;work_type;tw_start;tw_end\n59.9;30.3;a;b;c;local_repair;10:00;12:00\n",
     "строка 2: точка вне Московской агломерации"),
    ("lat;lon;address;district;type;work_type;tw_start;tw_end\n55.6;37.6;a;b;c;welding;10:00;12:00\n",
     "строка 2: неизвестный вид работ welding"),
])
def test_broken_files_are_explained(client, content, needle):
    name = "x.json" if content.startswith("{") else "x.csv"
    r = client.post("/api/scenarios/upload", json={"filename": name, "content": content})
    assert r.status_code == 422
    body = r.json()["detail"]
    assert needle in body["message"] + " " + " ".join(body["errors"])
    assert not any(x["uploaded"] for x in client.get("/api/scenarios").json())


def test_cp1251_csv_is_read(client):
    raw = CSV.encode("cp1251").decode("latin-1")            # браузер прочитал файл не в той кодировке
    r = client.post("/api/scenarios/upload", json={"filename": "d.csv", "content": raw})
    assert r.status_code == 200


def test_json_engineers_are_validated(client):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    del d["engineers"][0]["skills"]
    del d["engineers"][1]["start"]["lon"]
    r = client.post("/api/scenarios/upload", json={"filename": "x.json", "content": json.dumps(d, ensure_ascii=False)})
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert "инженер 1: нет поля skills" in errors
    assert "инженер 2: нет поля start.lon" in errors


@pytest.mark.parametrize("bad_lat", [None, [1, 2]])
def test_json_bad_lat_type_is_reported_not_500(client, bad_lat):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    d["requests"][0]["lat"] = bad_lat
    r = client.post("/api/scenarios/upload", json={"filename": "x.json", "content": json.dumps(d, ensure_ascii=False)})
    assert r.status_code == 422
    assert "координаты должны быть числами" in " ".join(r.json()["detail"]["errors"])


def test_json_engineer_must_be_an_object(client):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    d["engineers"][0] = "не объект"
    r = client.post("/api/scenarios/upload", json={"filename": "x.json", "content": json.dumps(d, ensure_ascii=False)})
    assert r.status_code == 422
    assert "инженер 1: должен быть объектом" in r.json()["detail"]["errors"]


def test_json_request_must_be_an_object(client):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    d["requests"][0] = "не объект"
    r = client.post("/api/scenarios/upload", json={"filename": "x.json", "content": json.dumps(d, ensure_ascii=False)})
    assert r.status_code == 422
    assert "строка 1: должна быть объектом" in r.json()["detail"]["errors"]


def test_broken_uploaded_file_does_not_break_listing(client):
    scenarios.UPLOADED.mkdir(parents=True, exist_ok=True)
    (scenarios.UPLOADED / "u-garbage.json").write_text("{не json", encoding="utf-8")
    (scenarios.UPLOADED / "u-partial.json").write_text(json.dumps({"id": "u-partial"}), encoding="utf-8")
    ids = {r["id"] for r in client.get("/api/scenarios").json()}
    assert {"normal", "peak", "short-staffed"} <= ids
    assert "u-garbage" not in ids and "u-partial" not in ids


def test_comma_delimited_csv_is_accepted(client):
    content = ("id,lat,lon,address,district,type,work_type,tw_start,tw_end\n"
               "R1,55.617,37.660,Царицыно,Царицыно,Нет линка,local_repair,10:00,12:00\n")
    r = client.post("/api/scenarios/upload", json={"filename": "day.csv", "content": content})
    assert r.status_code == 200, r.text
    assert r.json()["requests"] == 1


def _upload(client, d):
    return client.post("/api/scenarios/upload", json={"filename": "x.json", "content": json.dumps(d, ensure_ascii=False)})


def _say(r):
    body = r.json()["detail"]
    return body["message"] + " " + " ".join(body["errors"])


@pytest.mark.parametrize("patch,needle", [
    ({"config": "x"}, "config должен быть объектом"),
    ({"config": [1, 2]}, "config должен быть объектом"),
    ({"dictionaries": "x"}, "dictionaries должен быть объектом"),
    ({"dictionaries": {"skills": {}}}, "в dictionaries нет norms"),
    ({"dictionaries": {"norms": "x"}}, "в dictionaries нет norms"),
    ({"dictionaries": {"norms": {"local_repair": {"label": "x"}}}}, "норматив local_repair: нужны числа"),
])
def test_json_config_and_dictionaries_must_be_objects(client, patch, needle):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    d.update(patch)
    r = _upload(client, d)
    assert r.status_code == 422, r.text
    assert needle in _say(r)
    assert not any(x["uploaded"] for x in client.get("/api/scenarios").json())


def test_json_partial_config_falls_back_to_the_base_scenario(client):
    """Частичный config не ломает сессию: недостающее берётся из базового сценария."""
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    d["config"] = {"weights": d["config"]["weights"]}
    r = _upload(client, d)
    assert r.status_code == 200, r.text
    sid = client.post("/api/sessions", json={"scenario": r.json()["id"]}).json()["session_id"]
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    assert client.post(f"/api/sessions/{sid}/variants").status_code == 200


def test_json_norm_without_a_known_skill_is_reported(client):
    d = json.loads(NORMAL.read_text(encoding="utf-8"))
    d["dictionaries"]["norms"]["welding"] = {"label": "Сварка", "road_min": 20, "tech_min": 30, "docs_min": 0}
    d["requests"][0]["work_type"] = "welding"
    r = _upload(client, d)
    assert r.status_code == 422
    assert "строка 1: неизвестный вид работ welding" in _say(r)

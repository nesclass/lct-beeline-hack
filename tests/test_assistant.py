import json
from types import SimpleNamespace

import pytest

from planner import llm


@pytest.fixture
def planned(client, sid):
    client.put(f"/api/sessions/{sid}/settings", json={"engine": "greedy", "time_limit": 3})
    client.post(f"/api/sessions/{sid}/plan")
    return sid


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: False))


def _ask(client, sid, kind, question, **ctx):
    return client.post(f"/api/sessions/{sid}/assistant",
                       json={"context": {"kind": kind, **ctx}, "question": question}).json()


def _assigned_with_alternative(client, sid):
    plan = client.get(f"/api/sessions/{sid}/plan").json()["plan"]
    for rid, a in plan["assignments"].items():
        if a["engineer_id"] and not a.get("locked"):
            alt = next((x for x in a["reason"]["alternatives"] if x["feasible"]), None)
            if alt:
                return rid, a["engineer_id"], alt["engineer_id"]
    raise AssertionError("нет заявки с допустимой альтернативой")


def test_template_answer_about_a_request(client, planned, no_llm):
    rid, owner, alt = _assigned_with_alternative(client, planned)
    r = _ask(client, planned, "request", "Почему так?", id=rid)
    assert r["source"] == "template"
    assert rid in r["label"] and "план на 17.08" in r["label"]
    assert {"навык", "транспорт", "окно", "смена"} <= set(r["tools"])
    assert any(row["engineer_id"] == owner for row in r["rows"])
    assert r["action"] is None
    assert r["suggestions"] == ["Где риск опоздания?", "Кто загружен сильнее всех?"]


def test_template_proposes_a_move_when_asked_by_name(client, planned, no_llm):
    rid, owner, alt = _assigned_with_alternative(client, planned)
    name = next(e["name"] for e in client.get(f"/api/sessions/{planned}/engineers").json() if e["id"] == alt)
    r = _ask(client, planned, "request", f"Отдай её {name}у", id=rid)
    assert r["action"] == {"kind": "move", "request_id": rid, "engineer_id": alt, "title": f"Переназначить {rid} → {name}"}
    assert client.get(f"/api/sessions/{planned}").json()["pending_events"] == [], "ассистент сам ничего не пишет"


def test_template_about_an_engineer_uses_the_preview(client, planned, no_llm):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    r = _ask(client, planned, "engineer", "Что будет?", id="E01", params={"mode": "leave", "time": "13:00"})
    pre = client.post(f"/api/sessions/{planned}/preview/unavailable/E01", json={"mode": "leave", "time": "13:00"}).json()
    assert {row["name"] for row in r["rows"]} == {x["request_id"] for x in pre["released"]}
    assert "инженер Горбанев" in r["label"]


def test_unknown_engineer_id_is_404(client, planned):
    resp = client.post(f"/api/sessions/{planned}/assistant",
                       json={"context": {"kind": "engineer", "id": "E99"}, "question": "Что будет?"})
    assert resp.status_code == 404


def test_invalid_engineer_params_are_422(client, planned):
    resp = client.post(f"/api/sessions/{planned}/assistant",
                       json={"context": {"kind": "engineer", "id": "E01", "params": {"mode": "xx"}}, "question": "Что?"})
    assert resp.status_code == 422


def test_engineer_time_before_the_clock_falls_back_to_the_template(client, planned, no_llm):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "13:00"})
    r = _ask(client, planned, "engineer", "Что будет?", id="E01", params={"mode": "leave", "time": "12:00"})
    assert r["source"] == "template"
    assert r["text"].startswith("Не смог посчитать последствия:")
    assert r["tools"] == [] and r["rows"] == []


def test_template_about_changes_and_analytics(client, planned, no_llm):
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={})
    client.post(f"/api/sessions/{planned}/requests", json={
        "lat": 55.617, "lon": 37.660, "address": "Царицыно, ул. Бакинская, д. 3", "district": "Царицыно",
        "type": "Нет линка", "skill": "local", "work_type": "local_repair", "tw_start": "15:00", "tw_end": "17:00"})
    client.post(f"/api/sessions/{planned}/replan")
    ch = _ask(client, planned, "changes", "Коротко: что поменялось?")
    assert ch["label"] == "перепланирование от 12:00"
    assert [row["name"] for row in ch["rows"]] == ["Назначено", "Инженеров", "Пробег, км"]
    an = _ask(client, planned, "analytics", "Чем наш план лучше базового?")
    assert [row["name"] for row in an["rows"]] == ["Инженеров", "Пробег, км", "Не назначено"]
    assert "базов" in an["text"].lower()


def test_proxy_failure_falls_back_to_the_template(client, planned, monkeypatch):
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: True))
    monkeypatch.setattr(llm.Narrator, "_completion", lambda self, messages, **kw: None)
    r = _ask(client, planned, "plan", "Что не назначено?")
    assert r["source"] == "template"
    assert r["text"] and "Ошибка" not in r["text"]


def test_llm_empty_reply_falls_back_to_the_template(client, planned, monkeypatch):
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: True))
    monkeypatch.setattr(llm.Narrator, "_completion", lambda self, messages, **kw: _reply(content="   "))
    r = _ask(client, planned, "plan", "Что не назначено?")
    assert r["source"] == "template"
    assert r["text"]


class _Call:
    def __init__(self, name, args):
        self.id, self.function = "c1", SimpleNamespace(name=name, arguments=json.dumps(args))

    def model_dump(self):
        return {"id": self.id, "type": "function", "function": {"name": self.function.name, "arguments": self.function.arguments}}


def _reply(content=None, calls=None):
    msg = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=None)


def test_llm_move_proposal_is_checked_and_returned(client, planned, monkeypatch):
    rid, owner, alt = _assigned_with_alternative(client, planned)
    script = iter([_reply(calls=[_Call("propose_move", {"request_id": rid, "engineer_id": alt})]),
                   _reply(content="Можно: опозданий не будет.")])
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: True))
    monkeypatch.setattr(llm.Narrator, "_completion", lambda self, messages, **kw: next(script))
    r = _ask(client, planned, "request", "Отдай другому", id=rid)
    assert r["source"] == "llm"
    assert r["text"] == "Можно: опозданий не будет."
    assert "проверка переноса" in r["tools"]
    assert r["action"]["engineer_id"] == alt


def test_llm_cannot_propose_an_impossible_move(client, planned, monkeypatch):
    plan = client.get(f"/api/sessions/{planned}/plan").json()["plan"]
    rid, a = next((rid, a) for rid, a in plan["assignments"].items()
                  if a["engineer_id"] and any(not x["feasible"] and x["blocker"]["code"] == "SKILL"
                                              for x in a["reason"].get("alternatives", [])))
    bad = next(x["engineer_id"] for x in a["reason"]["alternatives"] if not x["feasible"] and x["blocker"]["code"] == "SKILL")
    script = iter([_reply(calls=[_Call("propose_move", {"request_id": rid, "engineer_id": bad})]),
                   _reply(content="Не получится.")])
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: True))
    monkeypatch.setattr(llm.Narrator, "_completion", lambda self, messages, **kw: next(script))
    assert _ask(client, planned, "request", "Отдай", id=rid)["action"] is None


def test_assistant_on_variants(client, planned):
    client.post(f"/api/sessions/{planned}/variants")
    got = client.get(f"/api/sessions/{planned}/variants").json()
    r = _ask(client, planned, "variants", "Что посоветуешь?")
    assert r["source"] == "template"
    assert len(r["rows"]) == 4
    assert r["text"] == got["text"]


def test_diff_bundle_understands_every_event_type():
    from planner.reasoning import bundle_diff
    from planner.model import Problem
    ds = json.load(open("data/scenarios/normal.json", encoding="utf-8"))
    p = Problem.from_dataset(ds)
    plan = {"diff": {"requests": {}, "engineers": {}, "summary": {"delta_total_km": 0, "delta_engineers_used": 0}},
            "events": [{"type": "new_request", "time": "12:00", "request_id": "R001"},
                       {"type": "move_request", "time": "12:00", "request_id": "R001", "engineer_id": "E02"},
                       {"type": "engineer_break", "time": "13:00", "until": "14:00", "engineer_id": "E01"}],
            "routes": [], "now": "12:00", "metrics": {}, "assignments": {}}
    assert [e["type"] for e in bundle_diff(plan, p)["events"]] == ["новая заявка", "перенос заявки", "перерыв"]


def test_assistant_on_variants_without_a_risk_estimate(monkeypatch, client, planned):
    """Оценка риска не посчиталась (assess_safe → None) — ассистент не падает, а говорит «нет оценки»."""
    from app import planning
    monkeypatch.setattr(planning, "assess_safe", lambda *a, **k: None)
    client.post(f"/api/sessions/{planned}/variants")
    resp = client.post(f"/api/sessions/{planned}/assistant",
                       json={"context": {"kind": "variants"}, "question": "Что посоветуешь?"})
    assert resp.status_code == 200, resp.text
    assert all(r["v"] == "нет оценки" for r in resp.json()["rows"])


def test_llm_about_an_engineer_gets_the_hypothetical_leave(client, planned, monkeypatch):
    """Окно «Недоступность» → «Спросить ассистента»: модель должна видеть не текущий план, а посчитанные
    последствия ещё не применённого ухода — и проверять другие варианты функцией."""
    seen, calls = [], []
    script = iter([_reply(calls=[_Call("preview_unavailable", {"mode": "leave", "time": "16:00"})]),
                   _reply(content="Если уйдёт в 13:00 — две заявки уйдут Демину.")])

    def completion(self, messages, **kw):
        seen.append(json.dumps(messages, ensure_ascii=False, default=str))
        calls.append(kw.get("tools"))
        return next(script)

    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: True))
    monkeypatch.setattr(llm.Narrator, "_completion", completion)
    preview = client.post(f"/api/sessions/{planned}/preview/unavailable/E01", json={"mode": "leave", "time": "13:00"})
    assert preview.status_code == 200
    r = _ask(client, planned, "engineer", "Что будет?", id="E01", params={"mode": "leave", "time": "13:00"})
    assert r["source"] == "llm"
    first = seen[0]
    assert "НЕ применил" in first and "уходит с 13:00" in first
    assert preview.json()["released"], "у E01 после 13:00 должны быть заявки — иначе тест ничего не проверяет"
    for x in preview.json()["released"]:
        assert x["request_id"] in first
    assert any(t["function"]["name"] == "preview_unavailable" for t in calls[0])
    # ответ функции — последствия для 16:00, а не для 13:00
    tool_msg = next(m for m in json.loads(seen[1]) if m.get("role") == "tool")
    assert json.loads(tool_msg["content"])["leave"] == "16:00"
    assert "проверка недоступности" in r["tools"]
    assert [row["name"] for row in r["rows"]] == [row["name"] for row in
                                                  _ask_template(client, planned, monkeypatch)["rows"]]


def _ask_template(client, sid, monkeypatch):
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: False))
    return _ask(client, sid, "engineer", "Что будет?", id="E01", params={"mode": "leave", "time": "13:00"})


def test_follow_up_questions_come_from_the_model_and_skip_asked_ones():
    from app.assistant import split_next
    text, qs = split_next("Освободятся две заявки.\n\nДАЛЕЕ: А если в 16:00? | Кто возьмёт R024? | Что будет?",
                          {"что будет?"})
    assert text == "Освободятся две заявки."
    assert qs == ["А если в 16:00?", "Кто возьмёт R024?"]
    assert split_next("Без подсказок.", set()) == ("Без подсказок.", [])
    assert split_next("Ответ.\n**ДАЛЕЕ:** «Первый вопрос?» | «Второй?»", set())[1] == ["Первый вопрос?", "Второй?"]


def test_template_suggestions_drop_the_question_just_asked(client, planned, no_llm):
    r = _ask(client, planned, "request", "Где риск опоздания?", id=_assigned_with_alternative(client, planned)[0])
    assert "Где риск опоздания?" not in r["suggestions"]


def test_changes_suggest_the_morning_comparison_only_after_a_replan(client, planned, no_llm):
    r = _ask(client, planned, "changes", "Коротко: что поменялось?")
    assert "Сравнить с утренним планом" not in r["suggestions"]
    assert "Показать на карте" not in r["suggestions"]
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/replan")
    r = _ask(client, planned, "changes", "Коротко: что поменялось?")
    assert "Сравнить с утренним планом" in r["suggestions"]
    m = _ask(client, planned, "changes", "Сравнить с утренним планом")
    assert "пересчитывали 1 раз" in m["text"] and "уходит в 13:00" in m["text"]
    assert [x["name"] for x in m["rows"]] == ["Назначено", "Инженеров", "Пробег, км"]


def test_llm_on_changes_gets_the_day_history(client, planned, monkeypatch):
    seen = []
    monkeypatch.setattr(llm.Narrator, "available", property(lambda self: True))
    monkeypatch.setattr(llm.Narrator, "_completion",
                        lambda self, messages, **kw: seen.append(json.dumps(messages, ensure_ascii=False)) or _reply(content="Ок."))
    client.put(f"/api/sessions/{planned}/clock", json={"time": "12:00"})
    client.post(f"/api/sessions/{planned}/engineers/E01/unavailable", json={"time": "13:00"})
    client.post(f"/api/sessions/{planned}/replan")
    _ask(client, planned, "changes", "Сравнить с утренним планом")
    assert "история плана за день" in seen[0] and "утро, до начала дня" in seen[0]
    assert "последнее перепланирование" in seen[0]

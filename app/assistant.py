"""Ассистент диспетчера. Отвечает по контексту экрана: языковая модель через LiteLLM-прокси с инструментами
над планом, а без ключа или при сбое — шаблоном из тех же структурированных фактов.
Ничего не меняет: перенос он только предлагает, в очередь его кладёт диспетчер."""
from __future__ import annotations

import json
import re
from datetime import date

from planner.llm import Narrator, _fn
from planner.model import Problem, fmt
from planner.reasoning import bundle_diff, bundle_plan, template_diff, template_summary

from . import analytics, planning, store, variants, whatif
from .schema import Unavailable

TOOL_LABEL = {"get_request": "заявка", "why_not": "проверка инженера", "what_if_move": "проверка «что если»",
              "get_engineer_route": "маршрут", "list_unassigned": "неназначенные", "plan_metrics": "метрики",
              "propose_move": "проверка переноса", "preview_unavailable": "проверка недоступности"}
MOVE_WORDS = ("отдай", "передай", "переназнач", "перенеси", "перекинь")


def _day(ds_meta: dict) -> str:
    d = ds_meta.get("date")
    return date.fromisoformat(d).strftime("%d.%m") if d else "сегодня"


def _num(x) -> str:
    return f"{x:g}".replace(".", ",")


def _plural(n: int, one: str, few: str, many: str) -> str:
    n100 = n % 100
    n10 = n % 10
    if 11 <= n100 <= 14:
        return many
    if n10 == 1:
        return one
    if 2 <= n10 <= 4:
        return few
    return many


def label(ctx: dict, view: dict) -> str:
    k = ctx["kind"]
    day = _day(view.get("meta", {}))
    plan = view["plan"]
    if k == "request":
        return f"заявка {ctx['id']} · план на {day}"
    if k == "engineer":
        return f"инженер {view['engineers'][ctx['id']]['name']} · недоступность"
    if k == "changes":
        return f"перепланирование от {plan['now']}" if plan.get("now") else "изменения в очереди"
    if k == "analytics":
        return f"аналитика · план {plan['now'] or 'на день'} и базовый"
    if k == "variants":
        return "варианты плана"
    return f"план на {day}"


def suggestions(ctx: dict, extra: dict) -> list[str]:
    """Шаблонные подсказки — только то, на что ассистент может ответить: extra говорит, есть ли
    с чем сравнивать (раньше «Сравнить с утренним планом» предлагалось и без него)."""
    k = ctx["kind"]
    if k == "request":
        return ["Где риск опоздания?", "Кто загружен сильнее всех?"]
    if k == "engineer":
        first = extra.get("no_taker")
        return ([f"Кто может взять {first}?"] if first else []) + ["Что будет, если он доделает текущую?"]
    if k == "changes":
        if extra.get("replans"):
            return ["Сравнить с утренним планом", "Кому стало тяжелее всех?"]
        if extra.get("pending"):
            return ["Что будет, если перепланировать сейчас?", "Какие заявки останутся без исполнителя?"]
        return ["Что не назначено и почему?", "Где риск опоздания?"]
    if k == "analytics":
        return ["Где ещё можно сэкономить?", "Кто загружен сильнее всех?"]
    return ["Что не назначено и почему?", "Где риск опоздания?"]


NEXT = "ДАЛЕЕ:"
NEXT_NOTE = (f"\n\nВ самом конце ответа отдельной строкой напиши «{NEXT}» и 2–3 коротких вопроса, которые диспетчер "
             "естественно задаст следующими именно по этой ситуации и твоему ответу (от его лица, до 60 знаков, "
             "через « | »). Только такие, на которые ты сможешь ответить по фактам выше и своим функциям; "
             "не повторяй уже заданные и не спрашивай то, на что ответ уже есть выше (перечислил освободившиеся "
             "заявки — не предлагай «какие заявки освободятся?»); лучше на шаг дальше: другое время, другой "
             "инженер, нагрузка, риск опоздания. Ты отвечаешь только текстом: не предлагай показать на карте, "
             "открыть экран, выгрузить. Не предлагай действий "
             "(«применить», «отправить») — только вопросы.")


def _asked(history: list) -> set[str]:
    """Вопросы, которые диспетчер уже задавал: к тексту вопроса в истории приписан контекст экрана."""
    return {str(m.get("content") or "").split("\n\n")[0].strip().lower()
            for m in history if isinstance(m, dict) and m.get("role") == "user"}


def split_next(text: str, asked: set[str]) -> tuple[str, list[str]]:
    """Ответ модели → (текст без строки «ДАЛЕЕ:», предложенные следующие вопросы)."""
    m = re.search(rf"\n?[ \t*_]*{NEXT}\s*(.+?)\s*$", text, flags=re.S)
    if not m:
        return text.strip(), []
    qs = [q.strip(" \t*_«»\"-") for q in re.split(r"\s*\|\s*|\n", m.group(1))]
    qs = [q for q in dict.fromkeys(qs) if 3 <= len(q) <= 80 and q.lower() not in asked]
    return text[:m.start()].strip(), qs[:3]


def _fresh(qs: list[str], asked: set[str]) -> list[str]:
    return [q for q in qs if q.lower() not in asked]


def _mentioned(question: str, view: dict) -> str | None:
    """Инженер, названный в вопросе по фамилии (первые пять букв — «Демину» → Демин)."""
    q = question.lower()
    hits = [k for k, e in view["engineers"].items() if e["name"].lower()[:5] in q]
    return hits[0] if len(hits) == 1 else None


def _move_action(con, sid: str, rid: str, eid: str, view: dict) -> dict | None:
    if whatif.check_move(con, sid, rid, eid):
        return None
    return {"kind": "move", "request_id": rid, "engineer_id": eid,
            "title": f"Переназначить {rid} → {view['engineers'][eid]['name']}"}


# -- шаблоны -----------------------------------------------------------------------------
def _t_request(con, sid, ctx, question, view) -> dict:
    rid = ctx["id"]
    plan = view["plan"]
    a = plan["assignments"].get(rid)
    names = {k: e["name"] for k, e in view["engineers"].items()}
    if a is None:
        return {"text": "Заявка заведена после расчёта — план её ещё не рассматривал. Она попадёт в расписание при перепланировании.",
                "tools": [], "rows": [], "action": None}
    if a.get("locked"):
        return {"text": a["text"], "tools": [], "rows": [], "action": None}
    if not a["engineer_id"]:
        return {"text": a["text"], "tools": ["навык", "транспорт", "окно", "смена"], "rows": [], "action": None}
    r, k = a["reason"], a["engineer_id"]
    feas = sorted((x for x in r["alternatives"] if x["feasible"]), key=lambda x: x["delta_km"])
    pos = r["position"]
    between = (f"между {pos['prev_request_id']} и {pos['next_request_id']}" if pos["prev_request_id"] and pos["next_request_id"]
               else "в начало маршрута" if not pos["prev_request_id"] else "в конец маршрута")
    text = (f"{names[k]} подходит по навыку и транспорту и успевает в окно. Вставка {between} "
            f"добавляет {_num(r['delta_km'])} км.")
    if feas:
        x = feas[0]
        text += f" {names[x['engineer_id']]} тоже может, но +{_num(x['delta_km'])} км."
    else:
        text += " Других подходящих свободных инженеров нет."
    rows = [{"name": names[k], "engineer_id": k, "a": f"приезд {r['arrive']}", "v": f"+{_num(r['delta_km'])} км", "tone": "ok"}]
    rows += [{"name": names[x["engineer_id"]], "engineer_id": x["engineer_id"], "a": f"приезд {x['arrive']}",
              "v": f"+{_num(x['delta_km'])} км", "tone": "warn"} for x in feas[:2]]
    action = None
    if any(w in question.lower() for w in MOVE_WORDS):
        target = _mentioned(question, view) or (feas[0]["engineer_id"] if feas else None)
        if target and target != k:
            action = _move_action(con, sid, rid, target, view)
    return {"text": text, "tools": ["навык", "транспорт", "окно", "смена"], "rows": rows, "action": action}


def _t_engineer(con, sid, ctx, question, view) -> dict:
    eid = ctx["id"]
    body = Unavailable(**(ctx.get("params") or {}))
    pre = whatif.unavailable_preview(con, sid, eid, body)
    name = view["engineers"][eid]["name"]
    cur = pre["current"]
    parts = []
    if cur:
        parts.append(f"Текущую {cur['request_id']} он успевает закончить к {cur['finish']}.")
    n, can = len(pre["released"]), pre["can_take"]
    if n:
        takers = sorted({x["taker"]["name"] for x in pre["released"] if x["taker"]})
        miss = [x["request_id"] for x in pre["released"] if not x["taker"]]
        noun = _plural(n, "заявка", "заявки", "заявок")
        verb = "Освободится" if noun == "заявка" else "Освободятся"
        parts.append(f"{verb} {n} {noun}: {can} могут взять {', '.join(takers) or 'никто'}"
                     + (f", для {', '.join(miss)} свободного инженера с нужным навыком на это время нет." if miss else "."))
    else:
        parts.append(f"У {name} после {pre['leave']} заявок нет — расписание не пострадает.")
    rows = [{"name": x["request_id"], "engineer_id": x["taker"]["engineer_id"] if x["taker"] else None,
             "a": x["taker"]["name"] if x["taker"] else "—", "v": "можно" if x["taker"] else "нет",
             "tone": "ok" if x["taker"] else "bad"} for x in pre["released"]]
    extra = {"no_taker": next((x["request_id"] for x in pre["released"] if not x["taker"]), None)}
    return {"text": " ".join(parts), "tools": ["навык", "окно", "смена"], "rows": rows, "action": None, "extra": extra}


def _t_morning(con, sid, view) -> dict | None:
    chain = planning.history(con, sid)
    if len(chain) < 2:
        return None
    a, b = chain[0], chain[-1]
    names = {k: e["name"] for k, e in view["engineers"].items()}
    evs = [_event_short(e, names) for h in chain[1:] for e in h["events"]]
    n = len(chain) - 1
    text = (f"С утра план пересчитывали {n} {_plural(n, 'раз', 'раза', 'раз')}: {', '.join(evs) or 'без событий'}. "
            f"Назначено {a['assigned']} из {a['total']} → {b['assigned']} из {b['total']}, инженеров {a['engineers_used']} → "
            f"{b['engineers_used']}, пробег {_num(a['total_km'])} → {_num(b['total_km'])} км.")
    rows = [{"name": "Назначено", "a": f"{a['assigned']} → ", "v": str(b["assigned"]), "tone": "ink"},
            {"name": "Инженеров", "a": f"{a['engineers_used']} → ", "v": str(b["engineers_used"]), "tone": "ink"},
            {"name": "Пробег, км", "a": f"{_num(a['total_km'])} → ", "v": _num(b["total_km"]),
             "tone": "ok" if b["total_km"] <= a["total_km"] else "warn"}]
    return {"text": text, "tools": ["история плана"], "rows": rows, "action": None}


def _t_changes(con, sid, ctx, question, view, p) -> dict:
    plan = view["plan"]
    if "утрен" in question.lower() or "базов" in question.lower():
        got = _t_morning(con, sid, view)
        if got:
            return got
        return {"text": "Сегодня план ещё не пересчитывали — текущий и есть утренний.", "tools": ["история плана"],
                "rows": [], "action": None}
    if not plan.get("diff"):
        imp = whatif.impact(con, sid)
        if imp["since"] is None:
            return {"text": "Изменений в очереди нет, перепланирования ещё не было.",
                    "tools": ["сравнение планов"], "rows": [], "action": None}
        return {"text": f"В очереди изменения с {imp['since']}. Если оставить план как есть, без исполнителя останутся "
                        f"{len(imp['orphaned'])} заявок, срочных без исполнителя — {imp['urgent_unassigned']}.",
                "tools": ["сравнение планов"], "rows": [], "action": None}
    prev = view["previous"]
    before = prev["metrics"]
    m = plan["metrics"]
    rows = [{"name": "Назначено", "a": f"{before['assigned']} → ", "v": str(m["assigned"]), "tone": "ink"},
            {"name": "Инженеров", "a": f"{before['engineers_used']} → ", "v": str(m["engineers_used"]), "tone": "ink"},
            {"name": "Пробег, км", "a": f"{_num(before['total_km'])} → ", "v": _num(m["total_km"]),
             "tone": "ok" if m["total_km"] <= before["total_km"] else "warn"}]
    return {"text": template_diff(bundle_diff(plan, p)), "tools": ["сравнение планов"], "rows": rows, "action": None}


def _t_analytics(con, sid, ctx, question, view) -> dict:
    a = analytics.report(con, sid)
    c, b = a["current"], a["baseline"]
    save = round((1 - c["total_km"] / b["total_km"]) * 100) if b["total_km"] else 0
    text = (f"Базовый вариант назначает по порядку поступления и задействует {b['engineers_used']} инженеров "
            f"на {_num(b['total_km'])} км. Наш — {c['engineers_used']} инженеров и {_num(c['total_km'])} км"
            + (f": {b['engineers_used'] - c['engineers_used']} остаются в резерве" if b["engineers_used"] > c["engineers_used"] else "")
            + (f", пробег меньше на {save} %." if save > 0 else "."))
    tone = lambda better: "ok" if better else "warn"
    rows = [{"name": "Инженеров", "a": f"{b['engineers_used']} → ", "v": str(c["engineers_used"]), "tone": tone(c["engineers_used"] <= b["engineers_used"])},
            {"name": "Пробег, км", "a": f"{_num(b['total_km'])} → ", "v": _num(c["total_km"]), "tone": tone(c["total_km"] <= b["total_km"])},
            {"name": "Не назначено", "a": f"{b['unassigned']} → ", "v": str(c["unassigned"]), "tone": tone(c["unassigned"] <= b["unassigned"])}]
    return {"text": text, "tools": ["базовый план", "метрики"], "rows": rows, "action": None}


def _template(con, sid, ctx, question, view, p) -> dict:
    k = ctx["kind"]
    if k == "request":
        return _t_request(con, sid, ctx, question, view)
    if k == "engineer":
        return _t_engineer(con, sid, ctx, question, view)
    if k == "changes":
        return _t_changes(con, sid, ctx, question, view, p)
    if k == "analytics":
        return _t_analytics(con, sid, ctx, question, view)
    return {"text": template_summary(bundle_plan(view["plan"], p)), "tools": ["метрики"], "rows": [], "action": None}


# -- языковая модель ------------------------------------------------------------------------------
def _screen_note(ctx: dict, lbl: str) -> str:
    return (f"\n\nДиспетчер сейчас смотрит: {lbl}. Контекст экрана: {json.dumps(ctx, ensure_ascii=False)}. "
            "Если он просит переназначить заявку, вызови propose_move — функция проверит допустимость; "
            "сам ты ничего не меняешь: предложение появится у диспетчера кнопкой.")


MODE_TEXT = {"leave": "уходит", "absent": "не выйдет сегодня", "break": "уходит на перерыв"}


def _hypothesis(pre: dict, name: str, body: Unavailable, clock: str) -> str:
    """Гипотетическая недоступность из окна «Недоступность» — фактами для модели. Без этого модель видела
    только текущий план и отвечала о нём, а не о том, что будет после ухода."""
    when = ("на весь день" if body.mode == "absent"
            else f"с {pre['leave']}" + (f" до {pre['until']}" if pre.get("until") else ""))
    cur = pre["current"]
    facts = {"сейчас": f"{clock} — раньше этого уйти нельзя", "инженер": name, "событие": f"{MODE_TEXT[body.mode]} {when}",
             "текущая заявка": (f"{cur['request_id']}, успевает закончить к {cur['finish']}" if cur else "нет"),
             "освободятся": [{"заявка": x["request_id"], "окно": x["window"],
                              "может взять": x["taker"]["name"] if x["taker"] else "никто — нет свободного с нужным навыком"}
                             for x in pre["released"]],
             "нагрузка тех, кто берёт": [{"инженер": x["name"], "получит": x["added"],
                                          "заявок было → станет": f"{x['stops_before']} → {x['stops_after']}",
                                          "пробег, км было → станет": f"{x['km_before']} → {x['km_after']}",
                                          "последняя заявка кончится было → станет": f"{x['finish_before'] or '—'} → {x['finish_after']}"}
                                         for x in pre.get("takers", [])]}
    return ("\n\nВАЖНО: диспетчер ещё НЕ применил событие — он заполняет окно «Недоступность» и спрашивает, "
            "что будет, ЕСЛИ оно случится. Отвечай о последствиях этого гипотетического события, а не о текущем "
            "плане. Последствия уже посчитаны по актуальному плану: "
            + json.dumps(facts, ensure_ascii=False)
            + ". Другое время ухода, «не выйдет», перерыв или «доделает / не доделает текущую» — проверяй функцией "
              "preview_unavailable. Ничего не применено, пока диспетчер не нажмёт «Добавить в изменения» "
              "и «Перепланировать».")


def _event_short(ev: dict, names: dict) -> str:
    t, who = ev["type"], names.get(ev.get("engineer_id"), ev.get("engineer_id"))
    return {"urgent_request": lambda: f"срочная {ev.get('request', {}).get('id', '')}",
            "new_request": lambda: f"новая {ev.get('request_id')}",
            "cancel_request": lambda: f"отмена {ev.get('request_id')}",
            "move_request": lambda: f"{ev.get('request_id')} → {who}",
            "engineer_break": lambda: f"перерыв: {who} {ev.get('time')}–{ev.get('until')}",
            "engineer_unavailable": lambda: f"{who} " + ("не вышел" if ev.get("mode") == "absent" else f"уходит в {ev.get('time')}"),
            }.get(t, lambda: t)()


def _day_story(con, sid: str, view: dict, p: Problem) -> tuple[str, dict]:
    """История дня фактами для модели: утренний (базовый) план, каждое перепланирование — что случилось
    и что стало с метриками; для последнего — разбор изменений. Без неё модель на «сравни с утренним»
    отвечала «данных нет»."""
    names = {k: e["name"] for k, e in view["engineers"].items()}
    chain = planning.history(con, sid)
    steps = [{"когда": h["at"] or "утро, до начала дня", "план": "базовый" if h["kind"] != "replan" else "перепланирование",
              "события": [_event_short(e, names) for e in h["events"]], "назначено": f"{h['assigned']} из {h['total']}",
              "инженеров": h["engineers_used"], "пробег, км": h["total_km"],
              **({"принят": h["accepted"]} if h["kind"] == "replan" else {})} for h in chain]
    facts = {"история плана за день (от утреннего к текущему)": steps}
    plan = view["plan"]
    if plan.get("diff"):
        b = bundle_diff(plan, p)
        facts["последнее перепланирование: что изменилось"] = {k: b[k] for k in ("now", "events", "changes", "engineers_changed", "summary")}
    pending = store.events(con, sid, pending_only=True)
    if pending:
        facts["в очереди, ещё не применено"] = [_event_short(e, names) for e in pending]
    text = ("\n\nФАКТЫ О ДНЕ (сравнивай планы по ним, не проси данных, которые здесь есть): "
            + json.dumps(facts, ensure_ascii=False, default=str))
    return text, {"replans": len(chain) > 1, "pending": bool(pending)}


def ask(con, sid: str, ctx: dict, question: str, history: list) -> dict:
    if ctx["kind"] == "variants":
        got = variants.latest(con, sid)
        if got is None:
            return {"text": "Варианты ещё не считались — нажмите «Построить варианты плана».", "source": "template",
                    "tools": [], "rows": [], "action": None, "suggestions": [], "history": history, "label": "варианты плана"}
        rows = [{"name": v["name"], "a": f"{v['assigned']}/{v['total']} · {v['engineers_used']} инж. · ",
                 "v": ("нет оценки" if v["expected_late"] is None else f"{_num(v['expected_late'])} опозд."), "tone": "ok" if v["key"] == got["recommended"] else "ink"}
                for v in got["variants"]]
        return {"text": got["text"], "source": "template", "tools": ["варианты", "базовый план"], "rows": rows,
                "action": None, "suggestions": suggestions(ctx, {}), "history": history, "label": "варианты плана"}

    view = planning.view(con, sid)
    p = Problem.from_dataset(planning.dataset(con, sid))
    lbl = label(ctx, view)
    n = Narrator()
    used: list[str] = []
    proposal: dict = {}

    def propose_move(request_id: str, engineer_id: str) -> str:
        owner = view["plan"]["assignments"].get(request_id, {}).get("engineer_id")
        if owner == engineer_id:
            return json.dumps({"ok": False, "reason": "заявка и так у этого инженера"}, ensure_ascii=False)
        why = whatif.check_move(con, sid, request_id, engineer_id)
        if why:
            return json.dumps({"ok": False, "reason": why}, ensure_ascii=False)
        proposal.update(_move_action(con, sid, request_id, engineer_id, view) or {})
        return json.dumps({"ok": True}, ensure_ascii=False)

    extra = {"propose_move": (_fn("propose_move", "Предложить диспетчеру переназначить заявку инженеру (проверяет допустимость; ничего не применяет).",
                                  {"request_id": {"type": "string"}, "engineer_id": {"type": "string"}},
                                  ["request_id", "engineer_id"]), propose_move)}
    note = _screen_note(ctx, lbl) + NEXT_NOTE
    asked = _asked(history) | {question.strip().lower()}
    shown: dict = {}                     # строки «кто возьмёт» из шаблона — и при ответе модели
    day = {}
    if ctx["kind"] in ("changes", "plan", "analytics"):
        story, day = _day_story(con, sid, view, p)
        note += story
    if ctx["kind"] == "engineer":
        eid = ctx["id"]
        body = Unavailable(**(ctx.get("params") or {}))
        try:
            note += _hypothesis(whatif.unavailable_preview(con, sid, eid, body), view["engineers"][eid]["name"], body,
                                fmt(store.session(con, sid)["clock_min"]))
            shown = _t_engineer(con, sid, ctx, question, view)
        except ValueError as e:
            note += f"\n\nПоследствия недоступности посчитать не удалось: {e}."

        def preview_unavailable(mode: str = "leave", time: str | None = None, until: str | None = None,
                                finish_current: bool = True) -> str:
            try:
                b = Unavailable(mode=mode, time=time, until=until, finish_current=finish_current)
                return json.dumps(whatif.unavailable_preview(con, sid, eid, b), ensure_ascii=False)
            except (ValueError, TypeError) as e:
                return json.dumps({"error": str(e)}, ensure_ascii=False)

        extra["preview_unavailable"] = (_fn(
            "preview_unavailable",
            "Что будет, если этот инженер станет недоступен: какая текущая заявка, какие освободятся и кто их может взять. "
            "Ничего не применяет.",
            {"mode": {"type": "string", "enum": ["leave", "absent", "break"],
                      "description": "уйдёт в time / не выйдет сегодня / перерыв с time до until"},
             "time": {"type": "string", "description": "ЧЧ:ММ; по умолчанию — часы сессии"},
             "until": {"type": "string", "description": "конец перерыва, ЧЧ:ММ"},
             "finish_current": {"type": "boolean", "description": "дать доделать текущую заявку"}},
            []), preview_unavailable)
    text, hist = None, history
    if n.available:
        baseline = analytics.baseline(con, sid)[0] if ctx["kind"] == "analytics" else None
        text, hist = n.chat(view["plan"], p, question + note, history, baseline=baseline,
                            strict=True, extra_tools=extra, on_tool=lambda name, args, res: used.append(name))
    if text is not None and text.strip():
        text, nxt = split_next(text, asked)
    if text is not None and text.strip():
        return {"text": text, "source": "llm", "tools": [TOOL_LABEL.get(x, x) for x in dict.fromkeys(used)] or shown.get("tools", []),
                "rows": shown.get("rows", []), "action": proposal or None,
                "suggestions": nxt or _fresh(suggestions(ctx, {**day, **shown.get("extra", {})}), asked),
                "history": hist, "label": lbl}
    try:
        t = _template(con, sid, ctx, question, view, p)
    except ValueError as e:
        t = {"text": f"Не смог посчитать последствия: {e}", "tools": [], "rows": [], "action": None}
    return {"text": t["text"], "source": "template", "tools": t["tools"], "rows": t["rows"], "action": t["action"],
            "suggestions": _fresh(suggestions(ctx, {**day, **t.get("extra", {})}), asked), "history": history, "label": lbl}

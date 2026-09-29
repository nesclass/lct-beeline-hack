"""ЛЛМ-обёртка над ризонингом (backups/docs/model.md §2.4) через LiteLLM proxy.

Два режима:
  Narrator.explain_request / summarize_plan / explain_diff — один вызов, пересказ бандла фактов;
  Narrator.chat — диалог диспетчера с планом через function calling: модель не может утверждать
  «Петров занят», не вызвав функцию, которая это проверила.

Стек: litellm (клиент) → LiteLLM proxy (litellm_config.yaml, роутинг) → любой провайдер (сейчас openai/gpt-6-luna).
Окружение:
  LITELLM_BASE_URL   адрес прокси, по умолчанию http://localhost:4000
  LITELLM_API_KEY    ключ прокси (= LITELLM_MASTER_KEY в конфиге прокси)
  LLM_MODEL          model_name из litellm_config.yaml, по умолчанию dispatcher

Без ключа (или при любой ошибке) всё возвращает шаблонный текст — объяснение обязательный
критерий, оно не должно зависеть от сети.
"""
from __future__ import annotations

import json
import os

from .explain import probe
from .model import Problem
from .plan import routes_from_plan
from .reasoning import bundle_diff, bundle_plan, bundle_request, template_diff, template_summary
from .routing import route_km

DEFAULT_BASE_URL = "http://localhost:4000"
DEFAULT_MODEL = "dispatcher"

SYSTEM = """Ты — помощник диспетчера службы выездных инженеров (телеком). Ты объясняешь решения
планировщика маршрутов понятным языком.

Правила:
- Используй ТОЛЬКО факты из переданного JSON. Ничего не додумывай: если чего-то нет в данных — так и скажи.
- Сохраняй идентификаторы заявок (R…) и инженеров рядом с фамилиями, чтобы диспетчер мог их найти.
- Времена — как в данных (HH:MM). Расстояния — км с одним знаком.
- Пиши по-русски, коротко, деловым тоном, без вводных фраз и без markdown-разметки (никаких **, #, ###). Абзацы — можно, списки — только если перечисляешь 3+ однотипных пункта.
- Не хвали план и не извиняйся за него. Диспетчеру нужны причины и следствия.

Смысл полей:
- Логика времени: инженер должен приехать в окно заявки; работа начинается с момента приезда (если приехал раньше окна — ждёт его начала) и длится по нормативу (техработы + документы), может заканчиваться после окна. finish — когда инженер освободится.
- slack_min — запас до конца окна после начала работ; wait_min — сколько инженер ждал открытия окна.
- alternatives.could_take — другие инженеры, которые физически могли бы взять заявку, и во что это обошлось бы (delta_km — дополнительный пробег их маршрута; поле cost говорит, чем обернётся перенос — цитируй его смысл).
- alternatives.busy — совместимые инженеры, у которых заявка не помещается в маршрут; detail объясняет, обо что упирается.
- Коды причин: SKILL — нет навыка; TRANSPORT — не тот транспорт; WINDOW_REACH — не успеть доехать в окно;
  SHIFT_FIT — работа не помещается в смену; BUSY — совместим, но занят; DISPLACED — вытеснена срочной заявкой;
  ENGINEER_LOST — инженер стал недоступен.
- Оценки «мог бы, но +N км» локальные: они не учитывают, что освободившееся место у текущего инженера кто-то займёт.
- Главные метрики плана по убыванию важности: число назначенных заявок, число задействованных инженеров, суммарный пробег."""

TASK_REQUEST = """Объясни диспетчеру, почему заявка назначена именно так (или почему не назначена).
Структура: 1) кому и почему это допустимо; 2) почему не другим — сначала кто мог бы и какой ценой, потом кто занят и чем; 3) на что обратить внимание, если есть (малый запас, ожидание, длинное плечо). 3–6 предложений.

{bundle}"""

TASK_SUMMARY = """Напиши краткое саммари плана на день для диспетчера: что получилось, чем план лучше базового варианта (если есть сравнение), где узкие места (перегруженные инженеры, заявки с малым запасом, дефицит навыков), что не назначено и почему. Заверши одной фразой: что диспетчеру стоит проверить или решить. До 10 предложений.

{bundle}"""

TASK_DIFF = """Объясни диспетчеру, что произошло при перепланировании: какие события, что было заморожено, какие заявки и почему поменяли инженера/время/статус, что стало с метриками. Причинно-следственно: событие → освободилось/потребовалось → куда ушло → что не влезло. До 8 предложений.

{bundle}"""

CHAT_ADDON = """

Ты в режиме диалога. На вопросы о конкретных заявках/инженерах и «а что если» отвечай ТОЛЬКО после вызова
функций — они считают по актуальному плану. Какую функцию звать:
- «почему заявка у X / не у Y» → get_request (там альтернативы), затем при необходимости why_not(заявка, Y);
- «кому можно отдать заявку» → get_request: поле alternatives.could_take — это и есть ответ;
- «что если перенести к Y» → what_if_move; «что делает X» → get_engineer_route; «что не назначено» → list_unassigned.
Инженеров передавай по ID из ростера ниже; фамилию без ID не угадывай. Если функция говорит, что перенос
увеличивает число задействованных инженеров, обязательно скажи об этом: минимум персонала важнее пробега.

РОСТЕР ИНЖЕНЕРОВ: {roster}

СВОДКА ПЛАНА:
"""


class Narrator:
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 temperature: float = 0.2):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.base_url = base_url or os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL)
        self.api_key = api_key or os.environ.get("LITELLM_API_KEY") or os.environ.get("LITELLM_MASTER_KEY")
        self.temperature = temperature
        self.last_usage = None
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _completion(self, messages: list, **kw):
        """Один вызов через прокси. Возвращает ModelResponse (OpenAI-совместимый) или None с last_error."""
        if not self.available:
            return None
        import litellm
        try:
            resp = litellm.completion(
                model=f"litellm_proxy/{self.model}", api_base=self.base_url, api_key=self.api_key,
                messages=messages, temperature=self.temperature, **kw,
            )
        except Exception as e:                       # litellm оборачивает всё в свои исключения; нам важен только текст
            self.last_error = f"{type(e).__name__}: {str(e)[:300]}"
            return None
        self.last_usage = getattr(resp, "usage", None)
        return resp

    # -- один вызов ------------------------------------------------------------------
    def _ask(self, task: str, bundle: dict, max_tokens: int = 1500) -> str | None:
        resp = self._completion(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": task.format(bundle=json.dumps(bundle, ensure_ascii=False))}],
            max_tokens=max_tokens,
        )
        if resp is None:
            return None
        choice = resp.choices[0]
        if choice.finish_reason == "content_filter" or not choice.message.content:
            self.last_error = f"finish_reason={choice.finish_reason}"
            return None
        return choice.message.content.strip()

    def explain_request(self, plan: dict, p: Problem, rid: str) -> str:
        b = bundle_request(plan, p, rid)
        return self._ask(TASK_REQUEST, b) or b["template_text"]

    def summarize_plan(self, plan: dict, p: Problem, baseline: dict | None = None) -> str:
        b = bundle_plan(plan, p, baseline)
        return self._ask(TASK_SUMMARY, b, max_tokens=2000) or template_summary(b)

    def explain_diff(self, plan: dict, p: Problem) -> str:
        b = bundle_diff(plan, p)
        return self._ask(TASK_DIFF, b, max_tokens=2000) or template_diff(b)

    # -- чат с планом через function calling ------------------------------------------
    def chat(self, plan: dict, p: Problem, question: str, history: list | None = None,
             baseline: dict | None = None, max_rounds: int = 8, *, extra_tools: dict | None = None,
             on_tool=None, strict: bool = False) -> tuple[str | None, list]:
        """Возвращает (ответ, обновлённая история без system-сообщения). strict — при недоступности
        или ошибке ЛЛМ ответ None: вызывающий сам решает, чем его заменить."""
        history = list(history or [])
        if not self.available:
            return (None if strict else "ЛЛМ недоступна (нет LITELLM_API_KEY). Доступны шаблонные объяснения: "
                    "narrate --request <id> / --summary / --diff."), history
        registry = {**make_tools(plan, p, baseline), **(extra_tools or {})}
        tools = [{"type": "function", "function": spec} for spec, _ in registry.values()]
        roster = ", ".join(f"{k} {e.name}" for k, e in p.engineers.items())
        system = {"role": "system", "content": SYSTEM + CHAT_ADDON.format(roster=roster)
                  + json.dumps(bundle_plan(plan, p, baseline), ensure_ascii=False)}
        history.append({"role": "user", "content": question})
        for _ in range(max_rounds):
            resp = self._completion([system] + history, tools=tools, tool_choice="auto", max_tokens=2000)
            if resp is None:
                return (None if strict else f"Ошибка ЛЛМ: {self.last_error}"), history
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []
            history.append({"role": "assistant", "content": msg.content,
                            **({"tool_calls": [tc.model_dump() for tc in tool_calls]} if tool_calls else {})})
            if not tool_calls:
                return (msg.content or "").strip(), history
            for tc in tool_calls:                           # все результаты — до следующего запроса
                _, fn = registry.get(tc.function.name, (None, None))
                args = {}
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = fn(**args) if fn else f"неизвестная функция {tc.function.name}"
                except Exception as e:                      # ошибка инструмента — модели, не наверх
                    result = f"ошибка: {type(e).__name__}: {e}"
                history.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                if on_tool:
                    on_tool(tc.function.name, args if fn else {}, result)
        return (None if strict else "Не удалось получить ответ за отведённое число шагов."), history


# ---------------------------------------------------------------------------
def _fn(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required, "additionalProperties": False}}


REQ = {"request_id": {"type": "string", "description": "идентификатор заявки, например R033"}}
ENG = {"engineer_id": {"type": "string", "description": "идентификатор инженера из ростера, например E03 (фамилия тоже принимается)"}}


def make_tools(plan: dict, p: Problem, baseline: dict | None = None) -> dict[str, tuple[dict, callable]]:
    """Инструменты чата: name -> (OpenAI function spec, python-функция). Тонкие обёртки над explain.probe и бандлами."""
    routes = routes_from_plan(plan)

    def _eng(x: str) -> str | None:
        """ID или фамилия (без учёта регистра, допускается 'Царькову' → Царьков по префиксу)."""
        x = (x or "").strip()
        if x in p.engineers:
            return x
        low = x.lower()
        hits = [k for k, e in p.engineers.items() if low.startswith(e.name.lower()[:5])]
        return hits[0] if len(hits) == 1 else None

    def get_request(request_id: str) -> str:
        if request_id not in plan["assignments"]:
            return f"Заявки {request_id} нет в плане."
        return json.dumps(bundle_request(plan, p, request_id), ensure_ascii=False)

    def get_engineer_route(engineer_id: str) -> str:
        engineer_id = _eng(engineer_id) or engineer_id
        rt = next((r for r in plan["routes"] if r["engineer_id"] == engineer_id), None)
        if rt is None:
            return f"Инженера {engineer_id} нет в плане."
        stops = [{"request_id": s["request_id"], "type": p.requests[s["request_id"]].type,
                  "district": p.requests[s["request_id"]].district, "arrive": s["arrive"], "start": s["start"],
                  "finish": s["finish"], "leg_km": s["leg_km"], "slack_min": s["slack_min"], "locked": s["locked"]}
                 for s in rt["stops"]]
        return json.dumps({"engineer": {"id": engineer_id, "name": rt["name"], "transport": rt["transport"],
                                        "shift": rt["shift"], "skills": p.engineers[engineer_id].skills},
                           "stops": stops, "total_km": rt["total_km"], "utilization": rt["utilization"],
                           "unavailable_from": rt.get("unavailable_from")}, ensure_ascii=False)

    def why_not(request_id: str, engineer_id: str) -> str:
        engineer_id = _eng(engineer_id)
        if request_id not in p.requests or not engineer_id:
            return "Нет такой заявки или инженера (передай ID из ростера)."
        pr = probe(p, routes, request_id, engineer_id)
        pr["engineer_name"] = p.engineers[engineer_id].name
        return json.dumps(pr, ensure_ascii=False)

    def what_if_move(request_id: str, engineer_id: str) -> str:
        engineer_id = _eng(engineer_id)
        if request_id not in p.requests or not engineer_id:
            return "Нет такой заявки или инженера (передай ID из ростера)."
        cur = plan["assignments"][request_id]["engineer_id"]
        if cur == engineer_id:
            return f"Заявка {request_id} и так у {p.engineers[cur].name} ({cur}). Кому её можно отдать — см. get_request → alternatives.could_take."
        pr = probe(p, routes, request_id, engineer_id)
        if not pr["feasible"]:
            return json.dumps({"feasible": False, "blocker": pr["blocker"]}, ensure_ascii=False)
        out = {"feasible": True, "from": cur, "to": engineer_id, "new_start": pr["start"],
               "delta_km_target": pr["delta_km"], "target_was_idle": not routes[engineer_id]}
        if cur:
            e = p.engineers[cur]
            old = route_km(p, e, routes[cur])
            new = route_km(p, e, [x for x in routes[cur] if x != request_id])
            out["delta_km_source"] = round(new - old, 1)
            out["delta_km_total"] = round(pr["delta_km"] + new - old, 1)
            out["source_becomes_idle"] = len(routes[cur]) == 1
        else:
            out["delta_km_total"] = pr["delta_km"]
        out["delta_engineers_used"] = int(out["target_was_idle"]) - int(out.get("source_becomes_idle", False))
        return json.dumps(out, ensure_ascii=False)

    def list_unassigned() -> str:
        return json.dumps([{"id": rid, "code": plan["assignments"][rid]["reason"]["code"],
                            "text": plan["assignments"][rid]["text"]} for rid in plan["unassigned"]], ensure_ascii=False)

    def plan_metrics() -> str:
        return json.dumps(bundle_plan(plan, p, baseline), ensure_ascii=False)

    return {
        "get_request": (_fn("get_request", "Карточка заявки: поля, кому назначена и почему, либо причина неназначения, альтернативы.",
                            REQ, ["request_id"]), get_request),
        "get_engineer_route": (_fn("get_engineer_route", "Маршрут инженера: остановки по порядку с временем прибытия/начала/окончания, пробег, загрузка.",
                                   ENG, ["engineer_id"]), get_engineer_route),
        "why_not": (_fn("why_not", "Почему заявка не у этого инженера: можно ли вставить её в его маршрут, где, какой ценой, или что мешает.",
                        {**REQ, **ENG}, ["request_id", "engineer_id"]), why_not),
        "what_if_move": (_fn("what_if_move", "Что будет, если переназначить заявку другому инженеру: допустимо ли, изменение пробега обоих маршрутов, меняется ли число задействованных инженеров.",
                             {**REQ, **ENG}, ["request_id", "engineer_id"]), what_if_move),
        "list_unassigned": (_fn("list_unassigned", "Все неназначенные заявки с кодом и текстом причины.", {}, []), list_unassigned),
        "plan_metrics": (_fn("plan_metrics", "Метрики плана, нагрузка инженеров, узкие места, сравнение с базовым вариантом.", {}, []), plan_metrics),
    }

"""Свой набор данных: JSON в формате сценария или CSV с заявками. Проверка — теми же правилами,
что и форма новой заявки; первая же ошибка не прерывает разбор — диспетчер видит все сразу."""
from __future__ import annotations

import copy
import csv
import io
import json
import uuid

from pydantic import ValidationError

from . import scenarios
from .catalog import SKILL_OF
from .schema import NewRequest

REQUIRED = ["lat", "lon", "address", "district", "type", "work_type", "tw_start", "tw_end"]
ENGINEER_FIELDS = ["id", "name", "start.lat", "start.lon", "shift_start", "shift_end", "skills", "transport"]


class Invalid(Exception):
    def __init__(self, message: str, errors: list[str] = ()):
        super().__init__(message)
        self.message, self.errors = message, list(errors)[:20]


def _text(content: str) -> str:
    """Браузер мог прочитать cp1251 как latin-1: такие строки восстанавливаем."""
    try:
        return content.encode("latin-1").decode("cp1251")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return content


def _msg(e: ValidationError) -> str:
    return "; ".join(str(x["msg"]).removeprefix("Value error, ") for x in e.errors())


def _engineers(rows: list) -> list[str]:
    """Проверка обязательных полей инженера из JSON: «инженер N: нет поля …»."""
    errors = []
    for i, e in enumerate(rows, start=1):
        if not isinstance(e, dict):
            errors.append(f"инженер {i}: должен быть объектом")
            continue
        for field in ENGINEER_FIELDS:
            if field.startswith("start."):
                sub = field.split(".", 1)[1]
                if not isinstance(e.get("start"), dict) or sub not in e["start"]:
                    errors.append(f"инженер {i}: нет поля {field}")
            elif field not in e:
                errors.append(f"инженер {i}: нет поля {field}")
    return errors


def _merged(base: dict, over: dict) -> dict:
    """Своё поверх базового: чего нет в файле, берётся из базового сценария (вглубь по словарям)."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merged(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _sections(d: dict, tpl: dict) -> tuple[dict, dict]:
    """config и dictionaries из файла: должны быть объектами; частичные дополняются базовым сценарием."""
    config, dictionaries = d.get("config"), d.get("dictionaries")
    errors = []
    if config is not None and not isinstance(config, dict):
        errors.append("config должен быть объектом")
    if dictionaries is not None:
        if not isinstance(dictionaries, dict):
            errors.append("dictionaries должен быть объектом")
        elif not isinstance(dictionaries.get("norms"), dict) or not dictionaries["norms"]:
            errors.append("в dictionaries нет norms — нормативов по видам работ")
        else:
            for wt, n in dictionaries["norms"].items():
                if not isinstance(n, dict) or not all(isinstance(n.get(f), (int, float)) for f in ("tech_min", "docs_min")):
                    errors.append(f"норматив {wt}: нужны числа tech_min и docs_min")
    if errors:
        raise Invalid("в файле есть ошибки", errors)
    out = _merged(tpl["dictionaries"], {k: v for k, v in (dictionaries or {}).items() if k != "norms"})
    if dictionaries:
        out["norms"] = dictionaries["norms"]           # нормативы файла — целиком, без базовых
    return _merged(tpl["config"], config or {}), out


def _requests(rows: list, norms: dict, first_line: int) -> list[dict]:
    out, errors, seen = [], [], set()
    for i, row in enumerate(rows):
        line = first_line + i
        if not isinstance(row, dict):
            errors.append(f"строка {line}: должна быть объектом")
            continue
        wt = (row.get("work_type") or "").strip()
        if wt not in norms or wt not in SKILL_OF:
            errors.append(f"строка {line}: неизвестный вид работ {wt or '(пусто)'}")
            continue
        try:
            body = NewRequest(lat=float(row["lat"]), lon=float(row["lon"]), address=row["address"],
                              district=row["district"], type=row["type"], skill=SKILL_OF[wt], work_type=wt,
                              tw_start=row["tw_start"], tw_end=row["tw_end"],
                              priority=(row.get("priority") or "normal").strip() or "normal",
                              required_transport=(row.get("required_transport") or "").strip() or None)
        except ValidationError as e:
            errors.append(f"строка {line}: {_msg(e)}")
            continue
        except (ValueError, KeyError, TypeError):
            errors.append(f"строка {line}: координаты должны быть числами")
            continue
        rid = (row.get("id") or "").strip() or f"R{len(out) + 1:03d}"
        if rid in seen:
            errors.append(f"строка {line}: повторяется номер заявки {rid}")
            continue
        seen.add(rid)
        n = norms[wt]
        out.append({**body.model_dump(), "id": rid, "duration_min": n["tech_min"] + n["docs_min"]})
    if errors:
        raise Invalid("в файле есть ошибки", errors)
    if not out:
        raise Invalid("в файле нет ни одной заявки")
    return out


def parse(filename: str, content: str, base: str, title: str | None) -> dict:
    try:
        tpl = scenarios.load(base)
    except KeyError:
        raise Invalid(f"нет такого базового сценария: {base}")
    content = _text(content)
    norms = tpl["dictionaries"]["norms"]
    ident = f"u-{uuid.uuid4().hex[:8]}"
    if filename.lower().endswith(".json"):
        try:
            d = json.loads(content)
        except json.JSONDecodeError as e:
            raise Invalid(f"не удалось прочитать JSON: {e.msg}, строка {e.lineno}")
        if not isinstance(d, dict) or not d.get("engineers") or not d.get("requests"):
            raise Invalid("в JSON должны быть списки engineers и requests")
        eng_errors = _engineers(d["engineers"])
        if eng_errors:
            raise Invalid("в файле есть ошибки", eng_errors)
        config, dictionaries = _sections(d, tpl)
        norms = dictionaries["norms"]
        reqs = _requests(d["requests"], norms, 1)
        return {"id": ident, "title": title or d.get("title") or filename, "description": d.get("description", "Загружено из файла"),
                "area": d.get("area", ""), "meta": {**tpl["meta"], **d.get("meta", {})},
                "config": config, "dictionaries": dictionaries,
                "engineers": d["engineers"], "requests": reqs, "events": []}
    sample = content[:2000]
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delim)
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise Invalid(f"нет колонок: {', '.join(missing)}")
    reqs = _requests(list(reader), norms, 2)
    return {"id": ident, "title": title or filename.rsplit(".", 1)[0], "description": "Заявки из файла, инженеры — из «"
            + tpl["title"] + "»", "area": tpl.get("area", ""), "meta": dict(tpl["meta"]),
            "config": copy.deepcopy(tpl["config"]), "dictionaries": copy.deepcopy(tpl["dictionaries"]),
            "engineers": copy.deepcopy(tpl["engineers"]), "requests": reqs, "events": []}

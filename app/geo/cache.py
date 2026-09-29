"""Матрица сценария считается один раз и кладётся на диск.

Ключ — хэш от координат: если сценарий поменялся, кэш просто не подойдёт и будет
пересчитан. На диске матрица лежит таблицами, а не словарями с кортежами в ключах,
потому что JSON такие ключи не умеет.

На диск попадает только ответ OSRM. Оценка по прямой — признак того, что OSRM сейчас
недоступен; она запоминается лишь в памяти процесса (чтобы каждый запрос не ждал
таймаута), и OSRM переспрашивается при следующем старте.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .provider import MODES, Point

DIR = Path(__file__).resolve().parent.parent.parent / "data" / "geo"
_memo: dict[tuple[str, str], dict] = {}     # (сценарий, ключ) → оценочная матрица


def key(points: dict[str, Point]) -> str:
    raw = json.dumps(sorted((i, round(p[0], 6), round(p[1], 6)) for i, p in points.items()))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def encode(points: dict[str, Point], m: dict) -> dict:
    ids = m["ids"]
    return {"key": key(points), "ids": ids, "source": m.get("source", "haversine"),
            "km": [[m["km"][(a, b)] for b in ids] for a in ids],
            "min": {mode: [[m["min"][(a, b, mode)] for b in ids] for a in ids] for mode in MODES}}


def decode(d: dict) -> dict:
    ids = d["ids"]
    km = {(a, b): d["km"][i][j] for i, a in enumerate(ids) for j, b in enumerate(ids)}
    minutes = {(a, b, mode): d["min"][mode][i][j]
               for mode in MODES for i, a in enumerate(ids) for j, b in enumerate(ids)}
    return {"ids": ids, "km": km, "min": minutes, "source": d.get("source", "haversine")}


def save(name: str, points: dict[str, Point], m: dict) -> None:
    """Через временный файл: оборванная запись не оставит на месте кэша половину JSON.
    Файл у каждого писателя свой — иначе параллельные запросы уводят его друг у друга."""
    DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DIR, prefix=f".{name}.",
                                     suffix=".tmp", delete=False) as fh:
        fh.write(json.dumps(encode(points, m), ensure_ascii=False))
    os.replace(fh.name, DIR / f"{name}.json")


def load(name: str, points: dict[str, Point]) -> dict | None:
    """Матрица с диска; битый или чужой файл — всё равно что нет файла."""
    f = DIR / f"{name}.json"
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return decode(d) if d.get("key") == key(points) else None
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, IndexError, AttributeError):
        return None


def get(name: str, points: dict[str, Point], provider) -> dict:
    """Готовая матрица с диска или из памяти, иначе свежая от провайдера:
    ответ OSRM — на диск, оценку — только в память процесса."""
    m = load(name, points)
    if m is not None and m["source"] == "osrm":       # оценку, оставленную прежним кодом, не берём
        return m
    k = (name, key(points))
    if k in _memo:
        return _memo[k]
    m = provider.matrix(points)
    if m.get("source") == "osrm":
        save(name, points, m)
    else:
        _memo[k] = m
    return m

"""Реестр сценариев.

Сценарий — неизменяемый JSON в data/scenarios. Сессия работает с копией его содержимого
в базе, сам файл никогда не правится.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"
UPLOADED = Path(__file__).resolve().parent.parent / "out" / "scenarios"   # загруженные диспетчером

# `ident` приходит из тела запроса и становится именем файла — и здесь, и в кэше матриц.
# Пропускаем только простые имена: строчные буквы, цифры и дефис.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _path(ident: str) -> Path:
    if not NAME.fullmatch(ident):
        raise KeyError(ident)
    for d in (DIR, UPLOADED):
        f = d / f"{ident}.json"
        if f.exists():
            return f
    raise KeyError(ident)


def listing() -> list[dict]:
    out = [_card(json.loads(f.read_text(encoding="utf-8")), uploaded=False) for f in sorted(DIR.glob("*.json"))]
    if UPLOADED.exists():
        files = sorted(UPLOADED.glob("*.json"), key=lambda f: f.stat().st_mtime)
        for f in files:
            try:
                out.append(_card(json.loads(f.read_text(encoding="utf-8")), uploaded=True))
            except (json.JSONDecodeError, KeyError, OSError):
                continue                                   # битый или неполный файл — не мешает остальным
    return out


def _card(d: dict, uploaded: bool) -> dict:
    return {"id": d["id"], "title": d["title"], "description": d["description"],
            "engineers": len(d["engineers"]), "requests": len(d["requests"]),
            "districts": len({r.get("district", "") for r in d["requests"]} - {""}),
            "area": d.get("area", ""), "uploaded": uploaded}


def load(ident: str) -> dict:
    return json.loads(_path(ident).read_text(encoding="utf-8"))


def save_uploaded(d: dict) -> dict:
    UPLOADED.mkdir(parents=True, exist_ok=True)
    (UPLOADED / f"{d['id']}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return _card(d, uploaded=True)

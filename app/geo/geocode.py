"""Адрес новой заявки → координаты через Nominatim (OpenStreetMap).

Форма присылает точку «центр района со сдвигом»; если геокодер нашёл адрес в пределах
агломерации, точка заменяется на найденную. Любая беда - сеть, пустой ответ, точка вне
рамки - оставляет точку формы: заявка заводится всегда. Адрес геокодера - GEOCODER_URL,
GEOCODER_URL=off выключает геокодинг.
"""
from __future__ import annotations

import os

import requests

from .provider import Point

BOX = (35.0, 54.2, 40.3, 57.1)            # рамка графа OSRM, как в проверке NewRequest
_memo: dict[str, Point | None] = {}


def queries(address: str) -> list[str]:
    """«Царицыно, ул. Бакинская, д. 3» геокодер ищет лучше без района впереди."""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    out = []
    if len(parts) > 1:
        out.append(", ".join(parts[1:]) + ", Москва")
    out.append(", ".join(parts) + ", Москва")
    return out


def geocode(address: str, http=requests) -> Point | None:
    url = os.environ.get("GEOCODER_URL", "https://nominatim.openstreetmap.org")
    if url == "off" or not address.strip():
        return None
    if address in _memo:
        return _memo[address]
    got = None
    for q in queries(address):
        try:
            r = http.get(f"{url.rstrip('/')}/search", timeout=3,
                         params={"q": q, "format": "json", "limit": 1, "bounded": 1,
                                 "viewbox": ",".join(map(str, BOX))},
                         headers={"User-Agent": "lct-dispatcher-prototype"})
            r.raise_for_status()
            hits = r.json()
            if hits:
                lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
                if BOX[1] <= lat <= BOX[3] and BOX[0] <= lon <= BOX[2]:
                    got = (round(lat, 6), round(lon, 6))
                    break
        except Exception:
            break                               # сеть или формат: дальше спрашивать незачем
    _memo[address] = got
    return got

"""Авто по настоящим дорогам: OSRM.

Матрица берётся одним запросом /table на все пары сразу. Пешком, вело и общественный
транспорт OSRM не считает (для них нужен отдельный граф на каждый профиль), поэтому им
остаётся оценка по скорости — но уже от дорожного километража, а не от прямой.

Недоступность OSRM не должна ронять приложение: при любой ошибке возвращается оценка
по прямой, и вызывающий узнаёт об этом по полю source.
"""
from __future__ import annotations

import requests

from .haversine import Haversine
from .provider import MODES, Point


class Osrm:
    def __init__(self, base_url: str = "http://localhost:5001", timeout: float = 30,
                 fallback: Haversine | None = None, http=requests):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.http = http
        self.fallback = fallback or Haversine()

    # -- матрица ------------------------------------------------------------------
    def matrix(self, points: dict[str, Point]) -> dict:
        """Любая беда с OSRM — сетевая, или ответ не той формы — возвращает чистую оценку
        по прямой: пересчитываем её заново, чтобы не отдать наполовину заполненную матрицу."""
        try:
            m = self.fallback.matrix(points)
            self._fill(m, points)
        except Exception:
            return self.fallback.matrix(points)
        m["source"] = "osrm"
        return m

    def _fill(self, m: dict, points: dict[str, Point]) -> None:
        ids = m["ids"]
        table = self._table(points, ids)
        for i, a in enumerate(ids):
            for j, b in enumerate(ids):
                sec, met = table["durations"][i][j], table["distances"][i][j]
                if sec is None or met is None:
                    continue
                m["km"][(a, b)] = met / 1000
                m["min"][(a, b, "car")] = int(round(sec / 60))
        for a in ids:                                  # остальные виды — от дорожного километража
            for b in ids:
                if a == b:
                    continue
                for mode in MODES:
                    if mode != "car":
                        m["min"][(a, b, mode)] = self.fallback.minutes(m["km"][(a, b)], mode)

    def _table(self, points: dict[str, Point], ids: list[str]) -> dict:
        coords = ";".join(f"{points[i][1]:.6f},{points[i][0]:.6f}" for i in ids)
        r = self.http.get(f"{self.base}/table/v1/driving/{coords}",
                          params={"annotations": "duration,distance"}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # -- геометрия ----------------------------------------------------------------
    def line(self, a: Point, b: Point, mode: str) -> list[Point]:
        if mode != "car":
            return [a, b]
        try:
            r = self.http.get(
                f"{self.base}/route/v1/driving/{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}",
                params={"overview": "full", "geometries": "geojson"}, timeout=self.timeout)
            r.raise_for_status()
            coords = r.json()["routes"][0]["geometry"]["coordinates"]
        except Exception:
            return [a, b]
        return [(lat, lon) for lon, lat in coords]

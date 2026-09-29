"""Оценка времени в пути по прямой: haversine × коэффициент извилистости ÷ скорость + фикс.

Работает всегда и без сети, поэтому служит запасным вариантом для всех остальных
провайдеров и единственным источником для пешком, вело и общественного транспорта.
"""
from __future__ import annotations

import math

from .provider import MODES, Point

SPEED_KMH = {"car": 25, "bike": 15, "foot": 5, "public": 18}
FIXED_MIN = {"car": 5, "bike": 2, "foot": 0, "public": 10}


def haversine_km(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


class Haversine:
    def __init__(self, detour: float = 1.3, speed: dict | None = None, fixed: dict | None = None):
        self.detour = detour
        self.speed = dict(speed or SPEED_KMH)
        self.fixed = dict(fixed or FIXED_MIN)

    def minutes(self, km: float, mode: str) -> int:
        return int(round(km / self.speed[mode] * 60 + self.fixed[mode]))

    def matrix(self, points: dict[str, Point]) -> dict:
        ids = list(points)
        km: dict[tuple[str, str], float] = {}
        minutes: dict[tuple[str, str, str], int] = {}
        for a in ids:
            for b in ids:
                d = 0.0 if a == b else haversine_km(points[a], points[b]) * self.detour
                km[(a, b)] = d
                for mode in MODES:
                    minutes[(a, b, mode)] = 0 if a == b else self.minutes(d, mode)
        return {"ids": ids, "km": km, "min": minutes, "source": "haversine"}

    def line(self, a: Point, b: Point, mode: str) -> list[Point]:
        return [a, b]

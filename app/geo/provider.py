"""Интерфейс источника времени в пути и геометрии маршрута.

Точка — (широта, долгота). Матрица — словарь:
    {"ids": [...], "km": {(a, b): километры}, "min": {(a, b, вид): минуты}, "source": "..."}
Километры не зависят от вида транспорта: это длина дороги между точками.
"""
from __future__ import annotations

from typing import Protocol

Point = tuple[float, float]
MODES = ("car", "bike", "foot", "public")


class Travel(Protocol):
    def matrix(self, points: dict[str, Point]) -> dict:
        """Матрица по всем парам точек."""

    def line(self, a: Point, b: Point, mode: str) -> list[Point]:
        """Ломаная для карты, включая оба конца."""

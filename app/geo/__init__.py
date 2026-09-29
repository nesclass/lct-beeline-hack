"""Единая точка входа гео-слоя.

Адрес OSRM берётся из переменной окружения OSRM_URL; если её нет - http://localhost:5001.
В Docker Compose приложению передаётся http://osrm:5000.
"""
from __future__ import annotations

import os

from . import cache
from .osrm import Osrm
from .provider import Point, Travel

_provider: Travel | None = None


def provider() -> Travel:
    global _provider
    if _provider is None:
        _provider = Osrm(base_url=os.environ.get("OSRM_URL", "http://localhost:5001"))
    return _provider


def matrix_for(scenario: str, points: dict[str, Point]) -> dict:
    """Матрица сценария: с диска, иначе считаем и кладём на диск."""
    return cache.get(scenario, points, provider())


def line(a: Point, b: Point, mode: str) -> list[Point]:
    return provider().line(a, b, mode)

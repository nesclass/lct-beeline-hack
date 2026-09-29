"""Тела запросов и настройки расчёта — на языке диспетчера.

Веса модели (P, F, G, множитель срочности) сюда не попадают: это константы сценария,
диспетчер их не выбирает.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

PRIORITY_F = {"fewer": 200, "balance": 60, "shorter": 10}     # вес инженера в км; P = 10000 держит порядок
MARGINS = {"econom": (0, 0, 0), "balanced": (10, 10, 2), "reliable": (20, 20, 5)}
MARGIN_LABEL = {"econom": "Экономный", "balanced": "Сбалансированный", "reliable": "Надёжный"}


class Settings(BaseModel):
    engine: Literal["ortools", "greedy"] = Field("ortools", description="Глубокий или быстрый движок")
    time_limit: float = Field(10, ge=1, le=120, description="Сколько секунд считать")
    warm_start: bool = Field(True, description="Стартовать глубокий движок от быстрого решения")
    work_pct: float = Field(0, ge=0, le=100, description="Запас к нормативу работы, %")
    travel_pct: float = Field(0, ge=0, le=100, description="Запас к времени в пути, %")
    travel_min: int = Field(0, ge=0, le=60, description="Запас на каждый переезд, мин")
    priority: Literal["fewer", "balance", "shorter"] = Field(
        "balance", description="Что важнее: меньше людей / баланс / меньше пробега")
    margin: Literal["econom", "balanced", "reliable", "custom"] = Field(
        "econom", description="Какой запас выбран на экране")


class NewSession(BaseModel):
    scenario: str


class Clock(BaseModel):
    time: str

    @field_validator("time")
    @classmethod
    def check(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v


class Unavailable(BaseModel):
    finish_current: bool = Field(True, description="Дать доделать текущую заявку")
    mode: Literal["leave", "absent", "break"] = Field(
        "leave", description="Уйдёт в указанное время / не выйдет сегодня / перерыв — вернётся в указанное время")
    time: str | None = Field(None, description="Когда уйдёт (начало перерыва), ЧЧ:ММ; по умолчанию — часы сессии")
    until: str | None = Field(None, description="Конец перерыва, ЧЧ:ММ")
    reason: str = Field("", max_length=200)

    @field_validator("time", "until")
    @classmethod
    def check(cls, v: str | None) -> str | None:
        if v is not None and not HHMM.match(v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v

    @model_validator(mode="after")
    def check_break(self):
        if self.mode == "break":
            if not (self.time and self.until):
                raise ValueError("укажите начало и конец перерыва")
            if self.until <= self.time:        # строки сравнимы: HHMM требует ведущий ноль
                raise ValueError("перерыв должен заканчиваться позже начала")
        return self


class ReplanBody(BaseModel):
    mode: Literal["minimal", "full"] = Field("minimal", description="Минимум перестановок / полный пересчёт")


class Move(BaseModel):
    engineer_id: str


class Cancel(BaseModel):
    reason: str = Field("", max_length=200)


class AskContext(BaseModel):
    kind: Literal["plan", "request", "engineer", "changes", "analytics", "variants"]
    id: str | None = None
    params: dict | None = None


class AskBody(BaseModel):
    context: AskContext
    question: str = Field(min_length=1, max_length=500)
    history: list = []


class NewRequest(BaseModel):
    lat: float
    lon: float
    address: str = ""
    district: str = ""
    type: str = ""
    skill: Literal["local", "connect", "emergency"]
    work_type: Literal["connect_base", "emergency", "equipment", "local_repair"]
    tw_start: str
    tw_end: str
    priority: Literal["normal", "urgent"] = "normal"
    required_transport: Literal["car", "bike", "foot", "public"] | None = None

    @field_validator("tw_start", "tw_end")
    @classmethod
    def check(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v

    @field_validator("lat")
    @classmethod
    def check_lat(cls, v: float) -> float:
        # граф OSRM собран на агломерацию (спека §6): 54.2–57.1 с.ш., 35.0–40.3 в.д.
        if not 54.2 <= v <= 57.1:
            raise ValueError("точка вне Московской агломерации")
        return v

    @field_validator("lon")
    @classmethod
    def check_lon(cls, v: float) -> float:
        if not 35.0 <= v <= 40.3:
            raise ValueError("точка вне Московской агломерации")
        return v

    @model_validator(mode="after")
    def check_window(self):
        if self.tw_end <= self.tw_start:        # ЧЧ:ММ с ведущим нулём сравниваются как строки
            raise ValueError("конец окна должен быть позже начала")
        return self

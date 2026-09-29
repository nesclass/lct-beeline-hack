"""Данные задачи: заявки, инженеры, матрица перемещений, веса. См. backups/docs/model.md §1–2."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

REASON_TEXT = {
    "SKILL": "нет нужного навыка",
    "TRANSPORT": "нет требуемого транспорта",
    "WINDOW_REACH": "не успевает доехать до конца окна",
    "SHIFT_FIT": "работа не помещается в смену",
    "BUSY": "занят другими заявками",
    "DISPLACED": "вытеснена срочной заявкой",
    "ENGINEER_LOST": "инженер стал недоступен",
    "PINNED": "закреплена диспетчером за другим инженером",
}


def hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt(m: int | float) -> str:
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


def haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@dataclass
class Request:
    id: str
    lat: float
    lon: float
    address: str
    district: str
    type: str
    skill: str
    duration: int
    tw_start: int
    tw_end: int
    priority: str = "normal"
    required_transport: str | None = None
    work_type: str | None = None       # категория норматива (backups/docs/Нормативы.xlsx)
    tech_min: int | None = None        # техработы у клиента
    docs_min: int | None = None        # оформление документов

    @classmethod
    def from_json(cls, d: dict, norms: dict | None = None) -> "Request":
        """duration = техработы + документы по нормативу; явный duration_min во входе имеет приоритет
        (для сырых данных без норматива)."""
        wt = d.get("work_type")
        n = (norms or {}).get(wt) if wt else None
        tech, docs = (n["tech_min"], n["docs_min"]) if n else (None, None)
        if d.get("duration_min") is not None:
            duration = int(d["duration_min"])
        elif n:
            duration = tech + docs
        else:
            raise ValueError(f"{d['id']}: нет duration_min и нет норматива для work_type={wt!r}")
        return cls(d["id"], d["lat"], d["lon"], d.get("address", ""), d.get("district", ""),
                   d.get("type", ""), d["skill"], duration,
                   hhmm(d["tw_start"]), hhmm(d["tw_end"]), d.get("priority", "normal"),
                   d.get("required_transport"), wt, tech, docs)

    def to_json(self) -> dict:
        return {"id": self.id, "lat": self.lat, "lon": self.lon, "address": self.address,
                "district": self.district, "type": self.type, "skill": self.skill, "work_type": self.work_type,
                "duration_min": self.duration, "tw_start": fmt(self.tw_start), "tw_end": fmt(self.tw_end),
                "priority": self.priority, "required_transport": self.required_transport}

    @property
    def duration_text(self) -> str:
        if self.tech_min is None:
            return f"{self.duration} мин"
        return f"{self.duration} мин (техработы {self.tech_min}" + (f" + документы {self.docs_min}" if self.docs_min else "") + ")"


@dataclass
class Engineer:
    id: str
    name: str
    lat: float
    lon: float
    start_label: str
    shift_start: int
    shift_end: int
    skills: list[str]
    transport: str
    # при перепланировании старт становится «виртуальным»: узел, где инженер сейчас, и момент освобождения
    start_node: str = ""
    available_from: int = 0
    breaks: list[tuple[int, int]] = field(default_factory=list)   # [начало, конец) — ни работы, ни дороги

    @classmethod
    def from_json(cls, d: dict) -> "Engineer":
        e = cls(d["id"], d.get("name", d["id"]), d["start"]["lat"], d["start"]["lon"],
                d["start"].get("label", ""), hhmm(d["shift_start"]), hhmm(d["shift_end"]),
                list(d["skills"]), d["transport"])
        e.start_node, e.available_from = e.id, e.shift_start
        e.breaks = sorted((hhmm(b), hhmm(en)) for b, en in d.get("breaks", []))
        return e


@dataclass
class Problem:
    requests: dict[str, Request]            # порядок = порядок входа (важно для baseline)
    engineers: dict[str, Engineer]
    config: dict
    dictionaries: dict
    prev_owner: dict[str, str] = field(default_factory=dict)   # перепланирование: прежний владелец
    pinned: dict[str, str] = field(default_factory=dict)   # закреплено диспетчером: заявка → инженер
    _pos: dict[str, tuple[float, float]] = field(default_factory=dict)
    _km: dict[tuple[str, str], float] = field(default_factory=dict)
    _min: dict[tuple[str, str, str], int] = field(default_factory=dict)

    # -- построение -----------------------------------------------------------------
    @classmethod
    def from_dataset(cls, ds: dict) -> "Problem":
        norms = ds.get("dictionaries", {}).get("norms", {})
        p = cls({r["id"]: Request.from_json(r, norms) for r in ds["requests"]},
                {e["id"]: Engineer.from_json(e) for e in ds["engineers"]},
                ds["config"], ds.get("dictionaries", {}))
        p.rebuild_matrix(ds.get("matrix"))
        return p

    def rebuild_matrix(self, external: dict | None = None) -> None:
        """Без external — расстояния по прямой. С external — готовые километры и минуты
        (гео-слой приложения); пары, которых в ней нет, досчитываются по требованию в km()."""
        self._pos = {r.id: (r.lat, r.lon) for r in self.requests.values()}
        self._pos.update({e.id: (e.lat, e.lon) for e in self.engineers.values()})
        if external:
            self._km = dict(external["km"])
            self._min = dict(external["min"])
            return
        self._min = {}
        f = self.config["travel"]["detour_factor"]
        self._km = {(a, b): 0.0 if a == b else haversine(*self._pos[a], *self._pos[b]) * f
                    for a in self._pos for b in self._pos}

    # -- доступ ---------------------------------------------------------------------
    @property
    def weights(self) -> dict:
        return self.config["weights"]

    def weight(self, r: Request) -> float:
        return self.weights["urgent_multiplier"] if r.priority == "urgent" else 1.0

    def km(self, a: str, b: str) -> float:
        """Километры между точками; недостающая пара досчитывается по прямой и запоминается
        (заявка из события появляется уже после того, как матрица посчитана)."""
        if (a, b) not in self._km:
            f = self.config["travel"]["detour_factor"]
            self._km[(a, b)] = 0.0 if a == b else haversine(*self._pos[a], *self._pos[b]) * f
        return self._km[(a, b)]

    # -- время: raw (как есть) и плановое (с подушкой §4.4а) -----------------------------
    @property
    def robustness(self) -> dict:
        return self.config.get("robustness", {})

    def travel_raw(self, a: str, b: str, transport: str) -> float:
        """Дорога без подушки, мин. normative — 20 мин на переезд; external — готовая матрица
        гео-слоя; matrix — по координатам и транспорту."""
        if a == b:
            return 0.0
        t = self.config["travel"]
        if t.get("mode", "matrix") == "normative":
            return float(t.get("normative_road_min", 20))
        if t.get("mode") == "external":
            got = self._min.get((a, b, transport))
            if got is not None:
                return float(got)
        return self.km(a, b) / t["speed_kmh"][transport] * 60 + t["fixed_min"][transport]

    def travel(self, a: str, b: str, transport: str) -> int:
        """Плановая дорога: raw · (1 + ε_travel) + σ, целые минуты (OR-Tools и simulate считают одинаково)."""
        if a == b:
            return 0
        r = self.robustness
        f = r.get("travel_factor", r.get("safety_factor", 0.0))
        return int(round(self.travel_raw(a, b, transport) * (1 + f) + r.get("travel_min", r.get("safety_min", 0))))

    def service(self, r: Request) -> int:
        """Плановая длительность работы: норматив · (1 + ε_work)."""
        f = self.robustness.get("work_factor", self.robustness.get("safety_factor", 0.0))
        return int(round(r.duration * (1 + f)))

    def new_request(self, d: dict) -> Request:
        """Заявка из события — с тем же нормативом, что и датасет."""
        return Request.from_json(d, self.dictionaries.get("norms", {}))

    def label(self, node: str) -> str:
        if node in self.requests:
            return f"{node} ({self.requests[node].address})"
        e = self.engineers[node]
        return e.start_label or node

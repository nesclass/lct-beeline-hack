"""
Генератор синтетического датасета по спеке backups/docs/data_spec.md.

    python data/synth/generate.py            # пишет data/synth/dataset.json
    python data/synth/generate.py --check    # + проверка покрытия ТЗ §6 (FIFO vs greedy)

Координаты синтетические: центроид района + шум ≤ ~1.5 км. Адреса — реальные улицы
района + случайный дом, к координатам привязаны только районом.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

SEED = 42
OUT = Path(__file__).parent / "dataset.json"

# ---------------------------------------------------------------------------
# География: один округ (ЮАО), районы из реального датасета «Юго-восток» без области; диаметр ~11 км
# ---------------------------------------------------------------------------
OFFICE = {"lat": 55.604, "lon": 37.664, "label": "Офис, ул. Бирюлёвская, д. 1с1"}

DISTRICTS = {
    #  name: (lat, lon, weight, streets)
    "Царицыно":                   (55.617, 37.660, 10, ["Кавказский б-р", "ул. Луганская", "ул. Бакинская", "ул. Севанская"]),
    "Москворечье-Сабурово":       (55.637, 37.680,  5, ["Пролетарский пр-т", "Каширское ш.", "ул. Кантемировская"]),
    "Орехово-Борисово Северное":  (55.622, 37.712,  8, ["ул. Шипиловская", "ул. Домодедовская", "ул. Ясеневая"]),
    "Орехово-Борисово Южное":     (55.606, 37.730,  7, ["Гурьевский пр-д", "Каширское ш.", "ул. Воронежская"]),
    "Зябликово":                  (55.612, 37.750,  8, ["ул. Кустанайская", "Ореховый б-р", "ул. Мусы Джалиля"]),
    "Братеево":                   (55.636, 37.762,  6, ["ул. Братеевская", "ул. Ключевая", "ул. Алма-Атинская"]),
    "Бирюлёво Восточное":         (55.590, 37.675,  8, ["ул. Бирюлёвская", "ул. Педагогическая", "ул. Загорьевская"]),
    "Бирюлёво Западное":          (55.590, 37.635,  6, ["Булатниковский пр-д", "Востряковский пр-д", "ул. Харьковская"]),
    "Чертаново Южное":            (55.590, 37.600,  5, ["ул. Россошанская", "Варшавское ш.", "ул. Газопровод"]),
}

HOMES = {  # стартовые точки «из дома»
    "Царицыно": {"lat": 55.620, "lon": 37.655, "label": "Дом, Царицыно"},
    "Зябликово": {"lat": 55.610, "lon": 37.748, "label": "Дом, Зябликово"},
    "Братеево": {"lat": 55.638, "lon": 37.765, "label": "Дом, Братеево"},
}

# ---------------------------------------------------------------------------
# Инженеры — руками, чтобы гарантировать все комбинации навыков и транспорта
# ---------------------------------------------------------------------------
ENGINEERS = [
    # id    name          transport shift          skills                          start
    ("E01", "Горбанев",    "car",    "09:00", "18:00", ["local", "connect", "emergency"], OFFICE),
    ("E02", "Паршин",      "car",    "09:00", "18:00", ["connect"],                       OFFICE),
    ("E03", "Саламатин",   "car",    "12:00", "21:00", ["local", "connect"],              OFFICE),
    ("E04", "Козырь",      "foot",   "09:00", "18:00", ["local"],                         HOMES["Царицыно"]),
    ("E05", "Белоновский", "car",    "13:00", "22:00", ["local", "connect"],              OFFICE),
    ("E06", "Рыбин",       "bike",   "11:00", "20:00", ["local", "connect"],              HOMES["Зябликово"]),
    ("E07", "Андреев",     "car",    "13:00", "22:00", ["connect", "emergency"],          OFFICE),
    ("E08", "Бузань",      "public", "13:00", "22:00", ["connect"],                       OFFICE),
    ("E09", "Макаров",     "car",    "09:00", "18:00", ["local", "emergency"],            OFFICE),
    ("E10", "Царьков",     "public", "13:00", "22:00", ["local"],                         HOMES["Братеево"]),
    ("E11", "Демин",       "car",    "13:00", "22:00", ["local", "connect", "emergency"], OFFICE),
    ("E12", "Каушнян",     "foot",   "10:00", "19:00", ["emergency"],                     OFFICE),
]

# ---------------------------------------------------------------------------
# Нормативы (backups/docs/Нормативы.xlsx): дорога / техработы / документы, мин.
# Длительность работы у клиента = техработы + документы; «дорога» — нормативная средняя,
# в режиме travel.mode = "matrix" вместо неё считается реальная дорога по координатам.
# ---------------------------------------------------------------------------
NORMS = {
    "connect_base": {"label": "Подключение клиентов Базовая",     "road_min": 20, "tech_min": 60, "docs_min": 10},
    "emergency":    {"label": "Аварий на ТКД",                    "road_min": 20, "tech_min": 80, "docs_min": 0},
    "equipment":    {"label": "Дозаказ оборудования",             "road_min": 20, "tech_min": 10, "docs_min": 10},
    "local_repair": {"label": "Локальная заявка/ремонт у клиента", "road_min": 20, "tech_min": 30, "docs_min": 0},
}

# Типы заявок: (label, skill, work_type, required_transport, weight)
REQUEST_TYPES = [
    ("Подключение (конвергенция)",  "connect",   "connect_base", None,  14),
    ("Заявка на подключение",       "connect",   "connect_base", None,   4),
    ("Дозаказ оборудования",        "connect",   "equipment",    "car",  4),
    ("Переключение на Гбит/с",      "connect",   "connect_base", None,   3),
    ("Нет линка",                   "local",     "local_repair", None,  10),
    ("Низкая скорость",             "local",     "local_repair", None,   5),
    ("Замена роутера",              "local",     "local_repair", None,   4),
    ("Замена ТВ-приставки",         "local",     "local_repair", None,   3),
    ("Работа с кабелем",            "local",     "local_repair", "car",  4),
    ("Авария на узле",              "emergency", "emergency",    "car",  5),
    ("Рост ошибок на порту",        "emergency", "emergency",    None,   5),
    ("Обрыв магистрали",            "emergency", "emergency",    "car",  2),
]


def duration_of(work_type: str) -> int:
    n = NORMS[work_type]
    return n["tech_min"] + n["docs_min"]
# сколько случайных заявок в каждый 2-часовой слот (стратифицировано, чтобы не зависеть от seed);
# аварии с вероятностью 0.4 получают окно на весь день вместо слота
SLOT_QUOTA = {("10:00", "12:00"): 7, ("12:00", "14:00"): 9, ("14:00", "16:00"): 13,
              ("16:00", "18:00"): 12, ("18:00", "20:00"): 8, ("20:00", "22:00"): 6}
ALL_DAY = ("10:00", "22:00")

CONFIG = {
    "travel": {
        "mode": "matrix",                 # matrix — по координатам; normative — 20 мин на любой переезд
        "normative_road_min": 20,
        "detour_factor": 1.3,
        "speed_kmh": {"car": 25, "bike": 15, "foot": 5, "public": 18},
        "fixed_min": {"car": 5, "bike": 2, "foot": 0, "public": 10},
    },
    "weights": {"P": 10000, "F": 60, "G": 15, "urgent_multiplier": 3},
    "robustness": {                       # backups/docs/model.md §4.4: подушка (а) и отчёт о рисках (б)
        "work_factor": 0.0, "travel_factor": 0.0, "travel_min": 0,   # запас к работе / к дороге / мин на переезд
        "risk": {"eps_grid": [0, 0.1, 0.2, 0.3], "tol_min": 10, "stress_runs": 200, "stress_cv": 0.15, "late_threshold": 0.5},
    },
}
DICTS = {
    "skills": {"local": "Локальные работы", "connect": "Работы на подключение и дозаказы",
               "emergency": "Аварийные работы"},
    "transport": {"car": "Автомобиль", "foot": "Пешеход", "bike": "Велосипед",
                  "public": "Общественный транспорт"},
    "priority": {"normal": "Обычная", "urgent": "Срочная"},
    "norms": NORMS,
}


def wchoice(rng, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def make_request(rng, rid, slot, district=None):
    if district is None:
        names = list(DISTRICTS)
        district = wchoice(rng, names, [DISTRICTS[n][2] for n in names])
    lat0, lon0, _, streets = DISTRICTS[district]
    while True:  # тип должен помещаться в слот до конца смены (22:00)
        label, skill, wt, transport, _ = wchoice(rng, REQUEST_TYPES, [t[4] for t in REQUEST_TYPES])
        dur = duration_of(wt)
        if hhmm(slot[0]) + dur <= hhmm("22:00"):
            break
    tw = ALL_DAY if (skill == "emergency" and rng.random() < 0.4) else slot
    return {
        "id": rid,
        "lat": round(lat0 + rng.uniform(-0.012, 0.012), 5),
        "lon": round(lon0 + rng.uniform(-0.020, 0.020), 5),
        "address": f"{district}, {rng.choice(streets)}, д. {rng.randint(1, 60)}",
        "district": district,
        "type": label, "skill": skill, "work_type": wt, "duration_min": dur,
        "tw_start": tw[0], "tw_end": tw[1],
        "priority": "normal", "required_transport": transport,
    }


def build(seed=SEED, engineers_n=None, load=1.0, ident="normal", title="Обычный день", description=""):
    rng = random.Random(seed)
    roster = ENGINEERS if engineers_n is None else ENGINEERS[:engineers_n]
    engineers = [
        {"id": i, "name": n, "start": st, "shift_start": a, "shift_end": b,
         "skills": sk, "transport": tr}
        for (i, n, tr, a, b, sk, st) in roster
    ]

    slots = [sl for sl, q in SLOT_QUOTA.items() for _ in range(max(1, round(q * load)))]
    rng.shuffle(slots)
    requests = [make_request(rng, f"R{n:03d}", sl) for n, sl in enumerate(slots, start=1)]

    # --- специальные заявки: две заведомо неназначаемые + пара «выгодно одному» ---
    lat, lon = DISTRICTS["Царицыно"][:2]
    requests.append({  # нет инженера с навыком+транспортом: connect + foot не существует
        "id": f"R{len(requests) + 1:03d}", "lat": lat + 0.003, "lon": lon - 0.004,
        "address": "Царицыно, музей-заповедник, павильон 3", "district": "Царицыно",
        "type": "Подключение (пешеходная зона)", "skill": "connect", "work_type": "connect_base",
        "duration_min": duration_of("connect_base"),
        "tw_start": "12:00", "tw_end": "14:00", "priority": "normal", "required_transport": "foot",
    })
    lat, lon = DISTRICTS["Зябликово"][:2]
    requests.append({  # не помещается в смену: авария 80 мин, клиент только с 21:00, смены до 22:00
        "id": f"R{len(requests) + 1:03d}", "lat": lat - 0.002, "lon": lon + 0.006,
        "address": "Зябликово, Ореховый б-р, д. 45", "district": "Зябликово",
        "type": "Обрыв магистрали", "skill": "emergency", "work_type": "emergency",
        "duration_min": duration_of("emergency"),
        "tw_start": "21:00", "tw_end": "22:00", "priority": "normal", "required_transport": "car",
    })
    # пара на дальнем краю округа (Братеево) в одном окне — солверу выгодно отдать одному инженеру
    for _ in range(2):
        r = make_request(rng, f"R{len(requests) + 1:03d}", ("14:00", "16:00"), district="Братеево")
        r.update({"skill": "connect", "type": "Подключение (конвергенция)", "work_type": "connect_base",
                  "duration_min": duration_of("connect_base"),
                  "required_transport": None, "tw_start": "14:00", "tw_end": "16:00"})
        requests.append(r)

    # --- события ---
    lat, lon = DISTRICTS["Царицыно"][:2]
    events = [
        {"id": "EV1", "type": "urgent_request", "time": "13:30",
         "request": {"id": "R901", "lat": lat + 0.006, "lon": lon + 0.008,
                     "address": "Царицыно, ул. Луганская, д. 10", "district": "Царицыно",
                     "type": "Авария на узле", "skill": "emergency", "work_type": "emergency",
                     "duration_min": duration_of("emergency"),
                     "tw_start": "13:30", "tw_end": "15:30", "priority": "urgent",
                     "required_transport": "car"}},
        {"id": "EV2", "type": "cancel_request", "time": "12:15",
         "request_id": next(r["id"] for r in requests if r["tw_start"] == "14:00")},
        {"id": "EV3", "type": "engineer_unavailable", "time": "14:00",
         "engineer_id": "E01", "finish_current": True},
    ]

    return {
        "id": ident, "title": title, "description": description, "area": "ЮАО",
        "meta": {"name": f"synth-{ident}", "date": "2026-08-17", "seed": seed,
                 "description": f"Синтетический рабочий день, ЮАО Москвы: {len(engineers)} инженеров, "
                                f"{len(requests)} заявок, {len(events)} события. "
                                "Координаты и адреса синтетические (центроид района + шум)."},
        "config": CONFIG, "dictionaries": DICTS,
        "engineers": engineers, "requests": requests, "events": events,
    }


# ---------------------------------------------------------------------------
# Проверка покрытия ТЗ §6: минимальная модель времени, FIFO baseline и жадный
# ---------------------------------------------------------------------------
def hhmm(s): h, m = s.split(":"); return int(h) * 60 + int(m)
def fmt(m): return f"{m // 60:02d}:{m % 60:02d}"


def haversine(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def check(ds):
    cfg = ds["config"]["travel"]
    E, R = ds["engineers"], ds["requests"]
    pos = {r["id"]: (r["lat"], r["lon"]) for r in R}
    for e in E: pos[e["id"]] = (e["start"]["lat"], e["start"]["lon"])

    def dist(a, b): return haversine(pos[a], pos[b]) * cfg["detour_factor"]
    def travel(a, b, tr): return dist(a, b) / cfg["speed_kmh"][tr] * 60 + cfg["fixed_min"][tr]

    def compat(r, e):
        if r["skill"] not in e["skills"]: return "SKILL"
        if r["required_transport"] and r["required_transport"] != e["transport"]: return "TRANSPORT"
        arr = hhmm(e["shift_start"]) + travel(e["id"], r["id"], e["transport"])
        t = max(arr, hhmm(r["tw_start"]))
        if t > hhmm(r["tw_end"]): return "WINDOW_REACH"
        if t + r["duration_min"] > hhmm(e["shift_end"]): return "SHIFT_FIT"
        return None

    # -- прокрутка маршрута: вернуть список t_i или None если недопустимо
    def simulate(e, route):
        t, cur, km, times = hhmm(e["shift_start"]), e["id"], 0.0, []
        for rid in route:
            r = byid[rid]
            arr = t + travel(cur, rid, e["transport"]); km += dist(cur, rid)
            st = max(arr, hhmm(r["tw_start"]))
            if st > hhmm(r["tw_end"]) or st + r["duration_min"] > hhmm(e["shift_end"]): return None
            times.append(st); t = st + r["duration_min"]; cur = rid
        return times, km

    byid = {r["id"]: r for r in R}

    def metrics(routes):
        used = sum(1 for v in routes.values() if v)
        km = {k: (simulate(byid_e[k], v)[1] if v else 0.0) for k, v in routes.items()}
        assigned = sum(len(v) for v in routes.values())
        return used, assigned, sum(km.values()), km
    byid_e = {e["id"]: e for e in E}

    # -- FIFO baseline (ТЗ §2.3)
    fifo = {e["id"]: [] for e in E}
    for r in R:
        for e in E:
            if compat(r, e) is None and simulate(e, fifo[e["id"]] + [r["id"]]) is not None:
                fifo[e["id"]].append(r["id"]); break

    # -- greedy: самые «зажатые» заявки первыми, лучшая вставка по Δkm (+F за пустой маршрут)
    F = ds["config"]["weights"]["F"]
    order = sorted(R, key=lambda r: (sum(compat(r, e) is None for e in E), hhmm(r["tw_end"]) - hhmm(r["tw_start"])))
    greedy = {e["id"]: [] for e in E}
    for r in order:
        best = None
        for e in E:
            if compat(r, e) is not None: continue
            base = simulate(e, greedy[e["id"]])
            for p in range(len(greedy[e["id"]]) + 1):
                cand = greedy[e["id"]][:p] + [r["id"]] + greedy[e["id"]][p:]
                sim = simulate(e, cand)
                if sim is None: continue
                d = sim[1] - base[1] + (F if not greedy[e["id"]] else 0)
                if best is None or d < best[0]: best = (d, e["id"], p)
        if best: greedy[best[1]].insert(best[2], r["id"])

    # -- отчёт
    print(f"Инженеров: {len(E)}, заявок: {len(R)}, событий: {len(ds['events'])}")
    print("Навыки заявок:", {s: sum(r["skill"] == s for r in R) for s in DICTS["skills"]})
    print("По нормативам:", {wt: sum(r["work_type"] == wt for r in R) for wt in NORMS})
    print("Треб. транспорт:", {str(t): sum(r["required_transport"] == t for r in R) for t in (None, "car", "foot")})
    pts = [(r["lat"], r["lon"]) for r in R]
    diam = max(haversine(a, b) for a in pts for b in pts)
    print(f"Диаметр зоны: {diam:.1f} км")
    print("Комбинации навыков инженеров:", sorted({",".join(e["skills"]) for e in E}))
    print("Транспорт инженеров:", {t: sum(e["transport"] == t for e in E) for t in DICTS["transport"]})
    zero = [(r["id"], sorted({compat(r, e) for e in E})) for r in R if all(compat(r, e) for e in E)]
    print("Заявки без кандидатов (ожидаем R056/R057):", zero)
    assert {z[0] for z in zero} == {"R056", "R057"}, zero
    for name, routes in (("FIFO baseline", fifo), ("greedy", greedy)):
        used, assigned, km, _ = metrics(routes)
        print(f"{name:14s}: инженеров {used:2d}, назначено {assigned}/{len(R)}, пробег {km:7.1f} км")
    fu, fa, fk, _ = metrics(fifo); gu, ga, gk, _ = metrics(greedy)
    # лексикографически, как в модели: больше назначено → меньше людей → меньше км
    assert (-ga, gu, gk) < (-fa, fu, fk), "greedy должен выигрывать у FIFO лексикографически"
    print("OK: конфликт FIFO vs оптимизация присутствует")
    _, _, _, gkm = metrics(greedy)
    print("greedy, км по инженерам:", {k: round(v, 1) for k, v in gkm.items()})
    un = [r["id"] for r in R if not any(r["id"] in v for v in greedy.values())]
    print("greedy, не назначены:", un)


SCENARIOS = [
    dict(ident="normal", title="Обычный день", load=1.0, engineers_n=None, seed=42,
         description="Штатная нагрузка: людей хватает, почти всё назначается."),
    dict(ident="peak", title="Пиковая нагрузка", load=1.35, engineers_n=None, seed=43,
         description="Заявок заметно больше при том же составе — часть не помещается в день."),
    dict(ident="short-staffed", title="Некомплект", load=1.0, engineers_n=8, seed=44,
         description="Обычный объём заявок силами восьми инженеров: дефицит людей и риск опозданий."),
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--scenarios", action="store_true", help="записать все сценарии в data/scenarios/")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    if args.scenarios:
        out_dir = Path(__file__).resolve().parent.parent / "scenarios"
        out_dir.mkdir(parents=True, exist_ok=True)
        for s in SCENARIOS:
            ds = build(**s)
            (out_dir / f"{s['ident']}.json").write_text(
                json.dumps(ds, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{s['ident']}: {len(ds['engineers'])} инженеров, {len(ds['requests'])} заявок")
    else:
        ds = build(args.seed)
        OUT.write_text(json.dumps(ds, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{OUT}: {len(ds['engineers'])} инженеров, {len(ds['requests'])} заявок")
        if args.check:
            check(ds)

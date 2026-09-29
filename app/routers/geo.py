"""Геометрия маршрутов для карты.

Линия тянется только для пар, реально попавших в план. Повторяющиеся пары считаются
один раз за запрос: у нескольких инженеров бывают общие участки. Если матрица — оценка
по прямой, OSRM недоступен, и участки рисуются прямыми без обращения к нему.
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import geo, planning, state, store
from .planning import with_plan

router = APIRouter(prefix="/api/sessions")


@router.get("/{sid}/routes")
def routes(sid: str):
    with_plan(sid)
    data = planning.view(state.con(), sid)
    engineers, requests = data["engineers"], data["requests"]
    # отменённая заявка уходит из вида, но инженер после неё может стоять в её точке
    known = {r["id"]: r for r in store.requests(state.con(), sid)}
    cache: dict[tuple, list] = {}

    def line(a, b, mode):
        if data["travel_source"] != "osrm":      # OSRM недоступен — дороги не спрашиваем
            return [a, b]
        key = (a, b, mode)
        if key not in cache:
            cache[key] = geo.line(a, b, mode)
        return cache[key]

    out = []
    for rt in data["plan"]["routes"]:
        if not rt["stops"]:
            continue
        e = engineers[rt["engineer_id"]]
        # линия всегда от депо: points содержат и замороженные с утра остановки. Где инженер
        # сейчас (после перепланирования — последняя замороженная заявка), говорит current;
        # узел, который не инженер и не заявка, — несогласованный план, а не повод рисовать депо.
        node = rt["start"]["node"]
        at = e if node == e["id"] else requests.get(node) or known[node]
        current = {"node": node, "lat": at["lat"], "lon": at["lon"], "available_from": rt["available_from"]}
        points = [{"request_id": None, "lat": e["lat"], "lon": e["lon"], "seq": 0,
                   "label": e["start"], "arrive": None, "start": None,
                   "finish": None, "locked": False}]
        for s in rt["stops"]:
            r = requests[s["request_id"]]
            points.append({"request_id": r["id"], "lat": r["lat"], "lon": r["lon"], "seq": s["seq"],
                           "label": r["address"], "arrive": s["arrive"], "start": s["start"],
                           "finish": s["finish"], "locked": s["locked"]})
        legs = [{"from": points[i]["request_id"], "to": points[i + 1]["request_id"],
                 "line": line((points[i]["lat"], points[i]["lon"]),
                              (points[i + 1]["lat"], points[i + 1]["lon"]), e["transport"])}
                for i in range(len(points) - 1)]
        out.append({"engineer_id": e["id"], "name": e["name"], "transport": e["transport"],
                    "current": current, "points": points, "legs": legs})
    return {"source": data["travel_source"], "routes": out}

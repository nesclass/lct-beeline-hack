/** Данные карты (4g): список маршрутов слева, точки и линия маршрута на карте, подпись под ним,
 *  справа — порядок остановок выбранного инженера (задача — «справа не отображается порядок»).
 *  Цвет точки — по запасу (задача 13): crit/warn перекрывают цвет инженера. */
import { TRANSPORT_SHORT } from './labels.js';
import { num, plural } from './num.js';
import { fmt, hm } from './time.js';
import { tolOf, tolText, tone } from './gantt.js';

// Подложка карты — OpenStreetMap: без ключа, подписи улиц по-русски, номера домов с 17-го
// масштаба. Прежние светлые подложки (CARTO, Esri Light Gray) адресов не показывали; чтобы
// маршруты не терялись на цветной карте, плитки слегка обесцвечены (.map-el .leaflet-tile-pane).
export const TILES = {
  url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  options: { maxZoom: 19, attribution: '&copy; участники OpenStreetMap' },
};

export function routeList(view, colors, selected) {
  const rows = view.plan.routes.filter(rt => rt.stops.length).map(rt => ({
    eid: rt.engineer_id, name: rt.name, c: colors[rt.engineer_id].main, n: rt.stops.length, km: num(rt.total_km), on: rt.engineer_id === selected }));
  return { rows, total: num(view.plan.routes.reduce((a, rt) => a + rt.total_km, 0)) };
}

export function pointsOf(route, view, colors) {
  const stops = Object.fromEntries(view.plan.routes.flatMap(rt => rt.stops.map(s => [s.request_id, s])));
  return route.points.filter(p => p.request_id).map(p => {
    const t = tolOf(view, p.request_id), k = tone(t), [tol, tolColor] = tolText(t), r = view.requests[p.request_id];
    return { seq: p.seq, id: p.request_id, x: [p.lat, p.lon],
             color: k === 'crit' ? 'var(--red)' : k === 'warn' ? '#D97706' : colors[route.engineer_id].main,
             tip: { title: `${p.seq}. ${p.request_id}`, type: r.type, addr: r.address, plan: `${p.start}–${p.finish}`,
                    leg: `${stops[p.request_id]?.leg_min ?? 0} мин`, tol, tolColor } };
  });
}

export function lineOf(route) {
  const out = [];
  route.legs.forEach((leg, i) => leg.line.forEach((pt, j) => { if (!(i > 0 && j === 0)) out.push([pt[0], pt[1]]); }));
  return out;
}

export const isRoad = (source, transport) => source === 'osrm' && transport === 'car';

export function footer(view, eid) {
  const rt = view.plan.routes.find(r => r.engineer_id === eid);
  return `${TRANSPORT_SHORT[rt.transport]} · ${rt.shift} · ${plural(rt.stops.length, ['заявка', 'заявки', 'заявок'])} · ${num(rt.total_km)} км`;
}

/** Порядок остановок выбранного инженера для правой колонки карты: старт (депо или «сейчас
 *  здесь» после перепланирования — rt.start.node — не депо), заявки по seq, конец смены с
 *  итогами. Статус — done/active/ahead по текущему времени (как в AvailabilityModal.currentStop);
 *  locked — заявка заморожена перепланированием независимо от времени. Отменённая заявка,
 *  которой уже нет в view.requests (план ещё не пересчитан), пропускается, а не роняет список. */
export function stopList(view, eid, clockMin, colors) {
  const rt = view.plan.routes.find(r => r.engineer_id === eid);
  if (!rt) return null;
  const c = colors[eid];
  const [shiftStart, shiftEnd] = rt.shift.split('–');
  const here = rt.start.node !== eid;
  const rows = rt.stops.filter(s => view.requests[s.request_id]).map(s => {
    const r = view.requests[s.request_id];
    const t = tolOf(view, s.request_id), k = tone(t), [tol, tolColor] = tolText(t);
    const status = hm(s.finish) <= clockMin ? 'done' : hm(s.start) <= clockMin ? 'active' : 'ahead';
    return { id: s.request_id, seq: s.seq, type: r.type, addr: r.address,
             win: `окно ${fmt(r.tw_start)}–${fmt(r.tw_end)}`, plan: `${s.start}–${s.finish}`,
             leg: s.leg_min > 0 ? `дорога ${s.leg_min} мин` : '', wait: s.wait_min > 0 ? `ожидание ${s.wait_min} мин` : '',
             tol, tolColor, color: k === 'crit' ? 'var(--red)' : k === 'warn' ? '#D97706' : c.main,
             status, locked: s.locked, manual: !!view.plan.assignments?.[s.request_id]?.manual };
  });
  return {
    eid, name: rt.name,
    head: { label: rt.start.label, time: here ? rt.available_from : shiftStart, here },
    rows,
    tail: { time: shiftEnd, n: plural(rows.length, ['заявка', 'заявки', 'заявок']), km: num(rt.total_km), travel: rt.total_travel_min },
  };
}

import { describe, expect, it } from 'vitest';
import { TILES, footer, isRoad, lineOf, pointsOf, routeList, stopList } from './mapView.js';

const view = {
  plan: { routes: [
    { engineer_id: 'E05', name: 'Белоновский', transport: 'car', total_km: 25.7, shift: '13:00–22:00',
      start: { node: 'E05', label: 'Офис, Кавказский б-р, 1' }, available_from: '13:00', total_travel_min: 27,
      stops: [
        { request_id: 'R1', seq: 1, start: '13:20', finish: '14:00', leg_min: 15, wait_min: 0, slack_min: 60, locked: true },
        { request_id: 'R2', seq: 2, start: '15:00', finish: '15:30', leg_min: 12, wait_min: 0, slack_min: 60, locked: false },
        { request_id: 'R3', seq: 3, start: '16:00', finish: '16:20', leg_min: 10, wait_min: 0, slack_min: 60, locked: false },
        { request_id: 'R4', seq: 4, start: '17:10', finish: '17:40', leg_min: 5, wait_min: 15, slack_min: 60, locked: false }] },
    { engineer_id: 'E08', name: 'Бузань', transport: 'public', total_km: 0, shift: '13:00–22:00',
      start: { node: 'R9', label: 'ул. Тестовая, 5' }, available_from: '14:10', total_travel_min: 0, stops: [] }],
    assignments: { R1: { manual: false }, R2: { manual: true }, R4: { manual: false } } },
  risk: { tol: { R1: 40, R2: 5 } },
  engineers: { E05: { name: 'Белоновский', transport: 'car', shift_start: 780, shift_end: 1320 } },
  requests: { R1: { type: 'Нет линка', address: 'Кавказский б-р, 12', tw_start: 780, tw_end: 900 },
              R2: { type: 'Подключение', address: 'ул. Бакинская, 21', tw_start: 840, tw_end: 960 },
              R4: { type: 'Ремонт', address: 'ул. Полевая, 3', tw_start: 900, tw_end: 1100 } },
  // R3 намеренно нет в requests — отменена, но план ещё не пересчитан (задача — не падать)
};
const colors = { E05: { main: '#C2185B' }, E08: { main: '#5B7C99' } };
const route = { engineer_id: 'E05', transport: 'car',
  points: [{ request_id: null, lat: 1, lon: 1, seq: 0 }, { request_id: 'R1', lat: 2, lon: 2, seq: 1, start: '13:20', finish: '14:00' },
           { request_id: 'R2', lat: 3, lon: 3, seq: 2, start: '15:00', finish: '15:30' }],
  legs: [{ line: [[1, 1], [1.5, 1.5], [2, 2]] }, { line: [[2, 2], [3, 3]] }] };

describe('список маршрутов', () => {
  it('только с заявками, выбранный отмечен, итог', () => {
    expect(routeList(view, colors, 'E05')).toEqual({ rows: [{ eid: 'E05', name: 'Белоновский', c: '#C2185B', n: 4, km: '25,7', on: true }], total: '25,7' });
  });
});

describe('точки и линия', () => {
  it('цвет по запасу, подсказка', () => {
    const pts = pointsOf(route, view, colors);
    expect(pts.map(p => [p.seq, p.color])).toEqual([[1, '#C2185B'], [2, 'var(--red)']]);
    expect(pts[1].tip).toEqual({ title: '2. R2', type: 'Подключение', addr: 'ул. Бакинская, 21', plan: '15:00–15:30',
                                 leg: '12 мин', tol: '5 мин · риск опоздания', tolColor: 'var(--red-ink)' });
  });
  it('линия без повторов', () => { expect(lineOf(route)).toEqual([[1, 1], [1.5, 1.5], [2, 2], [3, 3]]); });
  it('дороги — только авто от OSRM', () => {
    expect([isRoad('osrm', 'car'), isRoad('osrm', 'foot'), isRoad('haversine', 'car')]).toEqual([true, false, false]);
  });
  it('подпись внизу', () => { expect(footer(view, 'E05')).toBe('Авто · 13:00–22:00 · 4 заявки · 25,7 км'); });
});

describe('порядок остановок (правая колонка карты)', () => {
  it('старт от депо, порядок по seq, статус по времени, пропуск отменённой, дорога/ожидание, конец с итогами', () => {
    const l = stopList(view, 'E05', 910, colors); // 15:10 — R1 сдана, R2 в работе, R3 отменена (пропуск), R4 впереди
    expect(l.head).toEqual({ label: 'Офис, Кавказский б-р, 1', time: '13:00', here: false });
    expect(l.rows.map(r => r.id)).toEqual(['R1', 'R2', 'R4']); // R3 пропущена, порядок сохранён
    expect(l.rows.map(r => r.status)).toEqual(['done', 'active', 'ahead']);
    expect(l.rows[0]).toMatchObject({ locked: true, manual: false, leg: 'дорога 15 мин', wait: '' });
    expect(l.rows[1]).toMatchObject({ locked: false, manual: true, win: 'окно 14:00–16:00', plan: '15:00–15:30' });
    expect(l.rows[2]).toMatchObject({ leg: 'дорога 5 мин', wait: 'ожидание 15 мин', tol: '60 мин' });
    expect(l.tail).toEqual({ time: '22:00', n: '3 заявки', km: '25,7', travel: 27 });
  });

  it('после перепланирования инженер не в депо — «сейчас здесь», пустой маршрут', () => {
    const l = stopList(view, 'E08', 850, colors);
    expect(l.head).toEqual({ label: 'ул. Тестовая, 5', time: '14:10', here: true });
    expect(l.rows).toEqual([]);
    expect(l.tail).toEqual({ time: '22:00', n: '0 заявок', km: '0', travel: 0 });
  });

  it('неизвестный инженер — null, не падает', () => {
    expect(stopList(view, 'ZZZ', 900, colors)).toBeNull();
  });
});

describe('TILES', () => {
  it('подложка без ключа и с адресами: OpenStreetMap, дома видны при приближении', () => {
    expect(TILES.url).not.toMatch(/cartocdn/);
    expect(TILES.url).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    expect(TILES.options.maxZoom).toBeGreaterThanOrEqual(18);
    expect(TILES.options.attribution).toMatch(/OpenStreetMap/);
  });
});

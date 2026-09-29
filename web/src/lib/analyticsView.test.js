import { describe, expect, it } from 'vitest';
import { eventShort, historyRows, hourly, kmRows, loadLegend, loadRows, loadSummary, loadTotals, skillRows, slackBucket, slackRows,
         tiles, toCsv, trendRows, windowBucket, windowRows } from './analyticsView.js';

const a = {
  current: { assigned: 49, total: 51, unassigned: 2, engineers_used: 9, engineers_total: 12, total_km: 186.2, expected_late: 0.4,
             km_per_engineer: { E01: 13.3, E02: 19.5, E08: 0 } },
  baseline: { assigned: 46, total: 51, unassigned: 5, engineers_used: 11, engineers_total: 12, total_km: 247.4, expected_late: 0.9,
              km_per_engineer: { E01: 22.0, E02: 23.1, E08: 0 } },
  hours: [{ h: 9, in_work: 2, on_shift: 3 }, { h: 14, in_work: 11, on_shift: 9 }],
  skills: [{ skill: 'local', label: 'Локальные работы', assigned: 22, total: 22 }, { skill: 'connect', label: 'x', assigned: 20, total: 21 }],
};
const engineers = [{ id: 'E01', name: 'Горбанев' }, { id: 'E02', name: 'Паршин' }, { id: 'E08', name: 'Бузань' }];
const colors = { E01: { main: '#E4572E' }, E02: { main: '#F29E1F' }, E08: { main: '#5B7C99' } };

describe('аналитика', () => {
  it('плитки', () => {
    expect(tiles(a)).toEqual([
      { label: 'Назначено', val: '49 / 51', sub: 'базовый: 46', bg: 'var(--green-tint)', c: 'var(--green-ink)' },
      { label: 'Инженеров', val: '9', sub: 'базовый: 11 · −2', bg: 'var(--yellow-card)', c: 'var(--amber-ink)' },
      { label: 'Пробег', val: '186 км', sub: 'базовый: 247 · −25 %', bg: 'var(--blue-card)', c: 'var(--blue)' },
      { label: 'Ожид. опозданий', val: '0,4', sub: 'базовый: 0,9', bg: 'var(--peach)', c: 'var(--red-ink)' }]);
  });
  it('пробег по инженерам с отметкой базового', () => {
    const r = kmRows(a, engineers, colors);
    expect(r.map(x => x.name)).toEqual(['Горбанев', 'Паршин']);
    expect(r[1]).toMatchObject({ km: '19,5', c: '#F29E1F' });
    expect(Math.round(r[1].w)).toBe(84);
    expect(r[1].b).toBe(100);
  });
  it('по часам и по навыкам', () => {
    const h = hourly(a);
    expect(h.map(x => [x.t, x.n, x.c])).toEqual([['9', 2, 'var(--blue)'], ['14', 11, 'var(--amber)']]);
    expect(h[1].h).toBeGreaterThan(h[1].capH);
    expect(skillRows(a)[1]).toMatchObject({ name: 'Подключение', a: 20, tot: 21 });
  });
  it('история', () => {
    const names = { E01: 'Горбанев' };
    expect(eventShort({ type: 'engineer_unavailable', engineer_id: 'E01', mode: 'leave' }, names)).toBe('Горбанев ушёл');
    expect(eventShort({ type: 'urgent_request', request: { id: 'R901' } }, names)).toBe('Срочная R901');
    const rows = historyRows([
      { kind: 'variant', at: null, label: 'Сбалансированный', events: [], assigned: 48, total: 50, total_km: 185.1, changes: null },
      { kind: 'replan', at: '14:00', label: null, events: [{ type: 'urgent_request', request: { id: 'R901' } }, { type: 'engineer_unavailable', engineer_id: 'E01' }],
        assigned: 49, total: 51, total_km: 186.2, changes: 6 }], names, '09:00');
    expect(rows).toEqual([{ t: '09:00', why: 'Утверждён «Сбалансированный»', a: '48 / 50', km: '185 км', ch: '—' },
                          { t: '14:00', why: 'Срочная R901, Горбанев ушёл', a: '49 / 51', km: '186 км', ch: '6 изменений' }]);
  });
  it('выгрузка', () => {
    const csv = toCsv(a, engineers);
    expect(csv.startsWith('﻿инженер;пробег, км;базовый, км\n')).toBe(true);
    expect(csv).toContain('Горбанев;13,3;22\n');
    expect(csv.trim().split('\n').at(-1)).toBe('итого;186,2;247,4');
  });
  it('выгрузка — экранирование имени с ; и "', () => {
    const a2 = { ...a, current: { ...a.current, km_per_engineer: { E01: 13.3 } }, baseline: { ...a.baseline, km_per_engineer: { E01: 22.0 } } };
    const named = [{ id: 'E01', name: 'Иванов; мл. "Пётр"' }];
    const csv = toCsv(a2, named);
    expect(csv).toContain('"Иванов; мл. ""Пётр""";13,3;22\n');
  });
});

describe('аналитика — новые графики', () => {
  const load = {
    E01: { work: 300, travel: 60, wait: 30, break: 30, shift: 540 },
    E08: { work: 0, travel: 0, wait: 0, break: 0, shift: 540 } };
  const b = { ...a, now: null,
    current: { ...a.current, load, travel_min: 60, wait_min: 30, tol: [0, 9, 10, 19, 20, 39, 40, 59, 60, 200],
               windows: [{ off: -5, len: 120 }, { off: 0, len: 120 }, { off: 40, len: 120 }, { off: 80, len: 120 }, { off: 120, len: 120 }] },
    baseline: { ...a.baseline, load: { E01: { work: 100, travel: 90, wait: 200, break: 0, shift: 540 } }, travel_min: 90, wait_min: 200,
                tol: [5, 5], windows: [{ off: -200, len: 120 }] } };

  it('загрузка по инженерам: сегменты, «занят», инженер без заявок — вся смена свободна', () => {
    const r = loadRows(b, engineers);
    expect(r.map(x => x.name)).toEqual(['Горбанев', 'Бузань']);
    expect(r[0].segs.map(s => [s.k, s.min])).toEqual([['work', 300], ['travel', 60], ['wait', 30], ['break', 30], ['free', 120]]);
    expect(r[0].segs.reduce((s, x) => s + x.w, 0)).toBeCloseTo(100);
    expect(r[0].busy).toBe('67 %');
    expect(r[0].aria).toBe('Горбанев: работа 5 ч, дорога 1 ч, ожидание 0,5 ч, перерыв 0,5 ч из смены 9 ч');
    expect(r[1].segs).toEqual([expect.objectContaining({ k: 'free', w: 100 })]);
    expect(r[1].busy).toBe('0 %');
  });
  it('загрузка: итог команды и строка сравнения; без полей базового — только наш', () => {
    const t = loadTotals(b);
    expect(t.map(x => x.label)).toEqual(['наш план', 'базовый']);
    expect(t[1].segs.find(s => s.k === 'wait').min).toBe(200);
    expect(loadSummary(b)).toEqual([{ label: 'в дороге всего', cur: '1 ч', base: '1,5 ч' },
                                    { label: 'ожидание у клиента', cur: '0,5 ч', base: '3,3 ч' }]);
    expect(loadLegend(t).map(p => p.k)).toEqual(['work', 'travel', 'wait', 'break', 'free']);
    expect(loadLegend(loadTotals({ ...b, current: { ...b.current, load: { E08: load.E08 } } })).map(p => p.k))
      .toEqual(['work', 'travel', 'wait', 'free']);
    const old = { ...b, baseline: a.baseline };
    expect(loadTotals(old).map(x => x.label)).toEqual(['наш план']);
    expect(loadSummary(old)[0].base).toBe('—');
    expect(loadRows(a, engineers)).toEqual([]);
    expect(loadSummary(a)).toEqual([]);
  });
  it('запас по времени: границы корзин', () => {
    expect([0, 9, 10, 19, 20, 39, 40, 59, 60, 200].map(slackBucket)).toEqual([0, 0, 1, 1, 2, 2, 3, 3, 4, 4]);
    const r = slackRows(b);
    expect(r.map(x => [x.n, x.bn])).toEqual([[2, 2], [2, 0], [2, 0], [2, 0], [2, 0]]);
    expect(r[0]).toMatchObject({ p: '20 %', bp: '100 %', bw: 100, w: 20, c: 'var(--red)' });
  });
  it('запас: нет базового или пустой план — без падений', () => {
    const r = slackRows({ ...b, baseline: { ...b.baseline, tol: null } });
    expect(r.every(x => x.bn === null && x.bw === 0 && x.bp === '—')).toBe(true);
    const e = slackRows({ current: { tol: [] }, baseline: { tol: [] } });
    expect(e.every(x => x.n === 0 && x.w === 0 && x.p === '—')).toBe(true);
  });
  it('приезд в окно: до открытия, трети, после окна — только если есть', () => {
    expect([{ off: -1, len: 60 }, { off: 0, len: 60 }, { off: 19, len: 60 }, { off: 20, len: 60 }, { off: 40, len: 60 },
            { off: 60, len: 60 }, { off: 61, len: 60 }].map(windowBucket)).toEqual([0, 1, 1, 2, 3, 3, 4]);
    const r = windowRows(b);
    expect(r.map(x => [x.label, x.n, x.bn])).toEqual([['раньше окна, ждёт', 1, 1], ['в начале окна', 1, 0],
      ['в середине окна', 1, 0], ['в конце окна', 2, 0]]);
    const late = windowRows({ current: { windows: [{ off: 130, len: 120 }] }, baseline: {} });
    expect(late.at(-1)).toMatchObject({ label: 'после окна', n: 1, bn: null });
  });
  it('как менялся план: шаги и строки', () => {
    const t = trendRows([
      { at: null, assigned: 57, total: 59, total_km: 144.4, engineers_used: 9 },
      { at: '14:00', assigned: 57, total: 60, total_km: 169.2 }], '09:00');
    expect(t.steps).toEqual(['09:00', '14:00']);
    expect(t.rows.map(r => r.label)).toEqual(['Назначено', 'Пробег, км', 'Инженеров']);
    expect(t.rows[1].cells).toEqual([{ v: '144', h: 24 }, { v: '169', h: 28 }]);
    expect(t.rows[2].cells).toEqual([{ v: '9', h: 28 }, { v: '—', h: 0 }]);
    expect(t.rows[0].cells[1].v).toBe('57/60');
    expect(trendRows([], '09:00')).toEqual({ steps: [], rows: expect.any(Array) });
  });
});

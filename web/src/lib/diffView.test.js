import { describe, expect, it } from 'vitest';
import { GEN, INS, affectedText, banner, deltaTiles, groups, insight } from './diffView.js';

const names = { E01: 'Горбанев', E07: 'Андреев', E09: 'Макаров', E10: 'Царьков' };
const plan = {
  now: '14:00', solve_time_s: 4.1, accepted: false, replan_of: 'p0',
  events: [{ type: 'urgent_request', request: { id: 'R901' } }, { type: 'engineer_unavailable', engineer_id: 'E01' }],
  metrics: { assigned: 49, unassigned: 2, engineers_used: 10, total_km: 186.3 },
  routes: [{ engineer_id: 'E09', stops: [{ request_id: 'R901', start: '14:41' }, { request_id: 'R042', start: '16:27' }, { request_id: 'R043', start: '17:11' }] },
           { engineer_id: 'E07', stops: [{ request_id: 'R004', start: '14:48' }] },
           { engineer_id: 'E10', stops: [{ request_id: 'R005', start: '14:43' }, { request_id: 'R006', start: '15:40' }] }],
  diff: { requests: {
    R901: { status: 'newly_assigned', engineer_id: 'E09' }, R004: { status: 'moved', from: 'E01', to: 'E07', shift_min: 0 },
    R005: { status: 'moved', from: 'E01', to: 'E10', shift_min: 0 }, R006: { status: 'moved', from: 'E01', to: 'E10', shift_min: 0 },
    R042: { status: 'shifted', engineer_id: 'E09', shift_min: 48 }, R043: { status: 'shifted', engineer_id: 'E09', shift_min: 21 },
    R001: { status: 'unchanged' } },
    engineers: { E01: { status: 'removed' }, E09: { status: 'changed' }, E07: { status: 'changed' }, E10: { status: 'changed' } } },
};

describe('разбор', () => {
  it('баннер', () => {
    expect(banner(plan)).toEqual({ title: 'План пересчитан от 14:00', sub: '2 события · 4,1 с · черновик, инженеры ещё не уведомлены' });
  });
  it('плитки «было»', () => {
    expect(deltaTiles(plan, { assigned: 48, unassigned: 2, engineers_used: 9, total_km: 185.2 })).toEqual([
      { k: 'Назначено', b: '49 / 51', a: 'было 48', bg: 'var(--green-tint)', c: 'var(--green-ink)' },
      { k: 'Инженеров', b: '10', a: 'было 9', bg: 'var(--yellow-tint)', c: 'var(--ink-3)' },
      { k: 'Пробег, км', b: '186', a: 'было 185', bg: 'var(--blue-tint)', c: 'var(--amber-ink)' }]);
  });
  it('группы', () => {
    const g = groups(plan, names);
    expect(g.map(x => [x.t, x.n])).toEqual([['Новые', 1], ['Переданы', 3], ['Сдвинуты', 2]]);
    expect(g[0].items).toEqual([{ id: 'R901', text: '→ Макаров', t: '14:41' }]);
    expect(g[1].items[0]).toEqual({ id: 'R004', text: 'Горбанев → Андреев', t: '14:48' });
    expect(g[2].items[0]).toEqual({ id: 'R042', text: 'Макаров, +48 мин', t: '16:27' });
  });
  it('пояснение', () => {
    expect(insight(plan, names)).toBe('Заявки Горбанева переданы: Андреев, Царьков. Срочная R901 у Макарова, его 2 заявки сдвинуты внутри окон. Все заявки размещены.');
  });
  it('после принятия', () => {
    expect(affectedText(['E07', 'E09'], names)).toBe('План принят · изменения затрагивают 2 инженеров: Андреев, Макаров');
    expect(affectedText([], names)).toBe('План принят · маршруты инженеров не изменились');
    expect(affectedText(['E07'], names)).toBe('План принят · изменения затрагивают 1 инженера: Андреев');
    expect(affectedText(['E01', 'E07', 'E09', 'E10', 'E01'], names)).toMatch(/затрагивают 5 инженеров:/);
  });
});

describe('падеж фамилии', () => {
  it('«у/от кого»', () => {
    expect(['Макаров', 'Козырь', 'Белоновский', 'Кузьмина'].map(INS)).toEqual(['Макарова', 'Козыря', 'Белоновского', 'Кузьминой']);
    expect(GEN('Белоновский')).toBe('Белоновского');
  });
});

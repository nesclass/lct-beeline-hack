import { describe, expect, it } from 'vitest';
import { kpis, shortReason, tightList, unassignedList } from './plan.js';

const dict = { skills: { connect: 'Работы на подключение и дозаказы' }, transport: { foot: 'Пешеход' } };
const reqs = {
  R056: { type: 'Подключение', skill: 'connect', required_transport: 'foot', tw_start: 1080, tw_end: 1200, duration: 70, duration_text: '70 мин' },
  R057: { type: 'Авария на узле', skill: 'emergency', required_transport: null, tw_start: 1260, tw_end: 1320, duration: 80, duration_text: '80 мин' }};

describe('короткая причина', () => {
  it('по коду', () => {
    expect(shortReason(reqs.R056, { code: 'TRANSPORT', no_candidates: true }, dict))
      .toBe('Нужен пеший инженер с навыком «Подключение» — таких в смене нет');
    expect(shortReason(reqs.R057, { code: 'SHIFT_FIT', no_candidates: true }, dict))
      .toBe('80 минут работы не помещаются до конца ни одной смены');
    expect(shortReason(reqs.R057, { code: 'WINDOW_REACH', no_candidates: true }, dict)).toBe('Никто не успевает доехать до конца окна');
    expect(shortReason(reqs.R057, { code: 'BUSY', no_candidates: false, probes: [{}, {}] }, dict)).toBe('Все 2 подходящих инженера заняты');
    expect(shortReason(reqs.R057, { code: 'DISPLACED' }, dict)).toBe('Вытеснена срочной заявкой');
    expect(shortReason(reqs.R057, { code: 'ENGINEER_LOST' }, dict)).toBe('Инженер выбыл, у остальных нет места в окне');
  });
});

const view = {
  plan: { unassigned: ['R056'], metrics: { assigned: 48, unassigned: 2, engineers_used: 9, engineers_total: 12, total_km: 185.2 },
          assignments: { R056: { engineer_id: null, reason: { code: 'TRANSPORT', no_candidates: true } } },
          routes: [{ engineer_id: 'E01', stops: [{ request_id: 'A', start: '14:03', slack_min: 50 }, { request_id: 'B', start: '10:14', slack_min: 50 }] }] },
  risk: { tol: { A: 3, B: 12 }, stress: { expected_late: 0.41 } },
  engineers: { E01: { name: 'Горбанев' } }, requests: reqs, dict };

describe('плитки и списки', () => {
  it('плитки', () => {
    expect(kpis(view)).toEqual([
      { label: 'Назначено', val: '48 / 50', c: 'var(--green)' }, { label: 'Инженеров', val: '9 / 12', c: 'var(--yellow)' },
      { label: 'Пробег', val: '185 км', c: 'var(--blue)' }, { label: 'Запас < 10 мин', val: '1', c: 'var(--red)' },
      { label: 'Ожид. опозданий', val: '0,4', c: 'var(--amber)' }]);
  });
  it('без оценки риска — прочерки', () => {
    expect(kpis({ ...view, risk: null }).slice(3).map(k => k.val)).toEqual(['—', '—']);
  });
  it('не назначены и мало запаса', () => {
    expect(unassignedList(view)).toEqual([{ id: 'R056', type: 'Подключение', win: '18:00–20:00',
      why: 'Нужен пеший инженер с навыком «Подключение» — таких в смене нет' }]);
    expect(tightList(view, { E01: { main: '#E4572E' } })).toEqual([
      { id: 'A', eng: 'Горбанев', ec: '#E4572E', t: '14:03', tol: 3, tone: 'crit' },
      { id: 'B', eng: 'Горбанев', ec: '#E4572E', t: '10:14', tol: 12, tone: 'warn' }]);
  });
});

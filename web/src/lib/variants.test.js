import { describe, expect, it } from 'vitest';
import { compareCharts, variantRows } from './variants.js';

const ROWS = [
  { key: 'baseline', name: 'Базовый', desc: 'по порядку', plan_id: 'p0', assigned: 46, total: 50, engineers_used: 11, engineers_total: 12, total_km: 247, expected_late: 0.9, overtime_min: 14 },
  { key: 'econom', name: 'Экономный', desc: 'без запаса', plan_id: 'p1', assigned: 48, total: 50, engineers_used: 8, engineers_total: 12, total_km: 174, expected_late: 1.6, overtime_min: 22 },
  { key: 'balanced', name: 'Сбалансированный', desc: 'запас 10 %', plan_id: 'p2', assigned: 48, total: 50, engineers_used: 9, engineers_total: 12, total_km: 185, expected_late: 0.4, overtime_min: 6 },
  { key: 'reliable', name: 'Надёжный', desc: 'запас 20 %', plan_id: 'p3', assigned: 47, total: 50, engineers_used: 10, engineers_total: 12, total_km: 199, expected_late: 0.1, overtime_min: 0 }];

describe('таблица вариантов', () => {
  it('подписи, рекомендация, выбор, красные опоздания', () => {
    const t = variantRows(ROWS, 'balanced', 'balanced', 0.5);
    expect(t[2]).toMatchObject({ asg: '48 / 50', eng: 9, km: '185', late: '0,4', over: '6 мин', rec: true, on: true, lateBad: false, color: '#FFD200' });
    expect(t[1]).toMatchObject({ lateBad: true, on: false, rec: false });
    expect(t[0].color).toBe('#C9CED6');
  });
});

describe('сравнение', () => {
  it('ширина полосы — доля от наибольшего', () => {
    const [eng, km, late] = compareCharts(ROWS);
    expect(eng).toMatchObject({ title: 'Инженеров задействовано', sub: 'из 12' });
    expect(eng.rows.map(r => r.v)).toEqual(['11', '8', '9', '10']);
    expect(km.rows[0].w).toBe(100);
    expect(Math.round(km.rows[1].w)).toBe(70);
    expect(late.rows.map(r => r.v)).toEqual(['0,9', '1,6', '0,4', '0,1']);
    expect(late.rows[1].w).toBe(100);
  });
});

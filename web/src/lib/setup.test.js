import { describe, expect, it } from 'vitest';
import { MARGINS, applyMargin, marginLine, marginOf, sessionMix } from './setup.js';

describe('запас', () => {
  it('подпись', () => {
    expect(marginLine(MARGINS.balanced)).toBe('+10 % к работе и дороге, +2 мин на каждый переезд');
    expect(marginLine(MARGINS.econom)).toBe('без запаса: норматив и время в пути как есть');
    expect(marginLine([20, 10, 0])).toBe('+20 % к работе, +10 % к дороге');
  });
  it('выбор пресета меняет три поля и подпись', () => {
    const st = applyMargin({ work_pct: 0, travel_pct: 0, travel_min: 0, margin: 'econom', engine: 'ortools' }, 'reliable');
    expect(st).toMatchObject({ work_pct: 20, travel_pct: 20, travel_min: 5, margin: 'reliable', engine: 'ortools' });
    expect(marginOf(st)).toBe('reliable');
    expect(marginOf({ ...st, travel_min: 3 })).toBe('custom');
  });
});

describe('данные сессии', () => {
  it('состав по навыкам и транспорту', () => {
    const mix = sessionMix([{ skill: 'local' }, { skill: 'local' }, { skill: 'emergency' }],
                           [{ transport: 'car' }, { transport: 'foot' }, { transport: 'car' }]);
    expect(mix[0]).toEqual({ t: 'Заявки по навыкам', total: '3 заявки', parts: [
      { l: 'Локальные', n: 2, c: 'var(--sk-local)' }, { l: 'Подключение', n: 0, c: 'var(--sk-connect)' }, { l: 'Аварийные', n: 1, c: 'var(--sk-em)' }] });
    expect(mix[1].total).toBe('3 инженера');
    expect(mix[1].parts.map(p => [p.l, p.n])).toEqual([['Авто', 2], ['Пешком', 1], ['Вело', 0], ['Транспорт', 0]]);
  });
});

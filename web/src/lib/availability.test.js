import { describe, expect, it } from 'vitest';
import { initialState, quickTimes, summary, toBody } from './availability.js';

const e = { id: 'E01', shift_start: '09:00', shift_end: '18:00' };
const cur = { request_id: 'R003', finish: '12:57' };

describe('окно доступности', () => {
  it('по умолчанию — уйдёт сейчас, доделает текущую', () => {
    expect(initialState(e, null, '13:45', cur)).toEqual({ mode: 'leave', time: '13:45', until: '14:45', finish_current: true, reason: '' });
  });
  it('из события в очереди', () => {
    expect(initialState(e, { type: 'engineer_break', time: '14:00', until: '15:00', reason: 'обед' }, '13:45', null))
      .toMatchObject({ mode: 'break', time: '14:00', until: '15:00', reason: 'обед' });
    expect(initialState(e, { type: 'engineer_unavailable', mode: 'absent', time: '09:00' }, '08:00', null).mode).toBe('absent');
  });
  it('время ухода из очереди не раньше текущих часов', () => {
    expect(initialState(e, { type: 'engineer_unavailable', mode: 'leave', time: '10:00' }, '13:45', null).time).toBe('13:45');
    expect(initialState(e, { type: 'engineer_unavailable', mode: 'leave', time: '15:00' }, '13:45', null).time).toBe('15:00');
  });
  it('быстрые времена', () => {
    expect(quickTimes('13:45', cur)).toEqual([{ t: 'сейчас 13:45', v: '13:45' }, { t: 'после текущей · 12:57', v: '12:57' }]);
    expect(quickTimes('13:45', null)).toEqual([{ t: 'сейчас 13:45', v: '13:45' }]);
  });
  it('тело запроса', () => {
    expect(toBody({ mode: 'schedule' })).toBeNull();
    expect(toBody({ mode: 'leave', time: '14:00', until: '15:00', finish_current: false, reason: ' семья ' }))
      .toEqual({ mode: 'leave', time: '14:00', finish_current: false, reason: 'семья' });
    expect(toBody({ mode: 'break', time: '14:00', until: '15:00', finish_current: true, reason: '' }))
      .toEqual({ mode: 'break', time: '14:00', until: '15:00', reason: '' });
    expect(toBody({ mode: 'absent', reason: '' })).toEqual({ mode: 'absent', reason: '' });
  });
  it('итог последствий', () => {
    expect(summary({ released: [{ taker: { name: 'Андреев' } }, { taker: null }, { taker: { name: 'Царьков' } }], can_take: 2 }))
      .toEqual({ title: 'Освободятся 3 заявки', can: 'подобрать можно 2' });
    expect(summary({ released: [], can_take: 0 })).toEqual({ title: 'Заявки не освобождаются', can: '' });
  });
});

import { describe, expect, it } from 'vitest';
import { eventRows, forecast, leavingOf } from './changes.js';

const names = { E01: 'Горбанев', E09: 'Макаров' };
const requests = [{ id: 'R017', address: 'Ключевая ул., 8', type: 'Подключение' }];
const engineers = [{ id: 'E01', shift_start: '09:00' }, { id: 'E09', shift_start: '09:00' }];
const pending = [
  { id: 'EV1', type: 'urgent_request', time: '13:30', at: '13:30', request: { id: 'R901', type: 'Обрыв магистрали', address: 'Луганская 7', tw_start: '13:30', tw_end: '15:30' } },
  { id: 'EV2', type: 'engineer_unavailable', time: '14:00', at: '13:45', engineer_id: 'E01', mode: 'leave', finish_current: true, reason: '' },
  { id: 'EV3', type: 'cancel_request', time: '13:50', at: '13:50', request_id: 'R017', reason: 'клиент отказался' },
  { id: 'EV4', type: 'move_request', time: '13:55', at: '13:55', request_id: 'R017', engineer_id: 'E09', from: 'E01' },
  { id: 'EV5', type: 'engineer_break', time: '15:00', until: '15:30', at: '13:56', engineer_id: 'E09', reason: '' },
  { id: 'EV6', type: 'engineer_unavailable', time: '09:00', at: '13:57', engineer_id: 'E09', mode: 'absent', finish_current: false }];

describe('строки очереди', () => {
  const rows = eventRows(pending, names, requests, engineers);
  it('иконки и заголовки', () => {
    expect(rows.map(r => [r.ic, r.title])).toEqual([
      ['⚡', 'Срочная R901 · 13:30'], ['⏏', 'Горбанев уходит в 14:00 · 13:45'], ['✕', 'Отмена R017 · 13:50'],
      ['↪', 'R017 → Макаров · 13:55'], ['☕', 'Макаров: перерыв 15:00–15:30 · 13:56'], ['⏏', 'Макаров не выйдет сегодня · 13:57']]);
  });
  it('описания', () => {
    expect(rows[0].desc).toBe('Обрыв магистрали, Луганская 7, окно 13:30–15:30');
    expect(rows[1].desc).toBe('доделает текущую заявку');
    expect(rows[2].desc).toBe('клиент отказался');
    expect(rows[3].desc).toBe('было у Горбанев');
  });
  it('куда ведёт «изменить»', () => {
    expect(rows.map(r => r.edit.kind)).toEqual(['event', 'availability', 'event', 'request', 'availability', 'availability']);
    expect(rows[3].edit).toEqual({ kind: 'request', rid: 'R017' });
  });
});

describe('прогноз и уходы', () => {
  it('если оставить как есть', () => {
    expect(forecast({ orphaned: ['A', 'B', 'C'], urgent_unassigned: 1, expected_late: 0.41 })).toEqual([
      { t: 'Заявок без исполнителя', n: '3', c: 'var(--red-ink)' }, { t: 'Срочная не назначена', n: '1', c: 'var(--red-ink)' },
      { t: 'Ожидаемых опозданий', n: '0,4', c: 'var(--ink)' }]);
    expect(forecast({ orphaned: [], urgent_unassigned: 0, expected_late: null })[0].c).toBe('var(--ink)');
  });
  it('кто когда уходит', () => {
    expect(leavingOf(pending, engineers)).toEqual({ E01: 840, E09: 540 });
  });
});

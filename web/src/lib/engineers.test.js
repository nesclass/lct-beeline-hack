import { describe, expect, it } from 'vitest';
import { engineerCard, engineerRows, queuedFor } from './engineers.js';

const engineers = [
  { id: 'E01', name: 'Горбанев', shift_start: '09:00', shift_end: '18:00', skills: ['local', 'connect', 'emergency'], transport: 'car', unavailable_from: null },
  { id: 'E08', name: 'Бузань', shift_start: '13:00', shift_end: '22:00', skills: ['connect'], transport: 'public', unavailable_from: null },
  { id: 'E03', name: 'Саламатин', shift_start: '12:00', shift_end: '21:00', skills: ['local'], transport: 'car', unavailable_from: null },
  { id: 'E09', name: 'Макаров', shift_start: '09:00', shift_end: '18:00', skills: ['local'], transport: 'car', unavailable_from: '10:00' }];
const view = { plan: { routes: [
  { engineer_id: 'E01', total_km: 22.6, utilization: 0.56, stops: [
    { request_id: 'R003', start: '12:20', finish: '12:57', locked: true }, { request_id: 'R004', start: '14:03', finish: '15:00' },
    { request_id: 'R005', start: '14:43', finish: '15:20' }] },
  { engineer_id: 'E08', total_km: 0, utilization: 0, stops: [] },
  { engineer_id: 'E03', total_km: 19.5, utilization: 0.48, stops: [{ request_id: 'R012', start: '13:00', finish: '14:00' }] },
  { engineer_id: 'E09', total_km: 5, utilization: 0.1, stops: [{ request_id: 'R041', start: '09:30', finish: '10:00', locked: true }], unavailable_from: '10:00' }] },
  requests: { R003: { type: 'Дозаказ оборудования' }, R004: { type: 'Подключение' }, R005: { type: 'Настройка Wi-Fi' }, R012: { type: 'Нет линка' }, R041: { type: 'x' } } };
const colors = { E01: { main: '#E4572E', tint: '#FCE3DB' }, E08: { main: '#5B7C99', tint: '#E3EAF0' }, E03: { main: '#2FA84F', tint: '#DDF3E2' }, E09: { main: '#3F51B5', tint: '#E0E4F7' } };
const pending = [{ id: 'EV1', type: 'engineer_unavailable', engineer_id: 'E01', time: '14:00', mode: 'leave' }];

describe('строки инженеров', () => {
  const rows = engineerRows(engineers, view, colors, 12 * 60 + 30, pending);
  it('поля и состояния', () => {
    expect(rows[0]).toMatchObject({ name: 'Горбанев', ini: 'ГО', c: '#E4572E', tr: 'Авто', shift: '09:00–18:00', n: 3, km: '22,6', load: 56,
                                    st: 'уйдёт в 14:00', stColor: 'var(--amber-ink)' });
    expect(rows[0].skills.map(s => s.t)).toEqual(['Локальные', 'Подключение', 'Аварийные']);
    expect(rows[1]).toMatchObject({ st: 'в резерве', stColor: 'var(--muted)', c: '#C9CED6', n: '—', km: '—', load: 0 });
    expect(rows[2]).toMatchObject({ st: 'на смене' });
    expect(rows[3]).toMatchObject({ st: 'недоступен с 10:00', stColor: 'var(--red-ink)' });
  });
  it('смена позже часов', () => {
    expect(engineerRows(engineers, view, colors, 11 * 60, [])[2].st).toBe('с 12:00');
  });
  it('событие в очереди', () => { expect(queuedFor('E01', pending).id).toBe('EV1'); expect(queuedFor('E03', pending)).toBeNull(); });
});

describe('карточка', () => {
  it('сейчас, дальше, список', () => {
    const c = engineerCard('E01', engineers, view, colors, 12 * 60 + 30, pending);
    expect(c.now).toBe('R003 · Дозаказ оборудования · до 12:57');
    expect(c.next).toBe('2 заявки до конца смены');
    expect(c.km).toBe('22,6 км за день');
    expect(c.line).toBe('На смене · 09:00–18:00 · Авто');
    expect(c.list).toEqual([{ t: '12:20', id: 'R003', type: 'Дозаказ оборудования', cur: true },
                            { t: '14:03', id: 'R004', type: 'Подключение', cur: false }, { t: '14:43', id: 'R005', type: 'Настройка Wi-Fi', cur: false }]);
  });
});

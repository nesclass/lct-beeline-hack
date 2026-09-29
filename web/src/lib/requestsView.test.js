import { describe, expect, it } from 'vitest';
import { counts, executor, filterRows, reasonCard, stateOf, streetOf } from './requestsView.js';

const view = { plan: {
  routes: [{ engineer_id: 'E05', stops: [{ request_id: 'R022', start: '14:40' }] }],
  assignments: {
    R022: { engineer_id: 'E05' },
    R056: { engineer_id: null, text: 'Заявка R056 … не назначена: нет инженера с навыком «Работы на подключение» и транспортом «Пешеход». По инженерам — …',
            reason: { code: 'TRANSPORT', no_candidates: true, compat: { E02: 'TRANSPORT', E04: 'SKILL' }, probes: [] } },
    R057: { engineer_id: null, text: '…', reason: { code: 'SHIFT_FIT', no_candidates: true, compat: { E01: 'SHIFT_FIT' }, probes: [] } } } },
  requests: { R056: { skill: 'connect', required_transport: 'foot', duration: 70 }, R057: { skill: 'emergency', duration: 80 } } };
const names = { E05: 'Белоновский', E02: 'Паршин', E04: 'Козырь', E01: 'Горбанев' };
const list = [
  { id: 'R022', status: 'assigned', pending: [], priority: 'normal', address: 'Кавказский б-р, 12', district: 'Царицыно' },
  { id: 'R056', status: 'unassigned', pending: [], priority: 'normal', address: 'Шипиловская ул., 28', district: 'Орехово' },
  { id: 'R057', status: 'unassigned', pending: [], priority: 'normal', address: 'Харьковская, 5', district: 'Бирюлёво' },
  { id: 'R060', status: 'new', pending: ['new_request'], priority: 'normal', address: 'Кировоградская, 13', district: 'Чертаново', by_dispatcher: true },
  { id: 'R901', status: 'new', pending: ['urgent_request'], priority: 'urgent', address: 'ул. Луганская, 7', district: 'Царицыно', by_dispatcher: true },
  { id: 'R017', status: 'cancelled', pending: [], priority: 'normal', address: 'Ключевая, 8', district: 'Братеево' }];

describe('состояние', () => {
  it('подписи', () => {
    expect(list.map(r => stateOf(r, view).text)).toEqual(['Назначена', 'Не назначена', 'Не влезает в смену',
      'Ждёт перепланирования', 'Ждёт перепланирования', 'Отменена']);
    expect(stateOf({ ...list[0], pending: ['move_request'] }, view).key).toBe('waiting');
  });
  it('счётчики и фильтр с поиском', () => {
    expect(counts(list, view)).toEqual({ all: 6, assigned: 1, unassigned: 2, waiting: 2, urgent: 1, cancelled: 1 });
    expect(filterRows(list, view, 'waiting', '').map(r => r.id)).toEqual(['R060', 'R901']);
    expect(filterRows(list, view, 'all', 'луган').map(r => r.id)).toEqual(['R901']);
    expect(filterRows(list, view, 'all', 'r05').map(r => r.id)).toEqual(['R056', 'R057']);
  });
});

describe('исполнитель и причина', () => {
  it('кто и когда', () => {
    expect(executor(list[0], view, names)).toBe('Белоновский · 14:40');
    expect(executor(list[1], view, names)).toBe('—');
  });
  it('карточка причины по инженерам', () => {
    expect(reasonCard(list[1], view, names)).toEqual({ title: 'Нужен пеший инженер с навыком «Подключение» — таких в смене нет',
      text: 'Заявка R056 … не назначена: нет инженера с навыком «Работы на подключение» и транспортом «Пешеход».',
      chips: ['Паршин — транспорт', 'Козырь — навык'] });
    expect(reasonCard(list[0], view, names)).toBeNull();
  });
});

describe('streetOf', () => {
  it('убирает район из начала адреса — он и так строкой ниже', () => {
    expect(streetOf({ address: 'Бирюлёво Западное, ул. Харьковская, д. 5', district: 'Бирюлёво Западное' })).toBe('ул. Харьковская, д. 5');
  });
  it('адрес без района в начале — как есть', () => {
    expect(streetOf({ address: 'Кавказский б-р, 12', district: 'Царицыно' })).toBe('Кавказский б-р, 12');
    expect(streetOf({ address: 'Царицыно', district: 'Царицыно' })).toBe('Царицыно');
  });
});

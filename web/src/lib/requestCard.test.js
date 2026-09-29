import { describe, expect, it } from 'vitest';
import { cardFor } from './requestCard.js';

const view = {
  plan: {
    routes: [{ engineer_id: 'E05', stops: [{ request_id: 'R024' }, { request_id: 'R025', arrive: '16:44', start: '16:52', finish: '18:02', slack_min: 70 }, { request_id: 'R026' }] }],
    assignments: {
      R025: { engineer_id: 'E05', locked: false, text: 'длинный текст', reason: {
        position: { seq: 2, prev_request_id: 'R024', next_request_id: 'R026' }, arrive: '16:44', start: '16:52', finish: '18:02', delta_km: 2.1,
        alternatives: [
          { engineer_id: 'E02', feasible: false, blocker: { code: 'SKILL', text: 'нет нужного навыка' } },
          { engineer_id: 'E11', feasible: true, delta_km: 4.8, arrive: '16:20', start: '16:20' },
          { engineer_id: 'E03', feasible: false, blocker: { code: 'BUSY', text: 'после R020 (до 15:40) доедет только к 18:30' } },
          { engineer_id: 'E06', feasible: false, blocker: { code: 'WINDOW_REACH', text: 'не успевает доехать' } }] } },
      R056: { engineer_id: null, text: 'Заявка R056 не назначена: нет инженера…', reason: { code: 'TRANSPORT', no_candidates: true, compat: {} } },
    },
  },
  risk: { tol: { R025: 80 } },
  engineers: { E05: { name: 'Белоновский', transport: 'car' }, E02: { name: 'Паршин' }, E11: { name: 'Демин' }, E03: { name: 'Саламатин' }, E06: { name: 'Рыбин' } },
  requests: { R025: { type: 'Дозаказ оборудования', address: 'ул. Бакинская, 21', skill: 'connect', required_transport: null, tw_start: 960, tw_end: 1080 },
              R056: { type: 'Подключение', address: 'Шипиловская ул., 28', skill: 'connect', required_transport: 'foot', tw_start: 1080, tw_end: 1200 },
              R099: { type: 'Нет линка', address: 'x', skill: 'local', tw_start: 900, tw_end: 1000 } },
};
const colors = { E05: { main: '#C2185B', tint: '#F9DCE8' }, E02: { main: '#F29E1F' }, E11: { main: '#6D4C41' }, E03: { main: '#2FA84F' }, E06: { main: '#00A3A3' } };

describe('карточка назначенной заявки', () => {
  const c = cardFor(view, colors, 'R025');
  it('шапка и поля', () => {
    expect(c).toMatchObject({ id: 'R025', status: { text: 'назначена', tone: 'ok' }, tint: '#F9DCE8',
                              type: 'Дозаказ оборудования', addr: 'ул. Бакинская, 21' });
    expect(c.rows).toEqual([['Инженер', 'Белоновский · 2-я в маршруте', '#C2185B'], ['Окно клиента', '16:00–18:00'],
                            ['Приезд · работа', '16:44 · 16:52–18:02'], ['Запас', '80 мин', 'var(--green-ink)']]);
  });
  it('почему он и проверки', () => {
    expect(c.why).toBe('Белоновский ближе всех из подходящих: вставка между R024 и R026 добавляет 2,1 км. Демин тоже может, но +4,8 км.');
    expect(c.checks).toEqual(['навык «Подключение»', 'транспорт: авто', 'окно 16:00–18:00', 'в пределах смены']);
  });
  it('кто ещё мог бы: сначала можно, потом заняты, потом не подходят', () => {
    expect(c.alts).toEqual([
      { eid: 'E11', name: 'Демин', c: '#6D4C41', text: '+4,8 км, приезд 16:20', tone: 'ok' },
      { eid: 'E03', name: 'Саламатин', c: '#2FA84F', text: 'занят до 15:40', tone: 'warn' },
      { eid: 'E06', name: 'Рыбин', c: '#00A3A3', text: 'не успевает к окну', tone: 'warn' },
      { eid: 'E02', name: 'Паршин', c: '#F29E1F', text: 'нет навыка', tone: 'bad' }]);
    expect(c.movable).toEqual([{ eid: 'E11', name: 'Демин', text: '+4,8 км, приезд 16:20' }]);
  });
});

describe('сортировка «можно» — по возрастанию км, даже если сервер отдал в другом порядке', () => {
  const view2 = {
    plan: {
      routes: [{ engineer_id: 'E05', stops: [{ request_id: 'R030' }] }],
      assignments: {
        R030: { engineer_id: 'E05', locked: false, reason: {
          position: { seq: 1 }, arrive: '10:00', start: '10:00', finish: '10:30', delta_km: 1,
          alternatives: [
            { engineer_id: 'E11', feasible: true, delta_km: 9.0, arrive: '10:10' },
            { engineer_id: 'E03', feasible: true, delta_km: 2.5, arrive: '10:05' }] } },
      },
    },
    risk: { tol: { R030: 40 } },
    engineers: { E05: { name: 'Белоновский', transport: 'car' }, E11: { name: 'Демин' }, E03: { name: 'Саламатин' } },
    requests: { R030: { type: 'Тест', address: 'x', skill: 'connect', tw_start: 600, tw_end: 630 } },
  };
  it('можно-альтернативы упорядочены по delta_km, а не по позиции в ответе', () => {
    const c = cardFor(view2, colors, 'R030');
    expect(c.alts).toEqual([
      { eid: 'E03', name: 'Саламатин', c: '#2FA84F', text: '+2,5 км, приезд 10:05', tone: 'ok' },
      { eid: 'E11', name: 'Демин', c: '#6D4C41', text: '+9 км, приезд 10:10', tone: 'ok' }]);
    expect(c.movable).toEqual([
      { eid: 'E03', name: 'Саламатин', text: '+2,5 км, приезд 10:05' },
      { eid: 'E11', name: 'Демин', text: '+9 км, приезд 10:10' }]);
  });
});

describe('другие состояния', () => {
  it('не назначена — текст причины, без «почему он»', () => {
    const c = cardFor(view, colors, 'R056');
    expect(c.status).toEqual({ text: 'не назначена', tone: 'bad' });
    expect([c.why, c.explain]).toEqual([null, 'Заявка R056 не назначена: нет инженера…']);
  });
  it('не в плане', () => {
    expect(cardFor(view, colors, 'R099').status).toEqual({ text: 'ещё не в расписании', tone: 'warn' });
  });
  it('нет такой', () => { expect(cardFor(view, colors, 'R777')).toBeNull(); });
});

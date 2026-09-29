import { describe, expect, it } from 'vitest';
import { contextLabel, firstQuestion, placeholder, restore, rowView, switchTo } from './assistantView.js';

describe('ассистент', () => {
  it('строки: точка инженера или по кругу, цвет значения', () => {
    const colors = { E05: { main: '#C2185B' } };
    expect(rowView({ name: 'Белоновский', engineer_id: 'E05', a: 'приезд 15:48', v: '+2,1 км', tone: 'ok' }, colors, 0))
      .toEqual({ n: 'Белоновский', dot: '#C2185B', a: 'приезд 15:48', v: '+2,1 км', vc: 'var(--green)' });
    expect(rowView({ name: 'Пробег, км', a: '185 → ', v: '186', tone: 'warn' }, colors, 2).dot).toBe('var(--blue)');
  });
  it('первый вопрос и подсказка в поле', () => {
    expect(firstQuestion({ kind: 'request', id: 'R025' })).toBe('Почему так назначена R025?');
    expect(firstQuestion({ kind: 'plan' })).toBeNull();
    expect(placeholder({ kind: 'engineer' })).toBe('Спросите о последствиях');
    expect(placeholder({ kind: 'plan' })).toBe('Спросите о плане или попросите изменить');
  });
});

describe('переключение и восстановление разговора', () => {
  it('переключение архивирует контекст и history целиком, не только подписи', () => {
    const state = {
      id: 1, context: { kind: 'request', id: 'R1' }, label: 'заявка R1',
      messages: [{ role: 'user', text: 'Почему так назначена R1?' }], suggestions: ['А если поменять?'],
      history: [{ role: 'user', content: 'Почему так назначена R1?' }], past: [],
    };
    const next = switchTo(state, { kind: 'engineer', id: 'E1' });
    expect(next.context).toEqual({ kind: 'engineer', id: 'E1' });
    expect(next.messages).toEqual([]);
    expect(next.past).toEqual([{
      id: 1, context: { kind: 'request', id: 'R1' }, label: 'заявка R1',
      messages: [{ role: 'user', text: 'Почему так назначена R1?' }], suggestions: ['А если поменять?'],
      history: [{ role: 'user', content: 'Почему так назначена R1?' }],
    }]);
  });

  it('без смены контекста ничего не архивирует и не трогает состояние', () => {
    const state = {
      id: 1, context: { kind: 'request', id: 'R1' }, label: 'заявка R1',
      messages: [{ role: 'user', text: 'q' }], suggestions: [], history: [], past: [],
    };
    expect(switchTo(state, { kind: 'request', id: 'R1' })).toBe(state);
    expect(switchTo(state, null)).toBe(state);
  });

  it('восстановление возвращает контекст и history для сервера, текущий разговор уходит в past', () => {
    const past = [{
      id: 5, context: { kind: 'request', id: 'R1' }, label: 'заявка R1',
      messages: [{ role: 'user', text: 'Почему так назначена R1?' }], suggestions: [],
      history: [{ role: 'user', content: 'Почему так назначена R1?' }],
    }];
    const state = {
      id: 2, context: { kind: 'engineer', id: 'E1' }, label: 'инженер E1',
      messages: [{ role: 'user', text: 'Что будет?' }], suggestions: ['А если продлить?'],
      history: [{ role: 'user', content: 'Что будет?' }], past,
    };
    const next = restore(state, 0);
    expect(next).toEqual({
      id: 5, context: { kind: 'request', id: 'R1' }, label: 'заявка R1',
      messages: [{ role: 'user', text: 'Почему так назначена R1?' }], suggestions: [],
      history: [{ role: 'user', content: 'Почему так назначена R1?' }],
      past: [{
        id: 2, context: { kind: 'engineer', id: 'E1' }, label: 'инженер E1',
        messages: [{ role: 'user', text: 'Что будет?' }], suggestions: ['А если продлить?'],
        history: [{ role: 'user', content: 'Что будет?' }],
      }],
    });
  });
});

describe('подпись «видит» до первого ответа', () => {
  const view = { meta: { date: '2026-08-17' }, plan: { now: '14:00' } };
  it('как у сервера', () => {
    expect(contextLabel({ kind: 'request', id: 'R014' }, view)).toBe('заявка R014 · план на 17.08');
    expect(contextLabel({ kind: 'engineer', id: 'E01' }, view, { E01: 'Горбанев' })).toBe('инженер Горбанев · недоступность');
    expect(contextLabel({ kind: 'changes' }, view)).toBe('перепланирование от 14:00');
    expect(contextLabel({ kind: 'changes' }, { plan: { now: null } })).toBe('изменения в очереди');
    expect(contextLabel({ kind: 'plan' }, {})).toBe('план на сегодня');
    expect(contextLabel(null, view)).toBe('');
  });
});

import { describe, expect, it } from 'vitest';
import { sessionPill, whenText } from './labels.js';

describe('подписи', () => {
  it('статус сессии', () => {
    expect(sessionPill('planned', 0)).toEqual({ text: 'План актуален', tone: 'ok' });
    expect(sessionPill('dirty', 3)).toEqual({ text: '3 изменения ждут', tone: 'warn' });
    expect(sessionPill('dirty', 1)).toEqual({ text: '1 изменение ждёт', tone: 'warn' });
    expect(sessionPill('draft', 0)).toEqual({ text: 'Черновик', tone: 'warn' });
    expect(sessionPill('new', 0)).toEqual({ text: 'Плана нет', tone: 'gray' });
  });
  it('когда', () => {
    const now = new Date(2026, 8, 28, 15, 0).getTime() / 1000;
    expect(whenText(new Date(2026, 8, 28, 11, 42).getTime() / 1000, now)).toBe('сегодня, 11:42');
    expect(whenText(new Date(2026, 8, 27, 18, 20).getTime() / 1000, now)).toBe('вчера, 18:20');
    expect(whenText(new Date(2026, 8, 12, 10, 5).getTime() / 1000, now)).toBe('12.09, 10:05');
  });
});

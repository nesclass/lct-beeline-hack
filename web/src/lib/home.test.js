import { describe, expect, it } from 'vitest';
import { decodeFile, scenarioCards, sessionRows } from './home.js';

describe('карточки сценариев', () => {
  it('фон по кругу, жёлтая кнопка у первой, районы словами', () => {
    const list = ['a', 'b', 'c', 'd'].map(id => ({ id, title: id, description: 'd', engineers: 12, requests: 59, area: 'ЮАО', districts: 9 }));
    const c = scenarioCards(list);
    expect(c.map(x => x.bg)).toEqual(['var(--yellow-card)', 'var(--peach)', 'var(--blue-card)', 'var(--yellow-card)']);
    expect(c.map(x => x.primary)).toEqual([true, false, false, false]);
    expect(c[0]).toMatchObject({ area: 'ЮАО', districts: '9 районов', eng: 12, req: 59 });
  });
});

describe('недавние сессии', () => {
  it('короткий номер, статус, куда вести', () => {
    const now = new Date(2026, 8, 28, 15, 0).getTime() / 1000;
    const rows = sessionRows([
      { session_id: '7f3a1b2c', title: 'Обычный день', clock: '14:00', status: 'planned', pending: 0, updated_at: now - 3600 },
      { session_id: 'a91c0000', title: 'Некомплект', clock: '09:00', status: 'new', pending: 0, updated_at: now - 86400 },
    ], now);
    expect(rows[0]).toMatchObject({ short: 's-7f3a', scen: 'Обычный день', clock: '14:00', href: '/s/7f3a1b2c/plan',
                                    pill: { text: 'План актуален', tone: 'ok' }, upd: 'сегодня, 14:00' });
    expect(rows[1].href).toBe('/s/a91c0000/setup');
  });
});

describe('чтение файла', () => {
  it('UTF-8 и cp1251', () => {
    expect(decodeFile(new TextEncoder().encode('Царицыно').buffer)).toBe('Царицыно');
    const cp = new Uint8Array([0xD6, 0xE0, 0xF0, 0xE8, 0xF6, 0xFB, 0xED, 0xEE]);     // «Царицыно» в cp1251
    expect(decodeFile(cp.buffer)).toBe('Царицыно');
  });
});

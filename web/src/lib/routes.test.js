import { describe, expect, it } from 'vitest';
import { parse, setupClosed } from './routes.js';

describe('разбор адреса', () => {
  it('главная', () => { expect(parse('/')).toEqual({ page: 'home' }); });
  it('экраны сессии', () => {
    expect(parse('/s/fb3bc144/setup')).toEqual({ page: 'setup', sid: 'fb3bc144', sub: null });
    expect(parse('/s/fb3bc144/setup/variants')).toEqual({ page: 'variants', sid: 'fb3bc144', sub: null });
    expect(parse('/s/fb3bc144/plan/map')).toEqual({ page: 'plan', sid: 'fb3bc144', sub: 'map' });
    expect(parse('/s/fb3bc144/analytics/')).toEqual({ page: 'analytics', sid: 'fb3bc144', sub: null });
    expect(parse('/s/fb3bc144')).toEqual({ page: 'plan', sid: 'fb3bc144', sub: null });
  });
  it('прочее', () => {
    expect(parse('/s/fb3bc144/engineers/map')).toEqual({ page: 'notfound' });
    expect(parse('/s/XYZ/plan')).toEqual({ page: 'notfound' });
    expect(parse('/admin')).toEqual({ page: 'notfound' });
  });
});

describe('настройка после утверждения', () => {
  const planned = { session_id: 'ab12', plan_id: 'p1' }, fresh = { session_id: 'ab12', plan_id: null };
  it('закрыта, когда у сессии есть расписание', () => {
    expect(setupClosed(parse('/s/ab12/setup'), planned)).toBe(true);
    expect(setupClosed(parse('/s/ab12/setup/variants'), planned)).toBe(true);
  });
  it('открыта до расписания, на других экранах и пока грузится чужая сессия', () => {
    expect(setupClosed(parse('/s/ab12/setup'), fresh)).toBe(false);
    expect(setupClosed(parse('/s/ab12/plan'), planned)).toBe(false);
    expect(setupClosed(parse('/s/cd34/setup'), planned)).toBe(false);
  });
});

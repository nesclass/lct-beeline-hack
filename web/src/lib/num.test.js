import { describe, expect, it } from 'vitest';
import { num, pct, plural, signed } from './num.js';

describe('числа по-русски', () => {
  it('запятая и без хвостовых нулей', () => {
    expect(num(185.7)).toBe('185,7');
    expect(num(9)).toBe('9');
    expect(num(0.4)).toBe('0,4');
    expect(num(0.45, 2)).toBe('0,45');
    expect(num(2.04)).toBe('2');
    expect(num(null)).toBe('—');
  });
  it('знак и проценты', () => {
    expect(signed(3)).toBe('+3');
    expect(signed(-2.5)).toBe('-2,5');
    expect(signed(0)).toBe('0');
    expect(pct(0.564)).toBe('56 %');
  });
  it('склонение', () => {
    const f = ['заявка', 'заявки', 'заявок'];
    expect([1, 2, 5, 11, 21, 22, 25, 111].map(n => plural(n, f)))
      .toEqual(['1 заявка', '2 заявки', '5 заявок', '11 заявок', '21 заявка', '22 заявки', '25 заявок', '111 заявок']);
  });
});

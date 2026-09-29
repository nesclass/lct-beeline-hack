import { describe, expect, it } from 'vitest';
import { ENGINEER_COLORS, colorsFor } from './palette.js';

describe('цвета инженеров', () => {
  it('по порядку и по кругу', () => {
    const ids = Array.from({ length: 13 }, (_, i) => `E${String(i + 1).padStart(2, '0')}`);
    const c = colorsFor(ids);
    expect(c.E01).toEqual({ main: '#E4572E', tint: '#FCE3DB' });
    expect(c.E05).toEqual({ main: '#C2185B', tint: '#F9DCE8' });
    expect(c.E13).toEqual(c.E01);
    expect(ENGINEER_COLORS).toHaveLength(12);
  });
});

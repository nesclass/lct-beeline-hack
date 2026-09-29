import { describe, expect, it } from 'vitest';
import { clamp, fmt, hm, maskTime, parseTime, shortDate } from './time.js';

describe('время', () => {
  it('минуты ⇄ ЧЧ:ММ', () => {
    expect(fmt(545)).toBe('09:05');
    expect(hm('18:00')).toBe(1080);
    for (const m of [0, 599, 1439]) expect(hm(fmt(m))).toBe(m);
  });
  it('ограничение', () => {
    expect(clamp(5, 10, 20)).toBe(10);
    expect(clamp(25, 10, 20)).toBe(20);
    expect(clamp(15, 10, 20)).toBe(15);
  });
  it('короткая дата', () => {
    expect(shortDate('2026-08-17')).toBe('17.08');
    expect(shortDate(null)).toBe('');
    expect(shortDate(undefined)).toBe('');
  });
});

describe('время, набранное руками', () => {
  it('понимает привычные записи', () => {
    expect(['13:30', '13.30', '1330', '930', '9', ' 9:5 ', '0:00'].map(parseTime))
      .toEqual(['13:30', '13:30', '13:30', '09:30', '09:00', '09:05', '00:00']);
  });
  it('непонятное и невозможное — null', () => {
    expect(['', 'abc', '25:00', '12:60', '12345', null].map(parseTime)).toEqual([null, null, null, null, null, null]);
  });
});

describe('маска ЧЧ:ММ', () => {
  it('двоеточие само, лишнее отбрасывается', () => {
    expect(['1', '13', '133', '1330', '13:30', '13305', 'a1b3', ''].map(x => maskTime(x).text))
      .toEqual(['1', '13:', '13:3', '13:30', '13:30', '13:30', '13:', '']);
  });
  it('час с 3–9 — с нулём впереди; полнота — четыре цифры', () => {
    expect(maskTime('9').text).toBe('09:');
    expect(maskTime('930')).toEqual({ text: '09:30', complete: true });
    expect(maskTime('13:3').complete).toBe(false);
  });
});

/** Доступность инженера (4j) — варианты, быстрые времена, тело запроса, итог последствий. */
import { plural } from './num.js';
import { clamp, fmt, hm } from './time.js';

export const OPTIONS = shift => [
  { key: 'schedule', t: 'По графику', d: shift }, { key: 'leave', t: 'Уйдёт раньше', d: '' },
  { key: 'break', t: 'Перерыв', d: 'вернётся в указанное время' }, { key: 'absent', t: 'Не выйдет', d: 'весь день' }];

export function initialState(e, ev, clock, current) {
  const base = { mode: 'leave', time: clock, until: fmt(clamp(hm(clock) + 60, 0, 23 * 60 + 59)), finish_current: true, reason: '' };
  if (!ev) return base;
  if (ev.type === 'engineer_break') return { ...base, mode: 'break', time: ev.time, until: ev.until, reason: ev.reason || '' };
  const mode = ev.mode === 'absent' ? 'absent' : 'leave';
  const time = mode === 'leave' && hm(ev.time) < hm(clock) ? clock : ev.time;
  return { ...base, mode, time, finish_current: ev.finish_current ?? true, reason: ev.reason || '' };
}

export const quickTimes = (clock, current) =>
  [{ t: `сейчас ${clock}`, v: clock }, ...(current ? [{ t: `после текущей · ${current.finish}`, v: current.finish }] : [])];

export function toBody(s) {
  const reason = (s.reason || '').trim();
  if (s.mode === 'schedule') return null;
  if (s.mode === 'absent') return { mode: 'absent', reason };
  if (s.mode === 'break') return { mode: 'break', time: s.time, until: s.until, reason };
  return { mode: 'leave', time: s.time, finish_current: s.finish_current, reason };
}

export function summary(pre) {
  const n = pre.released.length;
  if (!n) return { title: 'Заявки не освобождаются', can: '' };
  return { title: `Освободятся ${plural(n, ['заявка', 'заявки', 'заявок'])}`, can: `подобрать можно ${pre.can_take}` };
}

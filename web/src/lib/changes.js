/** 4k «Изменения» — строки очереди, прогноз «если оставить как есть», кто когда уходит. */
import { num } from './num.js';
import { hm } from './time.js';

const IC = {
  urgent_request: ['⚡', 'var(--red-tint)', 'var(--red)'], new_request: ['+', 'var(--blue-tint)', 'var(--blue)'],
  engineer_unavailable: ['⏏', '#FCE3DB', '#E4572E'], engineer_break: ['☕', 'var(--amber-tint)', 'var(--amber)'],
  cancel_request: ['✕', 'var(--chip)', 'var(--ink-3)'], move_request: ['↪', 'var(--violet-tint)', 'var(--violet-ink)'] };

export function eventRows(pending, names, requests, engineers) {
  const req = id => requests.find(r => r.id === id) || {};
  return pending.map(ev => {
    const [ic, icBg, icColor] = IC[ev.type] || ['•', 'var(--chip)', 'var(--ink)'];
    const at = ev.at || ev.time, who = names[ev.engineer_id];
    let title = ev.type, desc = '', edit = { kind: 'event', tab: 'urgent', ev };
    if (ev.type === 'urgent_request' || ev.type === 'new_request') {
      const r = ev.request || req(ev.request_id), id = r.id || ev.request_id;
      title = `${ev.type === 'urgent_request' ? 'Срочная' : 'Новая'} ${id} · ${at}`;
      desc = `${r.type}, ${r.address}, окно ${r.tw_start}–${r.tw_end}`;
    } else if (ev.type === 'engineer_unavailable') {
      title = ev.mode === 'absent' ? `${who} не выйдет сегодня · ${at}` : `${who} уходит в ${ev.time} · ${at}`;
      desc = ev.reason || (ev.mode === 'absent' ? 'весь день' : ev.finish_current ? 'доделает текущую заявку' : 'текущую вернёт в пул');
      edit = { kind: 'availability', eid: ev.engineer_id, ev };
    } else if (ev.type === 'engineer_break') {
      title = `${who}: перерыв ${ev.time}–${ev.until} · ${at}`;
      desc = ev.reason || 'вернётся в указанное время';
      edit = { kind: 'availability', eid: ev.engineer_id, ev };
    } else if (ev.type === 'cancel_request') {
      title = `Отмена ${ev.request_id} · ${at}`;
      desc = ev.reason || req(ev.request_id).address || '';
      edit = { kind: 'event', tab: 'cancel', ev };
    } else if (ev.type === 'move_request') {
      title = `${ev.request_id} → ${who} · ${at}`;
      desc = ev.from ? `было у ${names[ev.from]}` : 'была без исполнителя';
      edit = { kind: 'request', rid: ev.request_id };
    }
    return { id: ev.id, ic, icBg, icColor, title, desc, edit };
  });
}

export const forecast = imp => [
  { t: 'Заявок без исполнителя', n: String(imp.orphaned.length), c: imp.orphaned.length ? 'var(--red-ink)' : 'var(--ink)' },
  { t: 'Срочная не назначена', n: String(imp.urgent_unassigned), c: imp.urgent_unassigned ? 'var(--red-ink)' : 'var(--ink)' },
  { t: 'Ожидаемых опозданий', n: num(imp.expected_late), c: 'var(--ink)' }];

export function leavingOf(pending, engineers) {
  const out = {};
  for (const ev of pending) if (ev.type === 'engineer_unavailable') {
    const t = ev.mode === 'absent' ? hm(engineers.find(e => e.id === ev.engineer_id).shift_start) : hm(ev.time);
    out[ev.engineer_id] = Math.min(out[ev.engineer_id] ?? Infinity, t);
  }
  return out;
}

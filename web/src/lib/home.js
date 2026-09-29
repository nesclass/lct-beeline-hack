/** Данные для 4a — сценарии дня, недавние сессии, загрузка своего файла. */
import { sessionPill, whenText } from './labels.js';
import { plural } from './num.js';

export const CARD_BG = ['var(--yellow-card)', 'var(--peach)', 'var(--blue-card)'];

export const scenarioCards = list => list.map((s, i) => ({
  id: s.id, title: s.title, desc: s.description, eng: s.engineers, req: s.requests, uploaded: s.uploaded,
  area: s.area || '—', districts: plural(s.districts, ['район', 'района', 'районов']),
  bg: CARD_BG[i % CARD_BG.length], primary: i === 0,
}));

export const sessionRows = (list, now = Date.now() / 1000) => list.map(s => ({
  sid: s.session_id, short: 's-' + s.session_id.slice(0, 4), scen: s.title, clock: s.clock,
  pill: sessionPill(s.status, s.pending), upd: whenText(s.updated_at, now),
  href: `/s/${s.session_id}/${s.status === 'new' ? 'setup' : 'plan'}`,
}));

export function decodeFile(buffer) {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
  catch { return new TextDecoder('windows-1251').decode(buffer); }
}

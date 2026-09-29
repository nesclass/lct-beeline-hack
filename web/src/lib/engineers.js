/** Инженеры — строки таблицы 4i и данные карточки инженера. */
import { IDLE } from './palette.js';
import { SKILL_CHIP, SKILL_SHORT, TRANSPORT_SHORT } from './labels.js';
import { num, plural } from './num.js';
import { hm } from './time.js';

const OWN = ['engineer_unavailable', 'engineer_break'];
export const queuedFor = (eid, pending) => [...pending].reverse().find(e => OWN.includes(e.type) && e.engineer_id === eid) || null;

function state(e, rt, clockMin, pending) {
  const q = queuedFor(e.id, pending);
  if (q?.type === 'engineer_break') return [`перерыв ${q.time}–${q.until}`, 'var(--amber-ink)'];
  if (q) return [q.mode === 'absent' ? 'не выйдет сегодня' : `уйдёт в ${q.time}`, 'var(--amber-ink)'];
  if (e.unavailable_from) return [`недоступен с ${e.unavailable_from}`, 'var(--red-ink)'];
  if (!rt || !rt.stops.length) return ['в резерве', 'var(--muted)'];
  if (hm(e.shift_start) > clockMin) return [`с ${e.shift_start}`, 'var(--green-ink)'];
  return ['на смене', 'var(--green-ink)'];
}

const routeOf = (view, eid) => view?.plan.routes.find(r => r.engineer_id === eid);

export function engineerRows(engineers, view, colors, clockMin, pending) {
  return engineers.map(e => {
    const rt = routeOf(view, e.id), busy = rt && rt.stops.length, [st, stColor] = state(e, rt, clockMin, pending);
    return { eid: e.id, name: e.name, ini: e.name.slice(0, 2).toUpperCase(),
             c: busy ? colors[e.id].main : IDLE, tint: busy ? colors[e.id].tint : 'var(--line-3)',
             tr: TRANSPORT_SHORT[e.transport], shift: `${e.shift_start}–${e.shift_end}`,
             skills: e.skills.map(k => ({ t: SKILL_SHORT[k], bg: SKILL_CHIP[k][0], c: SKILL_CHIP[k][1] })),
             n: busy ? rt.stops.length : '—', km: busy ? num(rt.total_km) : '—', load: busy ? Math.round(rt.utilization * 100) : 0, st, stColor };
  });
}

export function engineerCard(eid, engineers, view, colors, clockMin, pending) {
  const e = engineers.find(x => x.id === eid), row = engineerRows([e], view, colors, clockMin, pending)[0];
  const stops = routeOf(view, eid)?.stops || [];
  const cur = stops.find(s => hm(s.start) <= clockMin && hm(s.finish) > clockMin)
    || [...stops].reverse().find(s => hm(s.start) <= clockMin) || null;
  const after = stops.filter(s => hm(s.start) > clockMin);
  const from = cur ? stops.indexOf(cur) : stops.findIndex(s => hm(s.start) > clockMin);
  const type = rid => view.requests[rid].type;
  const [st0] = state(e, routeOf(view, eid), clockMin, []);         // строка карточки — по расписанию, без очереди
  const on = st0[0].toUpperCase() + st0.slice(1);
  return { name: e.name, ini: row.ini, c: row.c, tint: row.tint, line: `${on} · ${row.shift} · ${row.tr}`,
           chips: [...row.skills, { t: row.tr, bg: 'var(--chip)', c: 'var(--ink)' }],
           now: cur ? `${cur.request_id} · ${type(cur.request_id)} · до ${cur.finish}` : '—',
           next: after.length ? `${plural(after.length, ['заявка', 'заявки', 'заявок'])} до конца смены` : 'больше заявок нет',
           km: stops.length ? `${num(routeOf(view, eid).total_km)} км за день` : '—',
           list: (from < 0 ? [] : stops.slice(from, from + 6)).map(s => ({ t: s.start, id: s.request_id, type: type(s.request_id), cur: s === cur })) };
}

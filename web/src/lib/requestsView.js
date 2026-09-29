import { shortReason } from './plan.js';

export const FILTERS = [['all', 'Все'], ['assigned', 'Назначены'], ['unassigned', 'Не назначены'],
                        ['waiting', 'Ждут перепланирования'], ['urgent', 'Срочные'], ['cancelled', 'Отменены']];
const CODE = { SKILL: 'навык', TRANSPORT: 'транспорт', WINDOW_REACH: 'окно', SHIFT_FIT: 'смена', PINNED: 'закреплена' };

export function stateOf(r, view) {
  if (r.status === 'cancelled') return { key: 'cancelled', text: 'Отменена', tone: 'gray' };
  if (r.status === 'new' || r.pending.length) return { key: 'waiting', text: 'Ждёт перепланирования', tone: 'warn' };
  if (r.status === 'assigned') return { key: 'assigned', text: 'Назначена', tone: 'ok' };
  const code = view?.plan.assignments[r.id]?.reason?.code;
  return { key: 'unassigned', text: code === 'SHIFT_FIT' ? 'Не влезает в смену' : 'Не назначена', tone: 'bad' };
}

export function counts(list, view) {
  const c = { all: list.length, assigned: 0, unassigned: 0, waiting: 0, urgent: 0, cancelled: 0 };
  for (const r of list) { c[stateOf(r, view).key] += 1; if (r.priority === 'urgent') c.urgent += 1; }
  return c;
}

export function filterRows(list, view, key, query) {
  const q = query.trim().toLowerCase();
  return list.filter(r => (key === 'all' || (key === 'urgent' ? r.priority === 'urgent' : stateOf(r, view).key === key))
    && (!q || `${r.id} ${r.address} ${r.district}`.toLowerCase().includes(q)));
}

// В таблице район стоит отдельной строкой под адресом — повторять его в начале адреса незачем.
export function streetOf(r) {
  const pre = `${r.district}, `;
  return r.district && r.address.startsWith(pre) ? r.address.slice(pre.length) : r.address;
}

export function executor(r, view, names) {
  for (const rt of view?.plan.routes || []) for (const s of rt.stops)
    if (s.request_id === r.id) return `${names[rt.engineer_id]} · ${s.start}`;
  return '—';
}

export function reasonCard(r, view, names) {
  const a = view?.plan.assignments[r.id];
  if (!a || a.engineer_id || r.status !== 'unassigned') return null;
  const rs = a.reason;
  const chips = Object.entries(rs.compat || {}).filter(([, c]) => c).map(([k, c]) => `${names[k]} — ${CODE[c] || c}`)
    .concat((rs.probes || []).map(p => `${names[p.engineer_id]} — занят`));
  const first = a.text.split('. ')[0];
  return { title: shortReason(view.requests[r.id], rs, view.dict), text: first.endsWith('.') ? first : first + '.', chips };
}


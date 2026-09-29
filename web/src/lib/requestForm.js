/** Форма заявки 4h. Координат в форме нет: точка — центр района из начала адреса со сдвигом
 *  от хэша адреса (так устроены и синтетические точки сценариев). Навык — из вида работ. */
import { SKILL_SHORT } from './labels.js';
import { fmt, hm } from './time.js';

const LAST = 23 * 60 + 59;
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const norm = s => s.trim().toLowerCase().replaceAll('ё', 'е');

export function emptyForm(clockMin, catalog, urgent = true) {
  const start = Math.min(Math.ceil(clockMin / 30) * 30, LAST - 60);
  const t = catalog.types.find(x => (urgent ? x.skill === 'emergency' : x.skill !== 'emergency')) || catalog.types[0];
  return { address: '', type: t.type, transport: '', tw_start: fmt(start), tw_end: fmt(Math.min(start + 120, LAST)), urgent };
}

export function districtOf(address, districts) {
  const head = norm(address.split(',')[0] || '');
  return districts.find(d => norm(d.name) === head) || null;
}

function hash(s) {                                  // FNV-1a, 32 бита
  let h = 0x811c9dc5;
  for (const ch of s) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
  return h;
}

export function coordsFor(address, d) {
  const h = hash(address.trim());
  const dx = ((h & 0xffff) / 0xffff - 0.5) * 0.008, dy = ((h >>> 16) / 0xffff - 0.5) * 0.008;
  return [+(d.lat + dx).toFixed(5), +(d.lon + dy).toFixed(5)];
}

const typeOf = (f, catalog) => catalog.types.find(x => x.type === f.type) || catalog.types[0];

export function workInfo(f, catalog) {
  const t = typeOf(f, catalog), n = catalog.norms[t.work_type];
  return { skill: SKILL_SHORT[t.skill], minutes: n.tech_min + n.docs_min };
}

export function validate(f, catalog) {
  if (!f.address.trim()) return ['укажите адрес'];
  const out = [];
  if (!districtOf(f.address, catalog.districts))
    out.push(`начните адрес с района: ${catalog.districts.map(d => d.name).join(', ')}`);
  if (!HHMM.test(f.tw_start) || !HHMM.test(f.tw_end)) out.push('окно в формате ЧЧ:ММ');
  else if (hm(f.tw_end) <= hm(f.tw_start)) out.push('конец окна должен быть позже начала');
  return out;
}

export function toBody(f, catalog) {
  const d = districtOf(f.address, catalog.districts), t = typeOf(f, catalog), [lat, lon] = coordsFor(f.address, d);
  return { lat, lon, address: f.address.trim(), district: d.name, type: t.type, skill: t.skill, work_type: t.work_type,
           tw_start: f.tw_start, tw_end: f.tw_end, priority: f.urgent ? 'urgent' : 'normal', required_transport: f.transport || null };
}

export const formFromRequest = r => ({ address: r.address, type: r.type, transport: r.required_transport || '',
                                       tw_start: r.tw_start, tw_end: r.tw_end, urgent: r.priority === 'urgent' });

/** Можно ли отменить: нет по уже отменённой или отменяемой заявке; по остальным —
 *  как в клиентском процессе (см. L4 ядра) можно и после выезда, и в работе, нельзя
 *  только после завершения. Заявка не в плане не считается завершённой. */
export function canCancel(r, view, clockMin) {
  if (r.status === 'cancelled' || r.pending.includes('cancel_request')) return false;
  for (const rt of view?.plan.routes || []) for (const s of rt.stops)
    if (s.request_id === r.id) return hm(s.finish) > clockMin;
  return true;
}

export function cancellable(requests, view, clockMin) {
  const at = {};
  for (const rt of view?.plan.routes || []) for (const s of rt.stops) at[s.request_id] = { name: rt.name, start: s.start };
  return requests
    .filter(r => canCancel(r, view, clockMin))
    .map(r => ({ id: r.id, label: `${r.id} · ${r.type}`,
                 sub: at[r.id] ? `${at[r.id].name} в ${at[r.id].start} · ${r.address}` : `без исполнителя · ${r.address}` }));
}

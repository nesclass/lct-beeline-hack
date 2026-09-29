/** Время — минуты от полуночи; на экране и в API — ЧЧ:ММ. */
export const fmt = m => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
export const hm = s => { const [h, m] = s.split(':').map(Number); return h * 60 + m; };
export const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
export function shortDate(iso) {
  if (!iso) return '';
  const [, m, d] = iso.split('-');
  return `${d}.${m}`;
}

/** Время, набранное руками: «13:30», «13.30», «1330», «930», «9» → «ЧЧ:ММ»; непонятное — null. */
export function parseTime(s) {
  const t = String(s ?? '').trim().replace(/[.,\-\s]/g, ':');
  const m = t.match(/^(\d{1,2}):(\d{1,2})$/) || t.match(/^(\d{1,2})(\d{2})$/) || t.match(/^(\d{1,2})$/);
  if (!m) return null;
  const h = +m[1], mi = m[2] === undefined ? 0 : +m[2];
  return h < 24 && mi < 60 ? fmt(h * 60 + mi) : null;
}

/** Маска «ЧЧ:ММ» при наборе: только цифры, двоеточие ставится само, час с 3–9 — с нулём впереди.
 *  complete — набраны все четыре цифры (можно применять, не дожидаясь Enter). */
export function maskTime(raw) {
  let d = String(raw ?? '').replace(/\D/g, '');
  if (d.length && +d[0] > 2) d = '0' + d;
  d = d.slice(0, 4);
  const text = d.length > 2 ? `${d.slice(0, 2)}:${d.slice(2)}` : d.length === 2 ? `${d}:` : d;
  return { text, complete: d.length === 4 };
}

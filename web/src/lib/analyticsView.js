/** Данные 4m «Аналитика»: наш план против базового, по часам, по навыкам, загрузка, запас, приезд в окно, история, выгрузка CSV. */
import { SKILL_SHORT } from './labels.js';
import { num, pct, plural } from './num.js';

const minus = x => (x < 0 ? `−${-x}` : x > 0 ? `+${x}` : '0');

export function tiles(a) {
  const c = a.current, b = a.baseline;
  const save = b.total_km ? Math.round((c.total_km / b.total_km - 1) * 100) : 0;
  return [
    { label: 'Назначено', val: `${c.assigned} / ${c.total}`, sub: `базовый: ${b.assigned}`, bg: 'var(--green-tint)', c: 'var(--green-ink)' },
    { label: 'Инженеров', val: String(c.engineers_used), sub: `базовый: ${b.engineers_used} · ${minus(c.engineers_used - b.engineers_used)}`,
      bg: 'var(--yellow-card)', c: 'var(--amber-ink)' },
    { label: 'Пробег', val: `${num(c.total_km, 0)} км`, sub: `базовый: ${num(b.total_km, 0)} · ${minus(save)} %`, bg: 'var(--blue-card)', c: 'var(--blue)' },
    { label: 'Ожид. опозданий', val: num(c.expected_late), sub: `базовый: ${num(b.expected_late)}`, bg: 'var(--peach)', c: 'var(--red-ink)' }];
}

export function kmRows(a, engineers, colors) {
  const cur = a.current.km_per_engineer, base = a.baseline.km_per_engineer;
  const list = engineers.filter(e => (cur[e.id] || 0) > 0 || (base[e.id] || 0) > 0);
  const max = Math.max(...list.map(e => Math.max(cur[e.id] || 0, base[e.id] || 0)), 1);
  return list.map(e => ({ name: e.name, c: colors[e.id].main, km: cur[e.id] ? num(cur[e.id]) : '—',
                          w: (cur[e.id] || 0) / max * 100, b: (base[e.id] || 0) / max * 100 }));
}

export function hourly(a, height = 140) {
  const max = Math.max(...a.hours.map(h => Math.max(h.on_shift, h.in_work)), 1) * 1.15;
  return a.hours.map(h => ({ t: String(h.h), n: h.in_work, h: Math.round(h.in_work / max * height), capH: Math.round(h.on_shift / max * height),
                             c: h.in_work >= h.on_shift ? 'var(--amber)' : 'var(--blue)' }));
}

const SKILL_BAR = { local: 'var(--sk-local)', connect: 'var(--sk-connect)', emergency: 'var(--sk-em)' };
export function skillRows(a) {
  const max = Math.max(...a.skills.map(s => s.total), 1);
  return a.skills.map(s => ({ name: SKILL_SHORT[s.skill], a: s.assigned, tot: s.total, w: s.assigned / max * 100,
                              u: (s.total - s.assigned) / max * 100, c: SKILL_BAR[s.skill] }));
}

export function eventShort(ev, names) {
  const who = names[ev.engineer_id];
  switch (ev.type) {
    case 'urgent_request': return `Срочная ${ev.request.id}`;
    case 'new_request': return `Новая ${ev.request_id}`;
    case 'cancel_request': return `Отмена ${ev.request_id}`;
    case 'move_request': return `${ev.request_id} → ${who}`;
    case 'engineer_break': return `Перерыв: ${who}`;
    case 'engineer_unavailable': return ev.mode === 'absent' ? `${who} не вышел` : `${who} ушёл`;
    default: return ev.type;
  }
}

export const historyRows = (history, names, dayStart) => history.map(h => ({
  t: h.at || dayStart,
  why: h.kind === 'replan' ? h.events.map(e => eventShort(e, names)).join(', ') : h.label ? `Утверждён «${h.label}»` : 'Базовое расписание',
  a: `${h.assigned} / ${h.total}`, km: `${num(h.total_km, 0)} км`,
  ch: h.changes == null ? '—' : plural(h.changes, ['изменение', 'изменения', 'изменений']) }));

// CSV-экранирование: значение с ; " или переносом строки — в кавычки, внутренние " — вдвое.
const csvField = x => { const s = String(x); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const csvRow = (...cells) => cells.map(csvField).join(';');

export function toCsv(a, engineers) {
  const cur = a.current.km_per_engineer, base = a.baseline.km_per_engineer;
  const lines = [csvRow('инженер', 'пробег, км', 'базовый, км'),
    ...engineers.filter(e => cur[e.id] || base[e.id]).map(e => csvRow(e.name, num(cur[e.id] || 0), num(base[e.id] || 0))),
    csvRow('итого', num(a.current.total_km), num(a.baseline.total_km))];
  return '﻿' + lines.join('\n') + '\n';
}

// Загрузка смены: работа / дорога / ожидание / перерыв / свободно — у каждого работающего инженера.
export const LOAD_PARTS = [
  { k: 'work', label: 'работа', c: 'var(--blue)' },
  { k: 'travel', label: 'дорога', c: 'var(--amber)' },
  { k: 'wait', label: 'ожидание у клиента', c: 'var(--violet)' },
  { k: 'break', label: 'перерыв', c: 'var(--line)' },
  { k: 'free', label: 'свободно', c: 'var(--line-2)' }];
const hours = m => `${num(m / 60)} ч`;

function loadSegs(x) {
  const free = Math.max(0, x.shift - x.work - x.travel - x.wait - (x.break || 0));
  const full = { ...x, break: x.break || 0, free };
  const tot = Math.max(x.shift, x.work + x.travel + x.wait + full.break, 1);
  return LOAD_PARTS.filter(p => full[p.k] > 0).map(p => ({ ...p, min: full[p.k], w: full[p.k] / tot * 100 }));
}
const loadAria = (who, x) => `${who}: работа ${hours(x.work)}, дорога ${hours(x.travel)}, ожидание ${hours(x.wait)}`
  + (x.break ? `, перерыв ${hours(x.break)}` : '') + ` из смены ${hours(x.shift)}`;

/** Строки по инженерам (только наш план): сегменты в % смены, «занят» = работа + дорога. */
export function loadRows(a, engineers) {
  const load = a.current.load || {};
  return engineers.filter(e => load[e.id]).map(e => {
    const x = load[e.id];
    return { name: e.name, segs: loadSegs(x), busy: x.shift ? pct((x.work + x.travel) / x.shift) : '—', aria: loadAria(e.name, x) };
  });
}

/** Итог по команде: наш и базовый — по сумме смен работающих инженеров. Базового без полей — нет. */
export function loadTotals(a) {
  const sum = load => Object.values(load).reduce((s, x) => {
    for (const k of ['work', 'travel', 'wait', 'break', 'shift']) s[k] += x[k] || 0;
    return s; }, { work: 0, travel: 0, wait: 0, break: 0, shift: 0 });
  return [['наш план', a.current.load], ['базовый', a.baseline.load]].filter(([, l]) => l)
    .map(([label, l]) => { const x = sum(l); return { label, segs: loadSegs(x), aria: loadAria(label, x) }; });
}

/** Легенда — только те части, что есть на графике (перерыва может не быть вовсе). */
export const loadLegend = totals => LOAD_PARTS.filter(p => totals.some(t => t.segs.some(g => g.k === p.k)));

/** Одна строка сравнения: «в дороге всего: наш 11,5 ч · базовый 12,4 ч». */
export function loadSummary(a) {
  const c = a.current, b = a.baseline;
  if (c.travel_min == null) return [];
  const line = (label, k) => ({ label, cur: hours(c[k]), base: b[k] == null ? '—' : hours(b[k]) });
  return [line('в дороге всего', 'travel_min'), line('ожидание у клиента', 'wait_min')];
}

// Разбиение по корзинам: наш и базовый — доли от своего числа заявок (базовый назначает меньше), и количество.
function compare(buckets, cur, base, height) {
  const count = (list, i) => (list ? list.filter(x => x === i).length : null);
  const rows = buckets.map((b, i) => ({ ...b, n: count(cur, i), bn: count(base, i) }));
  const ct = cur ? cur.length : 0, bt = base ? base.length : 0;
  const share = (n, t) => (n == null || !t ? 0 : n / t);
  const max = Math.max(...rows.map(r => Math.max(share(r.n, ct), share(r.bn, bt))), 0.01);
  return rows.map(r => ({ ...r, w: share(r.n, ct) / max * height, bw: share(r.bn, bt) / max * height,
                          p: ct ? pct(share(r.n, ct)) : '—', bp: base && bt ? pct(share(r.bn, bt)) : '—' }));
}

export const SLACK_BUCKETS = [
  { label: 'меньше 10 мин', c: 'var(--red)' }, { label: '10–20 мин', c: 'var(--amber)' },
  { label: '20–40 мин', c: 'var(--green)' }, { label: '40–60 мин', c: 'var(--green)' }, { label: '60 мин и больше', c: 'var(--green)' }];
/** Номер корзины запаса: границы 10, 20, 40, 60 — ровно на границе уже следующая корзина. */
export const slackBucket = m => (m < 10 ? 0 : m < 20 ? 1 : m < 40 ? 2 : m < 60 ? 3 : 4);
export function slackRows(a, width = 100) {
  const b = x => (x ? x.map(slackBucket) : null);
  return compare(SLACK_BUCKETS, b(a.current.tol), b(a.baseline.tol), width);
}

export const WINDOW_BUCKETS = [
  { label: 'раньше окна, ждёт', c: 'var(--violet)' }, { label: 'в начале окна', c: 'var(--green)' },
  { label: 'в середине окна', c: 'var(--green)' }, { label: 'в конце окна', c: 'var(--amber)' },
  { label: 'после окна', c: 'var(--red)' }];
/** Где в окне приезд: до открытия / первая, вторая, последняя треть / после закрытия. */
export function windowBucket({ off, len }) {
  if (off < 0) return 0;
  const r = len > 0 ? off / len : 1;
  return r < 1 / 3 ? 1 : r < 2 / 3 ? 2 : r <= 1 ? 3 : 4;
}
/** «После окна» показываем, только если такие приезды есть хоть в одном плане. */
export function windowRows(a, width = 100) {
  const b = x => (x ? x.map(windowBucket) : null);
  const rows = compare(WINDOW_BUCKETS, b(a.current.windows), b(a.baseline.windows), width);
  return rows.filter((r, i) => i < 4 || r.n || r.bn);
}

/** Как менялся план за день: столбик на каждый шаг истории, высота — от максимума своей строки. */
export function trendRows(history, dayStart, height = 28) {
  const metrics = [
    { label: 'Назначено', v: h => h.assigned, f: h => `${h.assigned}/${h.total}` },
    { label: 'Пробег, км', v: h => h.total_km, f: h => num(h.total_km, 0) },
    { label: 'Инженеров', v: h => h.engineers_used, f: h => (h.engineers_used == null ? '—' : String(h.engineers_used)) }];
  const steps = history.map(h => h.at || dayStart);
  return { steps, rows: metrics.map(m => {
    const max = Math.max(...history.map(h => m.v(h) || 0), 1);
    return { label: m.label, cells: history.map(h => ({ v: m.f(h), h: Math.round((m.v(h) || 0) / max * height) })) };
  }) };
}

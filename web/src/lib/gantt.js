/** Геометрия диаграммы Ганта по макету Gantt.dc.html: строка 36px, заявка 20px в цвете инженера,
 *  обводка по запасу, дорога — тонкая линия перед заявкой. Три режима: план, очередь, разбор. */
import { IDLE } from './palette.js';
import { TRANSPORT_SHORT } from './labels.js';
import { fmt, hm } from './time.js';
import { num } from './num.js';
import { INS } from './diffView.js';
import { shortReason } from './plan.js';

export const NW = 180, RH = 36;
const RED = 'var(--red)', AMB = 'var(--amber)', INK = 'var(--ink)';

/** Масштаб шкалы: 0 — весь день по ширине экрана; дальше — минут на пиксель больше, диаграмма
 *  прокручивается вбок. Подпись заявки видна от 44px — на «крупно» и 15-минутная заявка подписана. */
export const ZOOMS = [null, 1.6, 2.4, 3.2];
export const trackWidth = (fit, span, level) =>
  Math.round(Math.max(780, fit, ZOOMS[level] ? span * ZOOMS[level] : 0));

export function dayBounds(view) {
  const es = Object.values(view.engineers);
  let t1 = Math.max(...es.map(e => e.shift_end));
  for (const rt of view.plan.routes) for (const s of rt.stops) t1 = Math.max(t1, hm(s.finish));
  return [Math.floor(Math.min(...es.map(e => e.shift_start)) / 60) * 60, Math.ceil(t1 / 60) * 60];
}

export function tolOf(view, rid) {
  const t = view.risk?.tol?.[rid];
  if (t !== undefined) return t;
  for (const rt of view.plan.routes) for (const s of rt.stops) if (s.request_id === rid) return s.slack_min;
  return Infinity;
}
export const tone = t => (t < 10 ? 'crit' : t < 20 ? 'warn' : 'good');
export function tolText(t) {
  const k = tone(t);
  return k === 'crit' ? [`${t} мин · риск опоздания`, 'var(--red-ink)']
    : k === 'warn' ? [`${t} мин · мало`, 'var(--amber-text)'] : [`${t} мин`, 'var(--green-ink)'];
}

/** С какой минуты штриховать недоступность. Без заявок — всю смену. В базовом плане уход,
 *  объявленный на время позже начала смены, обрезает смену: до ухода инженер работает. */
export function offFrom(route, engineer, plan) {
  if (!route.unavailable_from) return null;
  if (route.stops.length === 0) return engineer.shift_start;
  const t = hm(route.unavailable_from);
  return plan.replan_of ? t : Math.max(t, engineer.shift_start);
}

const HATCH = 'repeating-linear-gradient(135deg,rgba(229,56,59,.14) 0 5px,transparent 5px 10px)';
const base = { top: 8, h: 20, r: 6, bd: 'none', sh: 'none', ol: 'none', op: 1, color: INK, label: '', pad: 5 };

function hatchBar(x, from, to) {
  return { ...base, kind: 'hatch', l: x(from), w: x(to) - x(from), top: 3, h: 30, bg: HATCH, pad: 0 };
}

function workBar(s, c, x, o) {
  const b = hm(s.start), f = hm(s.finish), w = x(f) - x(b);
  return { ...base, kind: 'work', rid: s.request_id, l: x(b), w, bg: c.tint, sh: `inset 3px 0 0 ${c.main}`,
           label: w >= 44 ? s.request_id : '', ...o };
}

function travelBar(s, c, x, op = 0.5) {
  const a = hm(s.arrive);
  return { ...base, kind: 'travel', l: x(a - s.leg_min), w: x(a) - x(a - s.leg_min), top: 17, h: 2, r: 1, bg: c.main, op, pad: 0 };
}

// Значок правки над левым краем отрезка: читается и на узкой заявке. Если значки строки налезают
// друг на друга — сперва сокращаем до символа левый (его текст закрыт следующим), затем, если мало, и этот.
const BADGE_CH = 6.2, BADGE_PAD = 8;
function badge(bar, full, short, bg, color, bd = 'none') {
  return { kind: 'badge', rid: bar.rid, l: bar.l, top: 0, full, short, text: full, bg, color, bd,
           w: full.length * BADGE_CH + BADGE_PAD };
}
const shorten = b => { b.text = b.short; b.w = b.short.length * BADGE_CH + BADGE_PAD; };
function unclutter(bars) {
  let prev = null;
  for (const b of bars.filter(x => x.kind === 'badge').sort((a, c) => a.l - c.l)) {
    if (prev && b.l < prev.l + prev.w + 3) {
      shorten(prev);
      if (b.l < prev.l + prev.w + 3) shorten(b);
    }
    prev = b;
  }
  return bars;
}

const stopsOf = routes => {
  const out = {};
  for (const rt of routes || []) rt.stops.forEach((s, i) => (out[s.request_id] = { s, i, eid: rt.engineer_id }));
  return out;
};
const nameOf = (view, eid) => view.engineers[eid]?.name || eid;
const signedMin = n => `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n)} мин`;
const later = n => `на ${Math.abs(n)} мин ${n > 0 ? 'позже' : 'раньше'}`;
const inMoved = (d, eid) => d && (d.status === 'newly_assigned' || (d.status === 'moved' && d.to === eid));

/** Что в этом пересчёте случилось с инженером: ушёл, не вышел, перерыв. null — ничего. */
export function engineerEvent(view, eid) {
  const plan = view.plan;
  const ev = [...(plan.events || [])].reverse()
    .find(e => e.engineer_id === eid && (e.type === 'engineer_unavailable' || e.type === 'engineer_break'));
  if (ev?.type === 'engineer_break') return { short: `перерыв ${ev.time}`, why: `перерыв ${ev.time}–${ev.until}` };
  if (ev?.mode === 'absent') return { short: 'не вышел', why: 'не вышел сегодня' };
  if (ev) return { short: `выбыл ${ev.time}`, why: `выбыл в ${ev.time}` };
  if (plan.diff?.engineers?.[eid]?.status === 'removed') {
    const t = plan.routes.find(rt => rt.engineer_id === eid)?.unavailable_from;
    return t ? { short: `выбыл ${t}`, why: `выбыл в ${t}` } : { short: 'выбыл', why: 'выбыл' };
  }
  return null;
}

// Заявки, которые в новом маршруте инженера пришли к нему (новые и переданные): все или только до rid.
function arrivals(view, eid, before = null) {
  const diff = view.plan.diff?.requests || {}, rt = view.plan.routes.find(r => r.engineer_id === eid);
  const stops = rt ? rt.stops : [], i = before ? stops.findIndex(s => s.request_id === before) : stops.length;
  return stops.slice(0, i).filter(s => inMoved(diff[s.request_id], eid)).map(s => s.request_id);
}
// Заявки, которые стояли у инженера раньше rid, а теперь ушли (переданы, сняты, отменены).
function departures(view, eid, rid) {
  const diff = view.plan.diff?.requests || {}, rt = view.previous?.routes.find(r => r.engineer_id === eid);
  const stops = rt ? rt.stops : [], i = stops.findIndex(s => s.request_id === rid);
  return stops.slice(0, i < 0 ? 0 : i).filter(s => {
    const d = diff[s.request_id];
    return d && (d.status === 'removed' || d.status === 'newly_unassigned' || (d.status === 'moved' && d.from === eid));
  }).map(s => s.request_id);
}
const list = (ids, one, many) => `${ids.length > 1 ? many : one} ${ids.slice(-2).join(', ')}`;

/** Одна строка «что изменилось» по разбору пересчёта — простыми словами. null — без изменений. */
export function changeNote(view, rid) {
  const plan = view.plan, d = plan.diff?.requests?.[rid];
  if (!d || d.status === 'unchanged') return null;
  switch (d.status) {
    case 'newly_assigned': {
      const ev = (plan.events || []).find(e => (e.type === 'urgent_request' || e.type === 'new_request') && e.request?.id === rid);
      if (ev) return ev.type === 'urgent_request' ? 'Новая срочная заявка' : 'Новая заявка';
      const was = view.previous?.assignments?.[rid];
      return was && !was.engineer_id ? 'Раньше не помещалась в план — теперь нашлось место' : 'Добавлена в план';
    }
    case 'moved': {
      const from = INS(nameOf(view, d.from));
      if ((plan.events || []).some(e => e.type === 'move_request' && e.request_id === rid)) return `Перенесена диспетчером от ${from}`;
      const ev = engineerEvent(view, d.from);
      if (ev) return `Передана от ${from} — ${ev.why}`;
      const took = arrivals(view, d.from);
      return took.length ? `Передана от ${from}: освободила место для ${took.slice(-2).join(', ')}` : `Передана от ${from}`;
    }
    case 'shifted': case 'reordered': {
      const by = d.shift_min ? `Сдвинута ${later(d.shift_min)}` : 'Другое место в маршруте';
      const ins = arrivals(view, d.engineer_id, rid);
      if (ins.length) return `${by}: перед ней ${list(ins, 'вставлена', 'вставлены')}`;
      const gone = departures(view, d.engineer_id, rid);
      if (gone.length) return `${by}: перед ней ${list(gone, 'убрана', 'убраны')}`;
      const ev = engineerEvent(view, d.engineer_id);
      if (ev) return `${by}: у инженера ${ev.why}`;
      return `${by}: ${d.status === 'reordered' ? 'изменился порядок заявок' : 'перестроен маршрут до неё'}`;
    }
    case 'newly_unassigned': {
      const r = view.requests[rid], a = plan.assignments?.[rid];
      return r && a?.reason ? `Снята с плана: ${shortReason(r, a.reason, view.dict)}` : 'Снята с плана';
    }
    case 'removed': return 'Заявка отменена';
    default: return null;
  }
}

/** Где заявка стояла в прошлом плане — «14:27–15:37 у Демина». null — не было или не изменилась. */
export function wasNote(view, rid) {
  const d = view.plan.diff?.requests?.[rid];
  if (!d || d.status === 'unchanged') return null;
  const p = stopsOf(view.previous?.routes)[rid];
  if (!p) return d.status === 'newly_assigned' && view.previous?.assignments?.[rid] ? 'не было в плане' : null;
  const at = `${p.s.start}–${p.s.finish}`;
  return d.status === 'shifted' || d.status === 'reordered' ? at : `${at} у ${INS(nameOf(view, p.eid))}`;
}

/** Почему заявка у этого инженера — только когда данным есть что сказать. */
export function whyNote(view, rid) {
  const a = view.plan.assignments?.[rid];
  if (!a?.engineer_id) return null;
  if (a.locked || a.reason?.locked) return 'Уже начата или выполнена — пересчёт её не меняет';
  if (a.manual || a.reason?.manual) return 'Закреплена диспетчером';
  const alts = a.reason?.alternatives;
  if (!alts) return null;
  const ok = alts.filter(x => x.feasible);
  if (!ok.length) return 'Другие подходящие инженеры заняты или не успевают в окно';
  const best = ok.reduce((m, x) => (x.delta_km < m.delta_km ? x : m)), extra = best.delta_km - (a.reason.delta_km ?? Infinity);
  return extra >= 0.5 ? `Ближе всех по дороге: у ${INS(nameOf(view, best.engineer_id))} было бы на ${num(extra)} км больше` : null;
}

// Призраки прошлого плана в режиме разбора: где была заявка, которой на этом месте больше нет.
function ghostsOf(view, diff) {
  const out = {};
  for (const rt of view.previous?.routes || []) for (const s of rt.stops) {
    const d = diff[s.request_id], k = rt.engineer_id;
    if (!d) continue;
    const g = kind => (out[k] ||= []).push({ s, kind, d });
    if (d.status === 'moved' && d.from === k) g('moved');
    else if ((d.status === 'shifted' || d.status === 'reordered') && d.engineer_id === k && d.shift_min) g('shift');
    else if (d.status === 'removed') g('removed');
    else if (d.status === 'newly_unassigned') g('dropped');
  }
  return out;
}

function ghostBar(g, c, x, view, eid) {
  const gb = workBar(g.s, c, x, {}), o = { ...gb, kind: 'ghost', eid, bg: 'transparent', sh: 'none', ol: 'none' };
  if (gb.w < 44) o.label = '';
  if (g.kind === 'shift') return [{ ...o, bd: `1.5px dashed ${c.main}`, op: 0.6, label: '' }];
  if (g.kind === 'moved') {
    const to = nameOf(view, g.d.to);
    return [{ ...o, bd: '1.5px dashed #9AA1AB', color: 'var(--muted)' },
            badge(o, `→ ${to}`, '→', 'var(--line-2)', 'var(--ink-3)')];
  }
  const red = { ...o, bg: 'rgba(229,56,59,.06)', bd: `1.5px dashed ${RED}`, color: 'var(--red-ink)' };
  return [red, badge(o, g.kind === 'removed' ? 'отменена' : 'снята', '×', 'var(--red-tint)', 'var(--red-ink)')];
}

export function rows(view, colors, x, opts = {}) {
  const { mode = 'plan', selected = null, riskOnly = false, only = null, orphaned = new Set(), leaving = {} } = opts;
  const plan = view.plan, diff = mode === 'diff' ? plan.diff?.requests || {} : {};
  const ghosts = mode === 'diff' ? ghostsOf(view, diff) : {};
  return plan.routes.filter(rt => !only || rt.engineer_id === only).map(rt => {
    const e = view.engineers[rt.engineer_id], c = colors[rt.engineer_id], idle = rt.stops.length === 0;
    const bars = [];
    const off = offFrom(rt, e, plan);
    if (mode === 'queue' && leaving[rt.engineer_id] != null) bars.push(hatchBar(x, leaving[rt.engineer_id], e.shift_end));
    else if (off != null) bars.push(hatchBar(x, off, e.shift_end));
    for (const br of rt.breaks || []) {
      const l = x(hm(br.start)), w = x(hm(br.end)) - l;
      bars.push({ ...base, kind: 'break', l, w, bg: 'var(--line-2)', color: 'var(--muted)', label: w >= 60 ? 'перерыв' : '' });
    }
    for (const g of ghosts[rt.engineer_id] || []) bars.push(...ghostBar(g, c, x, view, rt.engineer_id));
    for (const s of rt.stops) {
      const t = tolOf(view, s.request_id), k = tone(t);
      let o = { ol: k === 'crit' ? `2px solid ${RED}` : k === 'warn' ? `2px solid ${AMB}` : 'none' };
      let trOp = 0.5, road = s.leg_min > 0, mark = null;
      if (mode === 'plan') {
        if (selected === s.request_id) o.ol = `2px solid ${INK}`;
        if (riskOnly && k === 'good') o.op = 0.25;
      } else if (mode === 'queue') {
        // освободится — по макету без дороги: к ней уже никто не едет
        if (orphaned.has(s.request_id)) { o = { bg: '#fff', bd: `1.5px dashed ${RED}`, sh: 'none', ol: 'none', color: 'var(--red-ink)' }; road = false; }
      } else {
        const d = diff[s.request_id] || { status: 'unchanged' };
        if (d.status === 'newly_assigned') {
          o = { bg: INK, sh: 'none', ol: 'none', color: '#fff' };
          const urgent = view.requests[s.request_id]?.priority === 'urgent';
          mark = [urgent ? '+ срочная' : '+ новая', '+', INK, '#fff'];
        } else if (d.status === 'moved') {
          o = { bg: c.main, sh: 'none', ol: 'none', color: '#fff' };
          mark = [`↪ от ${INS(nameOf(view, d.from))}`, '↪', c.main, '#fff'];
        } else if (d.status === 'shifted' || d.status === 'reordered') {
          o = { bd: `1.5px solid ${c.main}`, sh: 'none', ol: 'none' };
          const sh = d.shift_min ? signedMin(d.shift_min) : '';
          mark = d.status === 'reordered'
            ? [`⇅ ${sh}`.trim(), '⇅', '#fff', INK, `1px solid ${c.main}`]
            : [sh, sh.replace(' мин', ''), '#fff', INK, `1px solid ${c.main}`];
        } else { o = { op: 0.3, ol: 'none' }; trOp = 0.2; }
        if (d.status !== 'unchanged') trOp = 0.6;
      }
      if (road) bars.push(travelBar(s, c, x, trOp));
      const bar = workBar(s, c, x, o);
      if (bar.w < 44) bar.label = '';
      bars.push(bar);
      if (mark) bars.push(badge(bar, mark[0], mark[1], mark[2], mark[3], mark[4]));
    }
    const note = mode === 'diff' ? engineerEvent(view, rt.engineer_id)?.short || null : null;
    return { eid: rt.engineer_id, name: e.name, meta: TRANSPORT_SHORT[e.transport] || e.transport, note,
             dot: idle ? IDLE : c.main, nameColor: idle ? 'var(--muted)' : INK, bars: unclutter(bars) };
  });
}

/** Подсказка при наведении. opts.mode — режим диаграммы (в разборе — что изменилось и где была);
 *  opts.ghost — инженер, у которого нарисован призрак прошлого плана: подсказка о том, что было. */
export function tip(view, colors, rid, { mode = 'plan', ghost = null } = {}) {
  const r = view.requests[rid] || { type: 'Отменённая заявка', address: '—' };
  const win = r.tw_start != null ? `${fmt(r.tw_start)}–${fmt(r.tw_end)}` : '—';
  if (ghost) {
    const p = stopsOf(view.previous?.routes)[rid], cur = stopsOf(view.plan.routes)[rid];
    if (!p) return null;
    const lines = [], c = changeNote(view, rid), gone = !cur;
    if (c) lines.push({ k: 'Что изменилось', t: c });
    if (cur) lines.push({ k: 'Теперь', t: `${cur.s.start}–${cur.s.finish}` + (cur.eid !== p.eid ? ` у ${INS(nameOf(view, cur.eid))}` : '') });
    return { id: rid, type: r.type, addr: r.address, win, planK: 'Было', plan: `${p.s.start}–${p.s.finish}`,
             eng: nameOf(view, p.eid), tol: null, tolColor: null, tint: gone ? 'var(--red-tint)' : 'var(--line-2)', lines };
  }
  const at = stopsOf(view.plan.routes)[rid];
  if (!at) return null;
  const [tol, tolColor] = tolText(tolOf(view, rid)), lines = [];
  if (mode === 'diff') {
    const c = changeNote(view, rid), w = wasNote(view, rid);
    if (c) lines.push({ k: 'Что изменилось', t: c });
    if (w) lines.push({ k: 'Раньше', t: w });
  }
  const why = lines.length ? null : whyNote(view, rid);
  if (why) lines.push({ k: 'Почему у него', t: why });
  return { id: rid, type: r.type, addr: r.address, win, planK: 'План', plan: `${at.s.start}–${at.s.finish}`,
           eng: nameOf(view, at.eid), tol, tolColor, tint: colors[at.eid].tint, lines };
}

/** «До / После / Изменения» — когда у плана есть прошлый (черновик или принятый пересчёт). */
export const VERSIONS = [{ k: 'before', t: 'До' }, { k: 'after', t: 'После' }, { k: 'diff', t: 'Изменения' }];
export const hasVersions = view => !!(view?.previous && view.plan.diff);
export const defaultVersion = view => (view.plan.accepted ? 'after' : 'diff');

/** Прошлый план в форме обычного view — диаграмма рисует его как план, подсказки и плитки — о нём. */
export function beforeView(view) {
  const p = view.previous;
  return { ...view, previous: null, risk: p.risk ?? null,
           plan: { ...view.plan, plan_id: p.plan_id, routes: p.routes, metrics: p.metrics, replan_of: p.replan_of ?? null,
                   assignments: p.assignments || {}, unassigned: p.unassigned || [], diff: null, events: [] } };
}

export const LEGEND = {
  plan: [{ t: 'заявка · цвет инженера', bg: '#F9DCE8', bd: 'none' }, { t: 'запас < 20 мин', bg: '#fff', bd: `2px solid ${AMB}` },
         { t: 'запас < 10 мин', bg: '#fff', bd: `2px solid ${RED}` }],
  queue: [{ t: 'освободится после ухода', bg: '#fff', bd: `1.5px dashed ${RED}` },
          { t: 'инженер недоступен', bg: 'repeating-linear-gradient(135deg,rgba(229,56,59,.25) 0 4px,transparent 4px 8px)', bd: 'none' },
          { t: 'прошлое не меняется', bg: 'rgba(25,28,31,.06)', bd: 'none' }],
  diff: [{ t: 'новая', bg: INK, bd: 'none', mark: '+', c: '#fff' },
         { t: 'передана · цвет нового инженера', bg: '#6D4C41', bd: 'none', mark: '↪', c: '#fff' },
         { t: 'сдвинута · пунктир — где была', bg: '#E0E4F7', bd: '1.5px solid #3F51B5', mark: '±', c: 'var(--ink)' },
         { t: 'ушла к другому инженеру', bg: 'transparent', bd: '1.5px dashed #9AA1AB', mark: '→', c: 'var(--ink-3)' },
         { t: 'отменена или снята', bg: 'rgba(229,56,59,.06)', bd: `1.5px dashed ${RED}`, mark: '×', c: 'var(--red-ink)' },
         { t: 'без изменений', bg: '#F9DCE8', bd: 'none', op: 0.4 }],
};

/** 4l «Что изменилось» — баннер, плитки «было», группы правок, пояснение ассистента, заметка после принятия. */
import { num, plural } from './num.js';

export const GEN = n => (/[ыио]й$/.test(n) ? n.slice(0, -2) + 'ого' : /[аяь]$/.test(n) ? n.slice(0, -1) + 'и' : n + 'а');   // Горбанев → Горбанева; для «-а/-я/-ь» — «-и»
export const INS = n => (/[ыио]й$/.test(n) ? n.slice(0, -2) + 'ого' : /[ая]$/.test(n) ? n.slice(0, -1) + 'ой'
  : /ь$/.test(n) ? n.slice(0, -1) + 'я' : n + 'а');  // «у Макарова», «у Козыря», «у Белоновского»

export function banner(plan) {
  const n = plan.events.length;
  return { title: `План пересчитан от ${plan.now}`,
           sub: `${plural(n, ['событие', 'события', 'событий'])} · ${num(plan.solve_time_s)} с · ` +
                (plan.accepted ? 'принят' : 'черновик, инженеры ещё не уведомлены') };
}

export function deltaTiles(plan, before) {
  const m = plan.metrics, better = (x, y) => (x <= y ? 'var(--green-ink)' : 'var(--amber-ink)');
  return [
    { k: 'Назначено', b: `${m.assigned} / ${m.assigned + m.unassigned}`, a: `было ${before.assigned}`, bg: 'var(--green-tint)',
      c: m.assigned >= before.assigned ? 'var(--green-ink)' : 'var(--red-ink)' },
    { k: 'Инженеров', b: String(m.engineers_used), a: `было ${before.engineers_used}`, bg: 'var(--yellow-tint)', c: 'var(--ink-3)' },
    { k: 'Пробег, км', b: num(m.total_km, 0), a: `было ${num(before.total_km, 0)}`, bg: 'var(--blue-tint)', c: better(m.total_km, before.total_km) }];
}

const startOf = plan => Object.fromEntries(plan.routes.flatMap(rt => rt.stops.map(s => [s.request_id, s.start])));

export function groups(plan, names) {
  const at = startOf(plan), d = Object.entries(plan.diff.requests);
  const pick = (st, text, t = rid => at[rid] || '') => d.filter(([, v]) => st.includes(v.status)).map(([rid, v]) => ({ id: rid, text: text(v), t: t(rid) }));
  const out = [
    { t: 'Новые', sw: { bg: 'var(--ink)', bd: 'none' }, items: pick(['newly_assigned'], v => `→ ${names[v.engineer_id]}`) },
    { t: 'Переданы', sw: { bg: '#6D4C41', bd: 'none' }, items: pick(['moved'], v => `${names[v.from]} → ${names[v.to]}`) },
    { t: 'Сдвинуты', sw: { bg: '#E0E4F7', bd: '1.5px dashed #3F51B5' },
      items: pick(['shifted', 'reordered'], v => `${names[v.engineer_id]}, ${v.shift_min > 0 ? '+' : ''}${v.shift_min} мин`) },
    { t: 'Сняты с плана', sw: { bg: 'var(--red-tint)', bd: '1.5px solid var(--red)' }, items: pick(['newly_unassigned'], v => v.from ? `было у ${names[v.from]}` : '', () => '') },
    { t: 'Отменены', sw: { bg: 'var(--chip)', bd: 'none' }, items: pick(['removed'], () => 'отмена принята', () => '') }];
  return out.filter(g => g.items.length).map(g => ({ ...g, n: g.items.length }));
}

export function insight(plan, names) {
  const d = plan.diff, parts = [];
  for (const [k, v] of Object.entries(d.engineers)) if (v.status === 'removed') {
    const to = [...new Set(Object.values(d.requests).filter(x => x.status === 'moved' && x.from === k).map(x => names[x.to]))];
    parts.push(to.length ? `Заявки ${GEN(names[k])} переданы: ${to.join(', ')}.` : `У ${GEN(names[k])} заявок не осталось.`);
  }
  for (const ev of plan.events.filter(e => e.type === 'urgent_request')) {
    const got = d.requests[ev.request.id];
    if (!got || got.status !== 'newly_assigned') { parts.push(`Срочная ${ev.request.id} не размещена.`); continue; }
    const k = got.engineer_id, sh = Object.values(d.requests).filter(x => (x.status === 'shifted' || x.status === 'reordered') && x.engineer_id === k).length;
    parts.push(`Срочная ${ev.request.id} у ${INS(names[k])}` + (sh ? `, его ${plural(sh, ['заявка сдвинута', 'заявки сдвинуты', 'заявок сдвинуто'])} внутри окон.` : '.'));
  }
  const lost = Object.values(d.requests).filter(x => x.status === 'newly_unassigned').length;
  parts.push(lost ? `Не удалось разместить ${plural(lost, ['заявку', 'заявки', 'заявок'])}.` : 'Все заявки размещены.');
  return parts.join(' ');
}

export const affectedText = (ids, names) => ids.length
  ? `План принят · изменения затрагивают ${plural(ids.length, ['инженера', 'инженеров', 'инженеров'])}: ${ids.map(k => names[k]).join(', ')}`
  : 'План принят · маршруты инженеров не изменились';

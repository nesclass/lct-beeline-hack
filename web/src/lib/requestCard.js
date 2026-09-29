/** 4e — карточка заявки: почему этот инженер, кто ещё мог бы, переназначение. */
import { SKILL_SHORT } from './labels.js';
import { num } from './num.js';
import { fmt } from './time.js';
import { tolOf, tolText } from './gantt.js';

const TR = { car: 'авто', foot: 'пешком', bike: 'вело', public: 'транспорт' };
const HARD = { SKILL: 'нет навыка', TRANSPORT: 'нет транспорта', PINNED: 'закреплена за другим' };
const SOFT = { WINDOW_REACH: 'не успевает к окну', SHIFT_FIT: 'не помещается в смену' };

function altText(a) {
  if (a.feasible) return [`+${num(a.delta_km)} км, приезд ${a.arrive}`, 'ok'];
  const code = a.blocker.code;
  if (HARD[code]) return [HARD[code], 'bad'];
  if (SOFT[code]) return [SOFT[code], 'warn'];
  const until = a.blocker.text.match(/до (\d\d:\d\d)\)/);
  return [until ? `занят до ${until[1]}` : 'занят', 'warn'];
}

export function cardFor(view, colors, rid) {
  const r = view.requests[rid];
  if (!r) return null;
  const a = view.plan.assignments[rid];
  const win = `${fmt(r.tw_start)}–${fmt(r.tw_end)}`;
  const head = { id: rid, type: r.type, addr: r.address, checks: [], alts: [], movable: [], why: null, explain: a?.text ?? '' };
  if (!a) return { ...head, status: { text: 'ещё не в расписании', tone: 'warn' }, tint: 'var(--amber-tint)',
                   rows: [['Окно клиента', win]], explain: 'Заявка заведена после расчёта — попадёт в расписание при перепланировании.' };
  if (!a.engineer_id) return { ...head, status: { text: 'не назначена', tone: 'bad' }, tint: 'var(--red-tint)', rows: [['Окно клиента', win]] };
  const k = a.engineer_id, c = colors[k], e = view.engineers[k];
  if (a.locked) return { ...head, status: { text: 'заморожена', tone: 'gray' }, tint: c.tint,
                         rows: [['Инженер', e.name, c.main], ['Окно клиента', win]] };
  const rs = a.reason, [tol, tolColor] = tolText(tolOf(view, rid));
  const alts = rs.alternatives.map(x => {
    const [text, tone] = altText(x);
    return { eid: x.engineer_id, name: view.engineers[x.engineer_id].name, c: colors[x.engineer_id].main, text, tone, delta_km: x.delta_km };
  });
  const rank = { ok: 0, warn: 1, bad: 2 };
  // сначала по группе (можно → заняты → не подходят), внутри «можно» — по возрастанию км; остальные группы — как пришли с сервера
  alts.sort((p, q) => rank[p.tone] - rank[q.tone] || (p.tone === 'ok' ? p.delta_km - q.delta_km : 0));
  const feas = rs.alternatives.filter(x => x.feasible).sort((p, q) => p.delta_km - q.delta_km);
  const pos = rs.position;
  const where = pos.prev_request_id && pos.next_request_id ? `между ${pos.prev_request_id} и ${pos.next_request_id}`
    : pos.prev_request_id ? 'в конец маршрута' : 'в начало маршрута';
  let why = `${e.name} ближе всех из подходящих: вставка ${where} добавляет ${num(rs.delta_km)} км.`;
  if (feas.length) why += ` ${view.engineers[feas[0].engineer_id].name} тоже может, но +${num(feas[0].delta_km)} км.`;
  else why = `${e.name} — единственный, кто успевает: вставка ${where} добавляет ${num(rs.delta_km)} км.`;
  return {
    ...head, status: a.manual ? { text: 'закреплена диспетчером', tone: 'ok' } : { text: 'назначена', tone: 'ok' }, tint: c.tint,
    rows: [['Инженер', `${e.name} · ${pos.seq}-я в маршруте`, c.main], ['Окно клиента', win],
           ['Приезд · работа', `${rs.arrive} · ${rs.start}–${rs.finish}`], ['Запас', tol, tolColor]],
    why, checks: [`навык «${SKILL_SHORT[r.skill]}»`, `транспорт: ${TR[e.transport]}`, `окно ${win}`, 'в пределах смены'],
    alts: alts.slice(0, 4).map(({ eid, name, c: col, text, tone: t }) => ({ eid, name, c: col, text, tone: t })),
    movable: alts.filter(x => x.tone === 'ok').map(({ eid, name, text }) => ({ eid, name, text })),
  };
}

import { SKILL_SHORT } from './labels.js';
import { num, plural } from './num.js';
import { fmt } from './time.js';
import { tolOf, tone } from './gantt.js';

const WHO = { foot: 'пеший', car: 'на авто', bike: 'на велосипеде', public: 'на транспорте' };

export function kpis(view) {
  const m = view.plan.metrics, risk = view.risk;
  const crit = risk ? Object.values(risk.tol).filter(t => t < 10).length : null;
  return [
    { label: 'Назначено', val: `${m.assigned} / ${m.assigned + m.unassigned}`, c: 'var(--green)' },
    { label: 'Инженеров', val: `${m.engineers_used} / ${m.engineers_total}`, c: 'var(--yellow)' },
    { label: 'Пробег', val: `${num(m.total_km, 0)} км`, c: 'var(--blue)' },
    { label: 'Запас < 10 мин', val: crit == null ? '—' : String(crit), c: 'var(--red)' },
    { label: 'Ожид. опозданий', val: risk ? num(risk.stress.expected_late) : '—', c: 'var(--amber)' }];
}

export function shortReason(r, reason, dict) {
  const skill = SKILL_SHORT[r.skill] || r.skill;
  switch (reason.code) {
    case 'SKILL': case 'TRANSPORT':
      return r.required_transport
        ? `Нужен ${WHO[r.required_transport]} инженер с навыком «${skill}» — таких в смене нет`
        : `Нет инженера с навыком «${skill}»`;
    case 'SHIFT_FIT': return `${plural(r.duration, ['минута', 'минуты', 'минут'])} работы не помещаются до конца ни одной смены`;
    case 'WINDOW_REACH': return 'Никто не успевает доехать до конца окна';
    case 'BUSY': return reason.probes?.length ? `Все ${reason.probes.length} подходящих инженера заняты` : 'Все подходящие инженеры заняты';
    case 'DISPLACED': return 'Вытеснена срочной заявкой';
    case 'ENGINEER_LOST': return 'Инженер выбыл, у остальных нет места в окне';
    case 'PINNED': return 'Закреплена за инженером, у которого больше нет места';
    default: return reason.code;
  }
}

export const unassignedList = view => view.plan.unassigned.map(rid => {
  const r = view.requests[rid];
  return { id: rid, type: r.type, win: `${fmt(r.tw_start)}–${fmt(r.tw_end)}`,
           why: shortReason(r, view.plan.assignments[rid].reason, view.dict) };
});

export function tightList(view, colors, n = 4) {
  const out = [];
  for (const rt of view.plan.routes) for (const s of rt.stops) {
    const t = tolOf(view, s.request_id);
    if (t < 20) out.push({ id: s.request_id, eng: view.engineers[rt.engineer_id].name, ec: colors[rt.engineer_id].main,
                           t: s.start, tol: t, tone: tone(t) });
  }
  return out.sort((a, b) => a.tol - b.tol).slice(0, n);
}

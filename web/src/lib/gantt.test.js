import { describe, expect, it } from 'vitest';
import { LEGEND, beforeView, changeNote, dayBounds, defaultVersion, engineerEvent, hasVersions, offFrom, rows, tip, tolText, tone,
  wasNote, whyNote, ZOOMS, trackWidth } from './gantt.js';

const S1 = { request_id: 'R1', seq: 1, arrive: '09:10', start: '10:00', finish: '11:00', wait_min: 50, leg_min: 10, leg_km: 3, slack_min: 60, locked: true };
const S2 = { request_id: 'R2', seq: 2, arrive: '11:20', start: '11:20', finish: '12:30', wait_min: 0, leg_min: 20, leg_km: 5, slack_min: 5, locked: false };
const view = {
  plan: { replan_of: null, now: null, diff: null, routes: [
    { engineer_id: 'E01', stops: [S1, S2] },
    { engineer_id: 'E02', stops: [], unavailable_from: '12:00' },
    { engineer_id: 'E03', stops: [], breaks: [{ start: '13:00', end: '14:00' }] }] },
  risk: { tol: { R1: 40, R2: 8 }, late_prob: {} },
  engineers: { E01: { name: 'Горбанев', transport: 'car', shift_start: 540, shift_end: 1080 },
               E02: { name: 'Паршин', transport: 'foot', shift_start: 540, shift_end: 1080 },
               E03: { name: 'Козырь', transport: 'bike', shift_start: 600, shift_end: 1140 } },
  requests: { R1: { type: 'Нет линка', address: 'ул. А, 1', district: 'Царицыно', tw_start: 600, tw_end: 720, duration: 60 },
              R2: { type: 'Подключение', address: 'ул. Б, 2', district: 'Братеево', tw_start: 660, tw_end: 780, duration: 70 } },
};
const colors = { E01: { main: '#E4572E', tint: '#FCE3DB' }, E02: { main: '#F29E1F', tint: '#FDEFD6' }, E03: { main: '#2FA84F', tint: '#DDF3E2' } };
const x = t => t - 540;

describe('шкала и пороги', () => {
  it('день по целым часам', () => { expect(dayBounds(view)).toEqual([540, 1140]); });
  it('запас', () => {
    expect([tone(3), tone(12), tone(40)]).toEqual(['crit', 'warn', 'good']);
    expect(tolText(3)).toEqual(['3 мин · риск опоздания', 'var(--red-ink)']);
    expect(tolText(12)).toEqual(['12 мин · мало', 'var(--amber-text)']);
    expect(tolText(80)).toEqual(['80 мин', 'var(--green-ink)']);
  });
});

describe('строки плана', () => {
  it('дорога, работа с цветом инженера, обводка по запасу, подпись', () => {
    const [r1] = rows(view, colors, x, { mode: 'plan' });
    expect(r1).toMatchObject({ eid: 'E01', name: 'Горбанев', meta: 'Авто', dot: '#E4572E' });
    const [trv, w1, , w2] = r1.bars;
    expect(trv).toMatchObject({ kind: 'travel', l: 0, w: 10, top: 17, h: 2, bg: '#E4572E', op: 0.5 });
    expect(w1).toMatchObject({ kind: 'work', rid: 'R1', l: 60, w: 60, bg: '#FCE3DB', sh: 'inset 3px 0 0 #E4572E', ol: 'none', label: 'R1' });
    expect(w2).toMatchObject({ rid: 'R2', ol: '2px solid var(--red)' });
  });
  it('выбранная — чёрная обводка; «только с риском» гасит спокойные', () => {
    const [r1] = rows(view, colors, x, { mode: 'plan', selected: 'R1', riskOnly: true });
    const w = r1.bars.filter(b => b.kind === 'work');
    expect(w[0]).toMatchObject({ ol: '2px solid var(--ink)', op: 0.25 });
    expect(w[1].op).toBe(1);
  });
  it('инженер без заявок — серая точка и имя; недоступный — штриховка; перерыв — блок', () => {
    const r = rows(view, colors, x, { mode: 'plan' });
    expect(r[1]).toMatchObject({ dot: '#C9CED6', nameColor: 'var(--muted)' });
    expect(r[1].bars[0]).toMatchObject({ kind: 'hatch', l: 0, w: 540 });
    expect(r[2].bars[0]).toMatchObject({ kind: 'break', l: 240, w: 60, label: 'перерыв' });
  });
  it('фильтр по инженеру', () => {
    expect(rows(view, colors, x, { mode: 'plan', only: 'E02' }).map(r => r.eid)).toEqual(['E02']);
  });
});

describe('очередь и разбор', () => {
  it('освободится — белая с красным пунктиром; уходящий — штриховка с ухода', () => {
    const [r1] = rows(view, colors, x, { mode: 'queue', orphaned: new Set(['R2']), leaving: { E01: 690 } });
    expect(r1.bars[0]).toMatchObject({ kind: 'hatch', l: 150 });
    const w2 = r1.bars.find(b => b.rid === 'R2');
    expect(w2).toMatchObject({ bg: '#fff', bd: '1.5px dashed var(--red)', color: 'var(--red-ink)', sh: 'none', ol: 'none' });
  });
  it('новая, переданная, сдвинутая, без изменений, призрак', () => {
    const v = { ...view, previous: { routes: [{ engineer_id: 'E02', stops: [{ ...S1, request_id: 'R9', start: '15:00', finish: '16:00', arrive: '14:50' }] }] },
      requests: { ...view.requests, R9: { type: 'x', address: '', district: '', tw_start: 900, tw_end: 960, duration: 60 } },
      plan: { ...view.plan, replan_of: 'p0', diff: { requests: {
        R1: { status: 'unchanged' }, R2: { status: 'shifted', engineer_id: 'E01', shift_min: 15 },
        R9: { status: 'moved', from: 'E02', to: 'E01', shift_min: 0 } } },
        routes: [{ engineer_id: 'E01', stops: [S1, S2, { ...S2, request_id: 'R9', start: '15:00', finish: '16:00', arrive: '14:50' }] },
                 { engineer_id: 'E02', stops: [], unavailable_from: '12:00' }, view.plan.routes[2]] } };
    const [r1, r2] = rows(v, colors, x, { mode: 'diff' });
    const w = Object.fromEntries(r1.bars.filter(b => b.kind === 'work').map(b => [b.rid, b]));
    expect(w.R1.op).toBe(0.3);
    // по замыслу: сдвинутая — сплошная рамка (пунктир теперь у места, где была), сдвиг и «↪» — в значке, не в подписи
    expect(w.R2).toMatchObject({ bg: '#FCE3DB', bd: '1.5px solid #E4572E', label: 'R2' });
    expect(w.R9).toMatchObject({ bg: '#E4572E', color: '#fff', label: 'R9' });
    expect(r2.bars.find(b => b.kind === 'ghost')).toMatchObject({ rid: 'R9', bd: '1.5px dashed #9AA1AB', bg: 'transparent' });
  });
});

describe('подсказка', () => {
  it('поля и цвет запаса', () => {
    expect(tip(view, colors, 'R2')).toEqual({ id: 'R2', type: 'Подключение', addr: 'ул. Б, 2', win: '11:00–13:00',
      planK: 'План', plan: '11:20–12:30', eng: 'Горбанев', tol: '8 мин · риск опоздания', tolColor: 'var(--red-ink)', tint: '#FCE3DB',
      lines: [] });
  });
});

describe('когда штриховать недоступность', () => {
  const e = { shift_start: 480 };
  it('базовый — с ухода (но не раньше смены); перепланирование — с момента; без заявок — весь день', () => {
    expect(offFrom({ stops: [S1], unavailable_from: '12:00' }, e, { replan_of: null })).toBe(720);
    expect(offFrom({ stops: [S1], unavailable_from: '07:00' }, e, { replan_of: null })).toBe(480);
    expect(offFrom({ stops: [S1], unavailable_from: '12:00' }, e, { replan_of: 'p' })).toBe(720);
    expect(offFrom({ stops: [], unavailable_from: '12:00' }, e, { replan_of: 'p' })).toBe(480);
    expect(offFrom({ stops: [S1] }, e, { replan_of: null })).toBeNull();
  });
});

// Пересчёт в 14:00: Горбанев ушёл, пришла срочная R8, R6 отменена, R7 не поместилась.
const P = (rid, start, finish, o = {}) => ({ request_id: rid, seq: 1, arrive: start, start, finish, wait_min: 0, leg_min: 0, leg_km: 0, slack_min: 30, locked: false, ...o });
const dv = {
  engineers: view.engineers, dict: {},
  requests: { ...view.requests,
    R5: { type: 'Роутер', address: 'ул. В, 5', tw_start: 900, tw_end: 1020, duration: 30 },
    R7: { type: 'Приставка', address: 'ул. Г, 7', skill: 'local', tw_start: 780, tw_end: 840, duration: 30 },
    R8: { type: 'Авария', address: 'ул. Д, 8', priority: 'urgent', tw_start: 660, tw_end: 780, duration: 40 } },
  risk: null,
  previous: { plan_id: 'p0', replan_of: null, metrics: {}, unassigned: [],
    assignments: { R1: { engineer_id: 'E01' }, R2: { engineer_id: 'E02' }, R5: { engineer_id: 'E01' }, R6: { engineer_id: 'E02' }, R7: { engineer_id: 'E03' } },
    routes: [{ engineer_id: 'E01', stops: [P('R1', '10:00', '11:00'), P('R5', '15:10', '15:40')] },
             { engineer_id: 'E02', stops: [P('R2', '11:20', '12:30'), P('R6', '13:00', '13:30')] },
             { engineer_id: 'E03', stops: [P('R7', '13:00', '13:30')] }] },
  plan: { plan_id: 'p1', replan_of: 'p0', accepted: false, now: '14:00', unassigned: ['R7'],
    events: [{ type: 'engineer_unavailable', engineer_id: 'E01', time: '14:00', mode: 'leave' },
             { type: 'urgent_request', request: { id: 'R8' } }, { type: 'cancel_request', request_id: 'R6' }],
    assignments: { R1: { engineer_id: 'E01', locked: true, reason: { locked: true } },
                   R2: { engineer_id: 'E02', reason: { delta_km: 1, alternatives: [{ engineer_id: 'E03', feasible: true, delta_km: 4.2 }] } },
                   R5: { engineer_id: 'E02', reason: { delta_km: 2, alternatives: [] } },
                   R7: { engineer_id: null, reason: { code: 'BUSY', probes: [] } },
                   R8: { engineer_id: 'E02', manual: true, reason: {} } },
    diff: { engineers: { E01: { status: 'removed' }, E02: { status: 'changed' }, E03: { status: 'changed' } },
            requests: { R1: { status: 'unchanged' }, R2: { status: 'shifted', engineer_id: 'E02', shift_min: 25 },
                        R5: { status: 'moved', from: 'E01', to: 'E02', shift_min: 0 }, R6: { status: 'removed' },
                        R7: { status: 'newly_unassigned', from: 'E03', reason: 'BUSY' }, R8: { status: 'newly_assigned', engineer_id: 'E02' } } },
    routes: [{ engineer_id: 'E01', unavailable_from: '14:00', stops: [P('R1', '10:00', '11:00', { locked: true })] },
             { engineer_id: 'E02', stops: [P('R8', '11:00', '11:40'), P('R2', '11:45', '12:55'), P('R5', '15:10', '15:40')] },
             { engineer_id: 'E03', stops: [] }] },
};
const byRid = (row, kind) => Object.fromEntries(row.bars.filter(b => b.kind === kind).map(b => [b.rid, b]));

describe('разбор: значки и призраки', () => {
  const [r1, r2, r3] = rows(dv, colors, x, { mode: 'diff' });
  const b2 = byRid(r2, 'badge'), g1 = byRid(r1, 'ghost'), g2 = byRid(r2, 'ghost'), g3 = byRid(r3, 'ghost');
  it('значок у каждой правки: новая срочная, передана от кого, сдвиг в минутах', () => {
    expect(b2.R8).toMatchObject({ full: '+ срочная', short: '+', bg: 'var(--ink)', l: 120 });
    expect(b2.R5).toMatchObject({ text: '↪ от Горбанева', bg: '#F29E1F' });
    expect(b2.R2).toMatchObject({ full: '+25 мин', short: '+25', l: 165 });
    expect(b2.R5.text).toBe('↪ от Горбанева');
  });
  it('налезают — левый сокращается до символа, а если мало — и правый', () => {
    expect([b2.R8.text, b2.R2.text]).toEqual(['+', '+25 мин']);
    const [, r] = rows({ ...dv, plan: { ...dv.plan, routes: [dv.plan.routes[0],
      { engineer_id: 'E02', stops: [P('R8', '11:00', '11:10'), P('R2', '11:12', '12:55'), P('R5', '15:10', '15:40')] }, dv.plan.routes[2]] } },
      colors, x, { mode: 'diff' });
    expect(byRid(r, 'badge').R2.text).toBe('+25');
  });
  it('перестановка — «⇅»', () => {
    const v = { ...dv, plan: { ...dv.plan, diff: { ...dv.plan.diff, requests: { ...dv.plan.diff.requests,
      R2: { status: 'reordered', engineer_id: 'E02', from_seq: 1, to_seq: 2, shift_min: -5 } } } } };
    expect(byRid(rows(v, colors, x, { mode: 'diff' })[1], 'badge').R2.full).toBe('⇅ −5 мин');
  });
  it('переданная: серый призрак у прежнего инженера с «→ новый»', () => {
    expect(g1.R5).toMatchObject({ bd: '1.5px dashed #9AA1AB', l: 370, eid: 'E01' });
    expect(byRid(r1, 'badge').R5.text).toBe('→ Паршин');
  });
  it('сдвинутая: пунктир прежнего места на той же строке', () => {
    expect(g2.R2).toMatchObject({ l: 140, w: 70, bd: '1.5px dashed #F29E1F', label: '' });
  });
  it('отменённая и снятая — красный пунктир с подписью', () => {
    expect(g2.R6).toMatchObject({ bd: '1.5px dashed var(--red)' });
    expect(byRid(r2, 'badge').R6.text).toBe('отменена');
    expect(g3.R7).toMatchObject({ bd: '1.5px dashed var(--red)' });
    expect(byRid(r3, 'badge').R7.text).toBe('снята');
  });
  it('без изменений — бледная; у выбывшего — пометка в колонке имени', () => {
    expect(byRid(r1, 'work').R1.op).toBe(0.3);
    expect([r1.note, r2.note]).toEqual(['выбыл 14:00', null]);
    expect(rows(dv, colors, x, { mode: 'plan' })[0].note).toBeNull();
  });
  it('легенда разбора — ровно то, что рисуется', () => {
    expect(LEGEND.diff.map(l => l.t)).toEqual(['новая', 'передана · цвет нового инженера', 'сдвинута · пунктир — где была',
      'ушла к другому инженеру', 'отменена или снята', 'без изменений']);
  });
});

describe('разбор: пояснения', () => {
  it('что случилось с инженером', () => {
    expect(engineerEvent(dv, 'E01')).toEqual({ short: 'выбыл 14:00', why: 'выбыл в 14:00' });
    const brk = { ...dv, plan: { ...dv.plan, events: [{ type: 'engineer_break', engineer_id: 'E02', time: '13:00', until: '14:00' }] } };
    expect(engineerEvent(brk, 'E02').why).toBe('перерыв 13:00–14:00');
    expect(engineerEvent(dv, 'E03')).toBeNull();
  });
  it('переданная от выбывшего, срочная, сдвинутая из-за вставки, отменённая, снятая', () => {
    expect(changeNote(dv, 'R5')).toBe('Передана от Горбанева — выбыл в 14:00');
    expect(changeNote(dv, 'R8')).toBe('Новая срочная заявка');
    expect(changeNote(dv, 'R2')).toBe('Сдвинута на 25 мин позже: перед ней вставлена R8');
    expect(changeNote(dv, 'R6')).toBe('Заявка отменена');
    expect(changeNote(dv, 'R7')).toBe('Снята с плана: Все подходящие инженеры заняты');
    expect(changeNote(dv, 'R1')).toBeNull();
  });
  it('сдвиг без вставки: убранная перед ней, иначе — порядок', () => {
    const v = { ...dv, previous: { ...dv.previous, routes: [dv.previous.routes[0],
      { engineer_id: 'E02', stops: [P('R6', '10:00', '10:30'), P('R2', '11:20', '12:30')] }, dv.previous.routes[2]] },
      plan: { ...dv.plan, routes: [dv.plan.routes[0], { engineer_id: 'E02', stops: [P('R2', '10:55', '12:05')] }, dv.plan.routes[2]],
              diff: { ...dv.plan.diff, requests: { ...dv.plan.diff.requests, R2: { status: 'shifted', engineer_id: 'E02', shift_min: -25 } } } } };
    expect(changeNote(v, 'R2')).toBe('Сдвинута на 25 мин раньше: перед ней убрана R6');
    const r = { ...v, previous: dv.previous, plan: { ...v.plan, diff: { ...v.plan.diff, requests: { ...v.plan.diff.requests,
      R2: { status: 'reordered', engineer_id: 'E02', from_seq: 1, to_seq: 1, shift_min: -25 } } } } };
    expect(changeNote(r, 'R2')).toBe('Сдвинута на 25 мин раньше: изменился порядок заявок');
  });
  it('переданная не из-за ухода — кому освободила место', () => {
    const v = { ...dv, plan: { ...dv.plan, events: [],
      diff: { ...dv.plan.diff, engineers: {}, requests: { ...dv.plan.diff.requests, R5: { status: 'moved', from: 'E03', to: 'E02' },
        R7: { status: 'moved', from: 'E02', to: 'E03' } } },
      routes: [dv.plan.routes[0], dv.plan.routes[1], { engineer_id: 'E03', stops: [P('R7', '13:00', '13:30')] }] } };
    expect(changeNote(v, 'R5')).toBe('Передана от Козыря: освободила место для R7');
  });
  it('где была раньше', () => {
    expect(wasNote(dv, 'R5')).toBe('15:10–15:40 у Горбанева');
    expect(wasNote(dv, 'R2')).toBe('11:20–12:30');
    expect(wasNote(dv, 'R1')).toBeNull();
  });
  it('почему у этого инженера: начата, закреплена, ближе всех, иначе — молчим', () => {
    expect(whyNote(dv, 'R1')).toBe('Уже начата или выполнена — пересчёт её не меняет');
    expect(whyNote(dv, 'R8')).toBe('Закреплена диспетчером');
    expect(whyNote(dv, 'R2')).toBe('Ближе всех по дороге: у Козыря было бы на 3,2 км больше');
    expect(whyNote(dv, 'R5')).toBe('Другие подходящие инженеры заняты или не успевают в окно');
    expect(whyNote(dv, 'R7')).toBeNull();
  });
  it('подсказка разбора и подсказка призрака', () => {
    expect(tip(dv, colors, 'R5', { mode: 'diff' }).lines).toEqual([
      { k: 'Что изменилось', t: 'Передана от Горбанева — выбыл в 14:00' }, { k: 'Раньше', t: '15:10–15:40 у Горбанева' }]);
    expect(tip(dv, colors, 'R2', { mode: 'plan' }).lines).toEqual([{ k: 'Почему у него', t: 'Ближе всех по дороге: у Козыря было бы на 3,2 км больше' }]);
    expect(tip(dv, colors, 'R5', { mode: 'diff', ghost: 'E01' })).toMatchObject({ planK: 'Было', plan: '15:10–15:40', eng: 'Горбанев', tol: null,
      lines: [{ k: 'Что изменилось', t: 'Передана от Горбанева — выбыл в 14:00' }, { k: 'Теперь', t: '15:10–15:40 у Паршина' }] });
    expect(tip(dv, colors, 'R6', { mode: 'diff', ghost: 'E02' })).toMatchObject({ type: 'Отменённая заявка', win: '—', tint: 'var(--red-tint)',
      lines: [{ k: 'Что изменилось', t: 'Заявка отменена' }] });
  });
});

describe('до и после', () => {
  it('переключатель есть, когда есть прошлый план; черновик — разбор, принятый — «После»', () => {
    expect(hasVersions(dv)).toBe(true);
    expect(hasVersions(view)).toBe(false);
    expect(defaultVersion(dv)).toBe('diff');
    expect(defaultVersion({ ...dv, plan: { ...dv.plan, accepted: true } })).toBe('after');
  });
  it('«До» — прошлый план как обычный: его маршруты, назначения и запас, без разбора', () => {
    const b = beforeView(dv);
    expect(b.plan.routes).toBe(dv.previous.routes);
    expect(b.plan).toMatchObject({ plan_id: 'p0', replan_of: null, diff: null, events: [] });
    expect([b.previous, b.risk]).toEqual([null, null]);
    expect(rows(b, colors, x, { mode: 'plan' })[0].bars.filter(bar => bar.kind === 'work').map(bar => bar.rid)).toEqual(['R1', 'R5']);
    expect(tip(b, colors, 'R5')).toMatchObject({ plan: '15:10–15:40', eng: 'Горбанев', tol: '30 мин' });
    expect(beforeView({ ...dv, previous: { ...dv.previous, risk: { tol: { R5: 12 } } } }).risk.tol.R5).toBe(12);
  });
});

describe('масштаб диаграммы', () => {
  it('весь день — по ширине, не уже 780; крупнее — шире и с прокруткой', () => {
    expect(trackWidth(1100, 780, 0)).toBe(1100);
    expect(trackWidth(500, 780, 0)).toBe(780);
    expect(trackWidth(1100, 780, 2)).toBe(Math.round(780 * ZOOMS[2]));
    expect(trackWidth(3000, 780, 1)).toBe(3000);          // экран шире масштаба — не сжимаем
  });
  it('на самом крупном 15-минутная заявка шире порога подписи', () => {
    expect(15 * ZOOMS[ZOOMS.length - 1]).toBeGreaterThanOrEqual(44);
  });
});

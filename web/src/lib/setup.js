/** Данные 4b «Как строить план»: цели расчёта, пресеты запаса, состав сессии. */
import { SKILL_SHORT, TRANSPORT_SHORT } from './labels.js';
import { plural } from './num.js';

export const GOALS = [
  { key: 'fewer', t: 'Меньше инженеров', d: 'всех успеть минимальным составом' },
  { key: 'shorter', t: 'Меньше пробега', d: 'короче маршруты, можно больше людей' },
  { key: 'balance', t: 'Баланс', d: 'люди и километры поровну' }];
export const MARGINS = { econom: [0, 0, 0], balanced: [10, 10, 2], reliable: [20, 20, 5] };   // = app/schema.py
export const MARGIN_TITLE = { econom: 'Экономный', balanced: 'Сбалансированный', reliable: 'Надёжный' };

export function marginLine([w, t, m]) {
  if (!w && !t && !m) return 'без запаса: норматив и время в пути как есть';
  const parts = w === t && w ? [`+${w} % к работе и дороге`]
    : [...(w ? [`+${w} % к работе`] : []), ...(t ? [`+${t} % к дороге`] : [])];
  if (m) parts.push(`+${m} мин на каждый переезд`);
  return parts.join(', ');
}

export const applyMargin = (st, key) => {
  const [w, t, m] = MARGINS[key];
  return { ...st, work_pct: w, travel_pct: t, travel_min: m, margin: key };
};

export function marginOf(st) {
  const k = Object.keys(MARGINS).find(k => MARGINS[k].join() === [st.work_pct, st.travel_pct, st.travel_min].join());
  return k || 'custom';
}

const SKILL_BAR = { local: 'var(--sk-local)', connect: 'var(--sk-connect)', emergency: 'var(--sk-em)' };
const TR_BAR = { car: 'var(--blue)', foot: 'var(--green)', bike: '#F29E1F', public: '#00A3A3' };

export function sessionMix(requests, engineers) {
  const count = (xs, k, v) => xs.filter(x => x[k] === v).length;
  return [
    { t: 'Заявки по навыкам', total: plural(requests.length, ['заявка', 'заявки', 'заявок']),
      parts: Object.keys(SKILL_BAR).map(k => ({ l: SKILL_SHORT[k], n: count(requests, 'skill', k), c: SKILL_BAR[k] })) },
    { t: 'Инженеры по транспорту', total: plural(engineers.length, ['инженер', 'инженера', 'инженеров']),
      parts: Object.keys(TR_BAR).map(k => ({ l: TRANSPORT_SHORT[k], n: count(engineers, 'transport', k), c: TR_BAR[k] })) }];
}

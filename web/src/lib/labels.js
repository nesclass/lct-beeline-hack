import { plural } from './num.js';

export const SKILL_SHORT = { local: 'Локальные', connect: 'Подключение', emergency: 'Аварийные' };
export const SKILL_CHIP = { local: ['var(--sk-local-bg)', 'var(--sk-local)'], connect: ['var(--sk-connect-bg)', 'var(--sk-connect)'],
                            emergency: ['var(--sk-em-bg)', 'var(--sk-em)'] };
export const TRANSPORT_SHORT = { car: 'Авто', foot: 'Пешком', bike: 'Вело', public: 'Транспорт' };

export function sessionPill(status, pending) {
  if (status === 'planned') return { text: 'План актуален', tone: 'ok' };
  if (status === 'draft') return { text: 'Черновик', tone: 'warn' };
  if (status === 'dirty') {
    const [n, w] = plural(pending, ['изменение', 'изменения', 'изменений']).split(' ');
    return { text: `${n} ${w} ${pending % 10 === 1 && pending % 100 !== 11 ? 'ждёт' : 'ждут'}`, tone: 'warn' };
  }
  return { text: 'Плана нет', tone: 'gray' };
}

const two = n => String(n).padStart(2, '0');
export function whenText(ts, now = Date.now() / 1000) {
  const d = new Date(ts * 1000), n = new Date(now * 1000);
  const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(n) - day(d)) / 86400000);
  const hhmm = `${two(d.getHours())}:${two(d.getMinutes())}`;
  if (diff === 0) return `сегодня, ${hhmm}`;
  if (diff === 1) return `вчера, ${hhmm}`;
  return `${two(d.getDate())}.${two(d.getMonth() + 1)}, ${hhmm}`;
}

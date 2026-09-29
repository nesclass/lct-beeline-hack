/** Данные 4c «Варианты плана»: строки таблицы и полосы сравнения. */
import { num } from './num.js';

export const VARIANT_COLOR = { baseline: '#C9CED6', econom: '#2F6BFF', balanced: '#FFD200', reliable: '#16A34A' };

export const variantRows = (rows, recommended, selected, threshold) => rows.map(v => ({
  ...v, asg: `${v.assigned} / ${v.total}`, eng: v.engineers_used, km: num(v.total_km, 0),
  late: num(v.expected_late), over: v.overtime_min == null ? '—' : `${v.overtime_min} мин`,
  rec: v.key === recommended, on: v.key === selected, lateBad: (v.expected_late ?? 0) > threshold,
  color: VARIANT_COLOR[v.key],
}));

export function compareCharts(rows) {
  const chart = (title, sub, get, show) => {
    const max = Math.max(...rows.map(get)) || 1;
    return { title, sub, rows: rows.map(v => ({ n: v.name, v: show(get(v)), w: get(v) / max * 100, c: VARIANT_COLOR[v.key] })) };
  };
  return [
    chart('Инженеров задействовано', `из ${rows[0]?.engineers_total ?? 0}`, v => v.engineers_used, x => String(x)),
    chart('Пробег, км', 'сумма по всем', v => v.total_km, x => num(x, 0)),
    chart('Ожидаемые опоздания', 'за день', v => v.expected_late ?? 0, x => num(x))];
}

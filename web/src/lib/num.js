/** Числа на экране — по-русски: запятая, без хвостовых нулей. */
export function num(x, digits = 1) {
  if (x == null || Number.isNaN(x)) return '—';
  const k = 10 ** digits;
  return String(Math.round(x * k) / k).replace('.', ',');
}
export const signed = n => (n > 0 ? '+' : '') + num(n);
export const pct = x => `${Math.round(x * 100)} %`;
export function plural(n, [one, few, many]) {
  const d = n % 10, h = n % 100;
  return `${n} ${d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many}`;
}

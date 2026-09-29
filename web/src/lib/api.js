/** Запросы к серверу приложения. Путь — без /api. */
export class ApiError extends Error {
  constructor(status, message, errors = []) { super(message); this.status = status; this.errors = errors; }
}

export function errorText(data, status) {
  const d = data && data.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) return d.map(x => String(x.msg).replace(/^Value error, /, '')).join('; ');
  if (d && typeof d === 'object' && d.message) return d.message;
  return `сервер не ответил как ожидалось (${status})`;
}

export async function api(path, { method = 'GET', body } = {}) {
  const init = { method, headers: {} };
  if (body !== undefined) { init.headers = { 'content-type': 'application/json' }; init.body = JSON.stringify(body); }
  let res;
  try { res = await fetch('/api' + path, init); } catch { throw new ApiError(0, 'сервер недоступен — проверьте, что он запущен'); }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) throw new ApiError(res.status, errorText(data, res.status), data?.detail?.errors || []);
  return data;
}

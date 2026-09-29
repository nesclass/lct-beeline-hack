/** Адрес → экран. sid — 8 шестнадцатеричных знаков (app/store.new_id). */
const S = /^\/s\/([0-9a-f]+)(?:\/(setup|plan|engineers|requests|analytics)(?:\/(variants|map))?)?\/?$/;

/** Настройка и варианты — только до первого расписания: после утверждения день ведут
 *  перепланированием, а «начать заново» — это новый сценарий с главной. */
export const setupClosed = (r, session) =>
  (r.page === 'setup' || r.page === 'variants') && !!session?.plan_id && session.session_id === r.sid;

export function parse(path) {
  if (path === '' || path === '/') return { page: 'home' };
  const m = path.match(S);
  if (!m) return { page: 'notfound' };
  const [, sid, page = 'plan', sub = null] = m;
  if (sub === 'variants') return page === 'setup' ? { page: 'variants', sid, sub: null } : { page: 'notfound' };
  if (sub === 'map' && page !== 'plan') return { page: 'notfound' };
  return { page, sid, sub };
}

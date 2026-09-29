/** Текущий адрес и переход без перезагрузки. */
export const route = $state({ path: location.pathname, query: new URLSearchParams(location.search) });

export function go(path, { replace = false } = {}) {
  const [p, q = ''] = path.split('?');
  if (p === route.path && q === route.query.toString()) return;
  history[replace ? 'replaceState' : 'pushState'](null, '', path);
  route.path = p;
  route.query = new URLSearchParams(q);
  window.scrollTo(0, 0);
}

window.addEventListener('popstate', () => { route.path = location.pathname; route.query = new URLSearchParams(location.search); });

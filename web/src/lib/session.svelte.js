/** Стор открытой сессии. После каждой мутации перечитывается то, что она затронула.
 *  Мутации не бросают: ошибка — в error (её показывает шапка), результат — false/null. */
import { api, ApiError } from './api.js';
import { colorsFor } from './palette.js';
import { fmt, hm, clamp } from './time.js';
import { firstQuestion, restore, switchTo } from './assistantView.js';

const EMPTY_CHAT = () => ({ id: 0, context: null, label: '', messages: [], suggestions: [], history: [], past: [] });

class Session {
  sid = $state(null);
  session = $state(null);
  settings = $state(null);
  view = $state(null);
  engineers = $state([]);
  requests = $state([]);
  catalog = $state(null);
  missing = $state(false);
  busy = $state('');
  error = $state('');
  notice = $state('');
  panel = $state('default');
  selected = $state(null);
  assistant = $state(EMPTY_CHAT());
  modal = $state(null);
  impact = $state(null);
  chatSeq = 0; // счётчик id разговоров ассистента — не для рендера, обычное поле

  names = $derived(Object.fromEntries(this.engineers.map(e => [e.id, e.name])));
  colors = $derived(colorsFor(this.engineers.map(e => e.id)));

  path(tail = '') { return `/sessions/${this.sid}${tail}`; }

  async open(sid) {
    if (this.sid === sid) return;
    Object.assign(this, { sid, session: null, settings: null, view: null, engineers: [], requests: [], catalog: null,
                          missing: false, error: '', notice: '', panel: 'default', selected: null, impact: null });
    this.assistant = EMPTY_CHAT();
    try {
      await this.refresh();
      this.catalog = await api(this.path('/catalog'));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) this.missing = true; else this.error = e.message;
    }
  }

  async refresh() {
    this.session = await api(this.path());
    const [settings, view, engineers, requests] = await Promise.all([
      api(this.path('/settings')), this.session.plan_id ? api(this.path('/plan')) : null,
      api(this.path('/engineers')), api(this.path('/requests'))]);
    Object.assign(this, { settings, view, engineers, requests });
    await this.loadImpact();
  }

  async loadImpact() {
    this.impact = this.session.plan_id && this.session.pending_events.length ? await api(this.path('/impact')) : null;
  }

  async run(label, fn) {
    if (this.busy) return false;
    this.busy = label; this.error = ''; this.notice = '';
    try { const r = await fn(); return r === undefined ? true : r; }
    catch (e) { this.error = e.message; return false; }
    finally { this.busy = ''; }
  }

  saveSettings(st) { return this.run('Сохраняю…', async () => { this.settings = await api(this.path('/settings'), { method: 'PUT', body: st }); }); }

  setClock(time) {
    return this.run('Переставляю часы…', async () => { this.session = await api(this.path('/clock'), { method: 'PUT', body: { time } }); });
  }
  stepClock(delta) { return this.setClock(fmt(clamp(hm(this.session.clock) + delta, 0, 23 * 60 + 59))); }

  async buildVariants() {
    let out = null;
    await this.run('Считаю варианты…', async () => {
      await api(this.path('/settings'), { method: 'PUT', body: this.settings });
      out = await api(this.path('/variants'), { method: 'POST' });
    });
    return out;
  }
  approve(planId) { return this.run('Утверждаю…', async () => { await api(this.path(`/variants/${planId}/approve`), { method: 'POST' }); await this.refresh(); }); }

  async addRequest(body, replaceId = null) {
    let made = null;
    await this.run('Добавляю в изменения…', async () => {
      const q = replaceId ? `?replace=${replaceId}` : '';
      made = (await api(this.path(`/requests${q}`), { method: 'POST', body })).request;
      await this.refresh();
    });
    return made;
  }
  setAvailability(eid, body, replaceId = null) {
    return this.run('Добавляю в изменения…', async () => {
      const q = replaceId ? `?replace=${replaceId}` : '';
      await api(this.path(`/engineers/${eid}/unavailable${q}`), { method: 'POST', body });
      await this.refresh();
    });
  }
  cancelRequest(rid, reason = '') {
    return this.run('Добавляю в изменения…', async () => { await api(this.path(`/requests/${rid}/cancel`), { method: 'POST', body: { reason } }); await this.refresh(); });
  }
  moveRequest(rid, eid) {
    return this.run('Добавляю в изменения…', async () => { await api(this.path(`/requests/${rid}/move`), { method: 'POST', body: { engineer_id: eid } }); await this.refresh(); });
  }
  dropEvent(eventId) {
    return this.run('Убираю…', async () => { await api(this.path(`/events/${eventId}`), { method: 'DELETE' }); await this.refresh(); });
  }

  replan(mode = 'minimal') {
    return this.run(`Перепланирую от ${this.session.clock}…`, async () => {
      await api(this.path('/replan'), { method: 'POST', body: { mode } });
      await this.refresh();
      this.panel = 'diff';
    });
  }
  async accept() {
    let affected = null;
    await this.run('Принимаю…', async () => {
      affected = (await api(this.path('/plan/accept'), { method: 'POST' })).affected;
      await this.refresh();
      this.panel = 'default';
    });
    return affected;
  }
  rollback() {
    return this.run('Откатываю…', async () => { await api(this.path('/plan/rollback'), { method: 'POST' }); await this.refresh(); this.panel = 'changes'; });
  }

  select(rid) { this.selected = rid; this.panel = rid ? 'request' : 'default'; }
  openModal(m) { this.modal = m; }
  closeModal() { this.modal = null; }
  openPanel(name) { this.panel = name; }
  closePanel() { this.panel = 'default'; this.selected = null; }

  openAssistant(context) {
    const a = this.assistant;
    const next = switchTo(a, context);
    if (next !== a) { Object.assign(a, next); a.id = ++this.chatSeq; }
    this.panel = 'assistant';
    const q = firstQuestion(a.context);
    if (!a.messages.length && q) this.ask(q);
  }

  // «История» → клик по прошлому разговору: контекст и history возвращаются вместе с сообщениями,
  // текущий разговор архивируется под своим id (см. assistantView.restore).
  restoreConversation(i) {
    Object.assign(this.assistant, restore(this.assistant, i));
  }

  async ask(question) {
    const a = this.assistant;
    const id = a.id; // разговор мог смениться (или вернуться из past) до того, как придёт ответ
    a.messages.push({ role: 'user', text: question });
    const target = () => (a.id === id ? a : a.past.find(p => p.id === id));
    try {
      const r = await api(this.path('/assistant'), { method: 'POST', body: { context: a.context, question, history: a.history } });
      const t = target();
      if (t) {
        t.messages.push({ role: 'ai', text: r.text, tools: r.tools, rows: r.rows, action: r.action, source: r.source });
        Object.assign(t, { label: r.label, suggestions: r.suggestions, history: r.history });
      }
      return r;
    } catch (e) {
      const t = target();
      if (t) t.messages.push({ role: 'ai', text: e.message, tools: [], rows: [], action: null, source: 'error' });
      return null;
    }
  }
}

export const store = new Session();

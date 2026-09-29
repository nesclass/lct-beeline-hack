<script>
  /** Окно «Новое событие» — разметка backups/docs/design/DispatcherFlow.dc.html#4h.
   *  Три вкладки: срочная/обычная заявка, отмена заявки, инженер недоступен (→ задача 17).
   *  Правка события из очереди — store.modal.edit (см. lib/requestForm.js formFromRequest). */
  import { store } from '../lib/session.svelte.js';
  import { api } from '../lib/api.js';
  import { canCancel, cancellable, emptyForm, formFromRequest, toBody, validate } from '../lib/requestForm.js';
  import Modal from './Modal.svelte';
  import RequestForm from './RequestForm.svelte';

  const modal = store.modal;
  const edit = modal?.edit ?? null;

  function initialForm() {
    if (edit?.type === 'urgent_request') return formFromRequest(edit.request);
    if (edit?.type === 'new_request') {
      const r = store.requests.find(x => x.id === edit.request_id);
      if (r) return formFromRequest(r);
    }
    return emptyForm(store.session.clock_min, store.catalog);
  }

  // rid, преднастроенный ссылкой «отменить» из строки — только если её ещё можно отменить
  // (иначе, например, для уже завершённой, выбор снимается и кнопка остаётся недоступной).
  function initialSelected() {
    if (modal?.rid) {
      const r = store.requests.find(x => x.id === modal.rid);
      return r && canCancel(r, store.view, store.session.clock_min) ? modal.rid : null;
    }
    return edit?.request_id ?? null;
  }

  const TABS = [['urgent', '⚡ Срочная заявка'], ['cancel', 'Отмена заявки'], ['engineer', 'Инженер недоступен']];

  let activeTab = $state(edit?.type === 'cancel_request' ? 'cancel' : (modal?.tab ?? 'urgent'));
  let form = $state(initialForm());
  let selectedId = $state(initialSelected());
  let reason = $state(edit?.reason ?? '');
  let query = $state('');
  let preview = $state(null);

  const errors = $derived(validate(form, store.catalog));
  const cancellables = $derived(cancellable(store.requests, store.view, store.session.clock_min));
  const filtered = $derived(cancellables.filter(c => {
    const q = query.trim().toLowerCase();
    return !q || c.id.toLowerCase().includes(q) || c.sub.toLowerCase().includes(q);
  }));
  const disabled = $derived(
    activeTab === 'urgent' ? errors.length > 0 :
    activeTab === 'cancel' ? !selectedId : true);

  // 300 мс после последнего изменения формы — предпросмотр, кто успевает (POST /preview/request)
  $effect(() => {
    if (activeTab !== 'urgent' || errors.length) { preview = null; return; }
    const body = toBody(form, store.catalog);
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await api(store.path('/preview/request'), { method: 'POST', body });
        if (!cancelled) preview = r;
      } catch {
        if (!cancelled) preview = null;
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  });

  function pickEngineer(eid) {
    store.closeModal();
    store.openModal({ kind: 'availability', eid });
  }

  function finish() {
    const n = store.session?.pending_events?.length ?? 0;
    store.closeModal();
    store.notice = `Событие в очереди — «Изменения ${n}»`;
  }

  async function submit() {
    if (disabled) return;
    if (activeTab === 'urgent') {
      const made = await store.addRequest(toBody(form, store.catalog), edit?.id ?? null);
      if (made) finish();
    } else if (activeTab === 'cancel') {
      if (edit?.type === 'cancel_request' && !(await store.dropEvent(edit.id))) return;
      if (await store.cancelRequest(selectedId, reason)) finish();
    }
  }
</script>

<Modal title="Новое событие" onclose={() => store.closeModal()}>
  {#snippet children()}
    <div class="event-tabs">
      {#each TABS as [k, label] (k)}
        <button type="button" class="event-tab" class:on={activeTab === k} onclick={() => (activeTab = k)}>{label}</button>
      {/each}
    </div>

    {#if activeTab === 'urgent'}
      <RequestForm bind:form catalog={store.catalog} showPriority />
      {#if form.address.trim() && errors.length}
        <div class="event-errors">{errors.join('; ')}</div>
      {/if}
      {#if !errors.length && preview}
        {#if preview.candidates === null}
          <div class="preview-gray">План ещё не построен — исполнителя подберёт расчёт</div>
        {:else if preview.candidates.length === 0}
          <div class="preview-none">
            <span class="preview-none-title">Никто не успевает</span>
            <span>заявка останется без исполнителя до конца дня</span>
          </div>
        {:else}
          <div class="preview-ok">
            <span class="preview-ok-title">Успевают по навыку, окну и смене — {preview.candidates.length}</span>
            <div class="preview-ok-list">
              {#each preview.candidates.slice(0, 3) as c (c.engineer_id)}
                <span class="preview-cand"><span class="dot" style={`background:${store.colors[c.engineer_id]?.main ?? 'var(--idle)'}`}></span>{c.name}<span class="muted">с {c.start}</span></span>
              {/each}
            </div>
          </div>
        {/if}
      {/if}
    {:else if activeTab === 'cancel'}
      <input class="event-search" type="text" placeholder="Номер или адрес" bind:value={query} />
      <div class="event-list">
        {#each filtered as c (c.id)}
          <button type="button" class="event-row" class:on={selectedId === c.id} onclick={() => (selectedId = c.id)}>
            <span class="event-row-radio"><span></span></span>
            <span class="event-row-text"><span class="event-row-label">{c.label}</span><span class="event-row-sub">{c.sub}</span></span>
          </button>
        {:else}
          <div class="event-empty">Нет заявок, которые можно отменить</div>
        {/each}
      </div>
      <input class="event-reason" type="text" placeholder="Причина (необязательно)" bind:value={reason} />
    {:else}
      <div class="event-list">
        {#each store.engineers as e (e.id)}
          <button type="button" class="event-eng-row" onclick={() => pickEngineer(e.id)}>
            <span class="event-eng-dot" style={`background:${store.colors[e.id]?.main ?? 'var(--idle)'}`}></span>
            <span class="event-eng-name">{e.name}</span>
            <span class="event-eng-shift">{e.shift_start}–{e.shift_end}</span>
          </button>
        {/each}
      </div>
    {/if}
  {/snippet}
  {#snippet footer()}
    <span class="modal-foot-note">План не изменится, пока вы не нажмёте «Перепланировать»</span>
    <button type="button" class="btn gray" onclick={() => store.closeModal()}>Отмена</button>
    <button type="button" class="btn yellow submit-event" disabled={disabled} onclick={submit}>Добавить в изменения</button>
  {/snippet}
</Modal>

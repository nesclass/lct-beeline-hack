<script>
  /** Окно «Доступность инженера» — разметка backups/docs/design/DispatcherFlow.dc.html#4j.
   *  Четыре варианта, предпросмотр последствий (POST /preview/unavailable) через 300 мс.
   *  Панель ассистента справа (задача 20) — .modal-aside, пока открыта для этого инженера. */
  import { store } from '../lib/session.svelte.js';
  import { api } from '../lib/api.js';
  import { OPTIONS, initialState, quickTimes, summary, toBody } from '../lib/availability.js';
  import { queuedFor } from '../lib/engineers.js';
  import { hm } from '../lib/time.js';
  import Modal from './Modal.svelte';
  import Assistant from './Assistant.svelte';
  import TimeField from './TimeField.svelte';

  const modal = store.modal;
  const eid = modal.eid;
  const edit = modal.edit ?? queuedFor(eid, store.session.pending_events ?? []);
  const engineer = store.engineers.find(e => e.id === eid);
  const color = store.colors[eid] ?? { main: 'var(--idle)', tint: 'var(--line-3)' };

  function currentStop() {
    const rt = store.view?.plan.routes.find(r => r.engineer_id === eid);
    const clockMin = store.session.clock_min;
    return (rt?.stops || []).find(s => hm(s.start) <= clockMin && hm(s.finish) > clockMin) || null;
  }
  const current = currentStop();

  let state = $state(initialState(engineer, edit, store.session.clock, current));
  let preview = $state(null);

  const options = OPTIONS(`${engineer.shift_start}–${engineer.shift_end}`);
  const times = quickTimes(store.session.clock, current);
  const sum = $derived(preview ? summary(preview) : null);

  function clampLeave(v) { return hm(v) < hm(store.session.clock) ? store.session.clock : v; }
  function pickTime(v) { state.time = clampLeave(v); }

  // Предпросмотр — 300 мс после изменения; для «по графику» не запрашивается (toBody -> null).
  $effect(() => {
    const b = toBody(state);
    if (!b) { preview = null; return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await api(store.path(`/preview/unavailable/${eid}`), { method: 'POST', body: b });
        if (!cancelled) preview = r;
      } catch {
        if (!cancelled) preview = null;
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  });

  const inAssistant = $derived(store.panel === 'assistant' && store.assistant.context?.kind === 'engineer' && store.assistant.context?.id === eid);

  function askAssistant() { store.openAssistant({ kind: 'engineer', id: eid, params: toBody(state) }); }

  // пока ассистент открыт по этому инженеру — следующий вопрос учитывает свежие параметры окна.
  $effect(() => { if (inAssistant) store.assistant.context.params = toBody(state); });

  async function submit() {
    const b = toBody(state);
    if (b === null) {
      if (edit && !(await store.dropEvent(edit.id))) return;
      store.closeModal();
      return;
    }
    if (await store.setAvailability(eid, b, edit?.id ?? null)) store.closeModal();
  }
</script>

<Modal title={`Доступность · ${engineer.name}`} onclose={() => store.closeModal()} width={640}>
  {#snippet children()}
    <div class="avail-head">
      <span class="avail-avatar" style={`background:${color.main}`}>{engineer.name.slice(0, 2).toUpperCase()}</span>
      <span class="avail-sub">по графику {engineer.shift_start}–{engineer.shift_end}</span>
    </div>
    <!-- четыре варианта — одной строкой (раньше четыре карточки: окно не помещалось в экран и
         последствия уходили под прокрутку); детали выбранного — одной карточкой ниже -->
    <div class="avail-modes" role="radiogroup" aria-label="Доступность">
      {#each options as o (o.key)}
        <button type="button" role="radio" aria-checked={state.mode === o.key} class:on={state.mode === o.key}
                onclick={() => (state.mode = o.key)}>{o.t}</button>
      {/each}
    </div>
    {#if state.mode === 'schedule'}
      <div class="avail-card"><span class="avail-note">Работает как обычно: {engineer.shift_start}–{engineer.shift_end}. Изменений в плане не будет.</span></div>
    {:else if state.mode === 'leave'}
      <div class="avail-card">
            <div class="avail-detail">
              <div class="avail-row">
                <span class="avail-row-label">Уйдёт в</span>
                <TimeField name="leave" label="Уйдёт в" value={state.time} min={store.session.clock} onchange={v => (state.time = v)} />
                {#each times as tm (tm.v)}
                  <button type="button" class="avail-chip" class:on={state.time === clampLeave(tm.v)} aria-pressed={state.time === clampLeave(tm.v)}
                          onclick={() => pickTime(tm.v)}>{#if state.time === clampLeave(tm.v)}<span aria-hidden="true">✓ </span>{/if}{tm.t}</button>
                {/each}
              </div>
              {#if current}
                <div class="avail-row">
                  <span class="avail-row-label">{current.request_id}</span>
                  <span class="avail-seg">
                    <button type="button" class:on={state.finish_current} onclick={() => (state.finish_current = true)}>доделает до {current.finish}</button>
                    <button type="button" class:on={!state.finish_current} onclick={() => (state.finish_current = false)}>вернуть в пул</button>
                  </span>
                </div>
              {/if}
              <label class="avail-reason"><span>Причина <span class="muted">— необязательно</span></span>
                <input type="text" name="reason" maxlength="200" placeholder="например: заболел, сломалась машина" bind:value={state.reason} /></label>
            </div>
      </div>
    {:else if state.mode === 'break'}
      <div class="avail-card"><span class="avail-note">Вернётся в указанное время и продолжит маршрут.</span>
            <div class="avail-detail">
              <div class="avail-row">
                <span class="avail-row-label">с</span><TimeField name="break-from" label="Перерыв с" value={state.time} min={store.session.clock} onchange={v => (state.time = v)} />
                <span class="avail-row-label short">до</span><TimeField name="break-until" label="Перерыв до" value={state.until} min={state.time} onchange={v => (state.until = v)} />
              </div>
              <label class="avail-reason"><span>Причина <span class="muted">— необязательно</span></span>
                <input type="text" name="reason" maxlength="200" placeholder="например: заболел, сломалась машина" bind:value={state.reason} /></label>
            </div>
      </div>
    {:else}
      <div class="avail-card"><span class="avail-note">Весь день — все его заявки вернутся в пул.</span>
            <div class="avail-detail">
              <label class="avail-reason"><span>Причина <span class="muted">— необязательно</span></span>
                <input type="text" name="reason" maxlength="200" placeholder="например: заболел, сломалась машина" bind:value={state.reason} /></label>
            </div>
      </div>
    {/if}
    {#if sum}
      <div class="consequences">
        <div class="cons-head"><span class="cons-title">{sum.title}</span><span class="cons-can">{sum.can}</span></div>
        {#each preview.released as r (r.request_id)}
          <div class="cons-row">
            <span class="cons-id">{r.request_id}</span><span class="cons-win">{r.window}</span>
            {#if r.taker}
              <span class="cons-taker ok"><span class="dot"></span>возьмёт {r.taker.name}{#if r.taker.start}<span class="cons-at">· с {r.taker.start}</span>{/if}</span>
            {:else}
              <span class="cons-taker bad"><span class="dot"></span>свободного инженера нет</span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/snippet}
  {#snippet footer()}
    <button type="button" class="ask-consequences" onclick={askAssistant}>✦ Спросить ассистента о последствиях</button>
    <button type="button" class="btn gray" onclick={() => store.closeModal()}>Отмена</button>
    <button type="button" class="btn yellow submit-availability" onclick={submit}>Добавить в изменения</button>
  {/snippet}
  {#snippet aside()}
    {#if inAssistant}<div class="modal-aside"><Assistant /></div>{/if}
  {/snippet}
</Modal>

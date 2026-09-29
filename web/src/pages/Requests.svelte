<script>
  /** 1f «Заявки» — список с состоянием, причины неназначения, поиск, новая заявка.
   *  Раскладка backups/docs/design/Dispatcher Wireframes.dc.html#1f, оформление — токены серии 4. */
  import Shell from '../components/Shell.svelte';
  import RequestForm from '../components/RequestForm.svelte';
  import { store } from '../lib/session.svelte.js';
  import { go } from '../lib/router.svelte.js';
  import { canCancel, emptyForm, toBody, validate } from '../lib/requestForm.js';
  import { SKILL_SHORT } from '../lib/labels.js';
  import { FILTERS, counts, executor, filterRows, reasonCard, stateOf, streetOf } from '../lib/requestsView.js';

  let filter = $state('all');
  let query = $state('');
  let form = $state(null);

  const v = $derived(store.view);
  const cnt = $derived(counts(store.requests, v));
  const rows = $derived(filterRows(store.requests, v, filter, query));
  const errors = $derived(form ? validate(form, store.catalog) : []);

  $effect(() => { if (store.catalog && !form) form = emptyForm(store.session.clock_min, store.catalog, false); });

  function openCard(r) {
    store.select(r.id);
    go(`/s/${store.sid}/plan`);
  }

  async function submit() {
    if (!form || errors.length) return;
    const made = await store.addRequest(toBody(form, store.catalog));
    if (made) {
      form = emptyForm(store.session.clock_min, store.catalog, false);
      store.notice = `Заявка ${made.id} в изменениях`;
    }
  }
</script>

{#snippet topBar()}
  <div class="req-top">
    <div class="filters">
      {#each FILTERS as [key, label] (key)}
        <button type="button" class:on={filter === key} onclick={() => (filter = key)}>{label} {cnt[key]}</button>
      {/each}
    </div>
    <input class="req-search" type="text" placeholder="Поиск по адресу или номеру" bind:value={query} />
  </div>
{/snippet}

<Shell page="requests" top={topBar}>
  {#snippet main()}
    <div class="card req-table tbl-wrap">
      <div class="req-head">
        <span>№</span><span>Адрес</span><span>Тип</span><span>Окно</span><span>Навык</span><span>Исполнитель</span><span>Состояние</span>
      </div>
      {#each rows as r (r.id)}
        {@const st = stateOf(r, v)}
        {@const exec = executor(r, v, store.names)}
        {@const card = reasonCard(r, v, store.names)}
        <div class="req-row" class:has-reason={card}>
          <span class="req-id">
            {#if r.status === 'assigned'}
              <button type="button" class="req-id-num" onclick={() => openCard(r)}>{r.id}</button>
            {:else}
              <span class="req-id-num">{r.id}</span>
            {/if}
            {#if canCancel(r, v, store.session.clock_min)}
              <button type="button" class="req-cancel" onclick={() => store.openModal({ kind: 'event', tab: 'cancel', rid: r.id })}>отменить</button>
            {/if}
          </span>
          <span class="req-addr">
            <span>{streetOf(r)}</span>
            <span class="req-addr-district">{r.district}</span>
          </span>
          <span>{r.type}{r.priority === 'urgent' ? ' · срочная' : ''}</span>
          <span>{r.tw_start}–{r.tw_end}</span>
          <span>{SKILL_SHORT[r.skill] || r.skill}</span>
          <span>{exec}</span>
          <span class={`pill ${st.tone}`}>{st.text}</span>
        </div>
        {#if card}
          <div class="req-reason">
            <span class="req-reason-title">{card.title}</span>
            <span class="req-reason-text">{card.text}</span>
            <span class="req-reason-chips">{#each card.chips as c (c)}<span class="req-reason-chip">{c}</span>{/each}</span>
          </div>
        {/if}
      {:else}
        <div class="side-card-empty">Заявок нет</div>
      {/each}
    </div>
  {/snippet}
  {#snippet side()}
    <div class="card req-new">
      <span class="req-new-title">Новая заявка</span>
      {#if form}
        <RequestForm bind:form catalog={store.catalog} showPriority />
        {#if form.address.trim() && errors.length}
          <div class="err req-new-errors">{errors.join('; ')}</div>
        {/if}
      {/if}
      <button type="button" class="btn ink req-new-submit" disabled={!form || errors.length > 0} onclick={submit}>Добавить заявку</button>
      <span class="req-new-note muted">Заявка попадёт в план после «Перепланировать». Срочная может сдвинуть обычные в пределах их окон.</span>
    </div>
  {/snippet}
</Shell>

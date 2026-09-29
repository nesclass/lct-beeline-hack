<script>
  /** Шапка — разметка backups/docs/design/FlowHeader.dc.html. Часы, изменения, перепланирование и ассистент читают/пишут store. */
  import { store } from '../lib/session.svelte.js';
  import { go } from '../lib/router.svelte.js';
  import Link from './Link.svelte';

  let { page = '', context = { kind: 'plan' }, minimal = false } = $props();

  const TABS = [['setup', 'Настройка'], ['plan', 'План'], ['engineers', 'Инженеры'], ['requests', 'Заявки'], ['analytics', 'Аналитика']];

  const sid = $derived(store.sid);
  const s = $derived(store.session);
  const activeTab = $derived(page === 'variants' ? 'setup' : page);
  const havePlan = $derived(!!s?.plan_id);
  const pending = $derived(s?.pending_events?.length ?? 0);
  const dirty = $derived(s?.status === 'dirty');

  // «Переставляю часы…» и т.п.: быстрые действия проходят без мигания, долгие — плашкой поверх
  // страницы, не сдвигая её (раньше полоса на долю секунды толкала всё вниз)
  let busyShown = $state(false);
  $effect(() => {
    if (!store.busy) { busyShown = false; return; }
    const t = setTimeout(() => (busyShown = true), 400);
    return () => clearTimeout(t);
  });

  let editingClock = $state(false);
  let clockDraft = $state('');
  let clockInput = $state(null);
  let skipCommit = false;

  $effect(() => { if (editingClock) clockInput?.focus(); });

  function startEdit() {
    if (!s) return;
    clockDraft = s.clock;
    skipCommit = false;
    editingClock = true;
  }
  function onClockKey(e) {
    if (e.key === 'Enter') e.currentTarget.blur();
    else if (e.key === 'Escape') { skipCommit = true; e.currentTarget.blur(); }
  }
  async function onClockBlur() {
    editingClock = false;
    if (skipCommit) { skipCommit = false; return; }
    await store.setClock(clockDraft);
  }

  function onQueue() { store.openPanel('changes'); go(`/s/${sid}/plan`); }
  async function onReplan() {
    if (!dirty) return;
    await store.replan('minimal');
    go(`/s/${sid}/plan`);
  }
  function onAssistant() { if (store.panel === 'assistant') store.closePanel(); else store.openAssistant(context); }
</script>

<div class="header">
  <Link href="/" class="brand" aria-label="билайн бизнес"><img src="/beeblik.png" alt="" width="30" height="30" />
    <span class="brand-word" aria-hidden="true"><b>билайн</b> бизнес</span></Link>
  {#if !minimal}
    <span class="header-sep"></span>
    <Link href="/" class="scenario">
      <span class="scenario-dot"></span>
      <span class="scenario-name">{s?.title ?? ''}</span>
      <span class="scenario-car">▾</span>
    </Link>
    <div class="tabs">
      {#each TABS.filter(([k]) => k !== 'setup' || !havePlan) as [k, label] (k)}
        {@const active = k === activeTab}
        {@const off = !havePlan && (k === 'plan' || k === 'analytics')}
        <Link href={`/s/${sid}/${k}`} disabled={off} class={`${active ? 'active' : ''} ${off ? 'off' : ''}`}>{label}</Link>
      {/each}
    </div>
    <div class="header-spacer"></div>
    <div class="header-tools">
      <div class="clock">
        <button type="button" aria-label="На 15 минут назад" onclick={() => store.stepClock(-15)}>‹</button>
        {#if editingClock}
          <input class="clock-value" type="time" step="300" aria-label="Часы сессии" bind:value={clockDraft} bind:this={clockInput}
            onkeydown={onClockKey} onblur={onClockBlur} />
        {:else}
          <button type="button" class="clock-value" onclick={startEdit}>{s?.clock ?? ''}</button>
        {/if}
        <button type="button" aria-label="На 15 минут вперёд" onclick={() => store.stepClock(15)}>›</button>
      </div>
      <button type="button" class="add-event" onclick={() => store.openModal({ kind: 'event', tab: 'urgent' })}>+ Событие</button>
      <button type="button" class="queue" class:dirty={pending > 0} onclick={onQueue} title="Изменения" aria-label={`Изменения: ${pending}`}>
        <span class="btn-label">Изменения</span><span class="badge">{pending}</span></button>
      <button type="button" class="replan" class:active={dirty} disabled={!dirty} onclick={onReplan}>Перепланировать</button>
      <button type="button" class="assistant" class:active={store.panel === 'assistant'} onclick={onAssistant} title="Ассистент" aria-label="Ассистент">
        <span class="assistant-icon">✦</span><span class="btn-label">Ассистент</span></button>
    </div>
  {/if}
</div>
{#if busyShown}<div class="busy-pill" role="status">{store.busy}</div>{/if}
{#if store.error}<div class="band err" role="alert">{store.error}<button onclick={() => (store.error = '')} aria-label="Скрыть">×</button></div>{/if}
{#if store.notice}<div class="band ok" role="status">{store.notice}<button onclick={() => (store.notice = '')} aria-label="Скрыть">×</button></div>{/if}

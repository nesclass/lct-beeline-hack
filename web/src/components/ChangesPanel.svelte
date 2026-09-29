<script>
  /** 4k «Изменения» — очередь событий, «если оставить как есть», выбор режима пересчёта.
   *  Разметка — правая колонка backups/docs/design/DispatcherFlow.dc.html#4k. */
  import { store } from '../lib/session.svelte.js';
  import { eventRows, forecast } from '../lib/changes.js';
  import Link from './Link.svelte';

  let mode = $state('minimal');
  let replanning = $state(false);

  const pending = $derived(store.session?.pending_events || []);
  const rows = $derived(eventRows(pending, store.names, store.requests, store.engineers));
  const fc = $derived(store.impact ? forecast(store.impact) : []);
  const hasPlan = $derived(!!store.session?.plan_id);
  // черновик перепланирования не принят — из очереди можно вернуться к его разбору
  const draft = $derived(!!store.view?.plan?.replan_of && !store.view.plan.accepted);

  function edit(row) {
    const e = row.edit;
    if (e.kind === 'request') store.select(e.rid);
    else if (e.kind === 'availability') store.openModal({ kind: 'availability', eid: e.eid, edit: e.ev });
    else store.openModal({ kind: 'event', tab: e.tab, edit: e.ev });
  }

  async function doReplan() {
    replanning = true;
    try { await store.replan(mode); } finally { replanning = false; }
  }
</script>

<div class="changes-panel side-card">
  <div class="changes-head">
    <span class="changes-title">Изменения</span>
    {#if rows.length}<span class="changes-count">{rows.length}</span>{/if}
    <span style="flex:1"></span>
    {#if store.impact}<span class="changes-since">с {store.impact.since}</span>{/if}
  </div>
  {#if draft}
    <div class="changes-back">
      <span>Перепланирование ещё не принято</span>
      <button type="button" class="btn outline sm" style="background:var(--card);flex:none" onclick={() => store.openPanel('diff')}>К разбору изменений</button>
    </div>
  {/if}
  {#if !rows.length}
    <div class="side-card-empty">Изменений нет. Добавьте событие кнопкой «+ Событие».</div>
  {:else}
    {#each rows as row (row.id)}
      <div class="change-row">
        <span class="change-ic" style={`background:${row.icBg};color:${row.icColor}`}>{row.ic}</span>
        <div class="change-body">
          <span class="change-title">{row.title}</span>
          <span class="change-desc">{row.desc}</span>
        </div>
        <button type="button" class="change-edit" onclick={() => edit(row)}>изменить</button>
        <button type="button" class="change-drop" aria-label={`Убрать событие ${row.id}`} onclick={() => store.dropEvent(row.id)}>×</button>
      </div>
    {/each}
    {#if !hasPlan}
      <div class="changes-noplan">
        <span>Плана ещё нет — изменения учтутся при построении</span>
        <Link href={`/s/${store.sid}/setup`} class="btn yellow sm">К настройке</Link>
      </div>
    {:else}
      <div class="changes-forecast">
        <span class="changes-forecast-title">Если оставить план как есть</span>
        {#each fc as f (f.t)}
          <div class="forecast-row"><span>{f.t}</span><span style={`font-weight:700;color:${f.c}`}>{f.n}</span></div>
        {/each}
      </div>
      <div class="changes-modes">
        <span class="changes-modes-title">Как пересчитать</span>
        <div class="mode-list">
          <button type="button" class={`mode-row ${mode === 'minimal' ? 'on' : ''}`} aria-pressed={mode === 'minimal'} onclick={() => (mode = 'minimal')}>
            <span class="mode-radio"><span class="mode-dot"></span></span>
            <span class="mode-text"><span class="mode-name">Минимум перестановок</span><span class="mode-desc">трогаем только затронутые маршруты</span></span>
          </button>
          <button type="button" class={`mode-row ${mode === 'full' ? 'on' : ''}`} aria-pressed={mode === 'full'} onclick={() => (mode = 'full')}>
            <span class="mode-radio"><span class="mode-dot"></span></span>
            <span class="mode-text"><span class="mode-name">Полный пересчёт</span><span class="mode-desc">лучше метрики, больше звонков инженерам</span></span>
          </button>
        </div>
      </div>
      <div class="changes-replan-wrap">
        <button type="button" class="btn yellow replan-now" disabled={!!store.busy} onclick={doReplan}>
          {replanning ? `Пересчитываю от ${store.session.clock}…` : `Перепланировать от ${store.session.clock}`}
        </button>
      </div>
    {/if}
  {/if}
</div>

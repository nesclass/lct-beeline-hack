<script>
  /** 4i «Инженеры» — таблица и карточка выбранного. Разметка backups/docs/design/DispatcherFlow.dc.html#4i. */
  import Shell from '../components/Shell.svelte';
  import EngineerCard from '../components/EngineerCard.svelte';
  import { store } from '../lib/session.svelte.js';
  import { engineerRows } from '../lib/engineers.js';

  let sel = $state(null);
  $effect(() => { if (sel === null && store.engineers.length) sel = store.engineers[0].id; });

  const pending = $derived(store.session?.pending_events ?? []);
  const rows = $derived(engineerRows(store.engineers, store.view, store.colors, store.session?.clock_min ?? 0, pending));
  const ctx = $derived(sel ? { kind: 'engineer', id: sel } : { kind: 'plan' });
  // как клик по заявке на диаграмме (store.select): выбор инженера показывает его карточку,
  // даже если справа был открыт ассистент — иначе клик по строке ничего не меняет на экране.
  function pick(eid) {
    sel = eid;
    if (store.panel === 'assistant') store.openPanel('default');
  }
</script>

<Shell page="engineers" context={ctx}>
  {#snippet main()}
    <div class="card eng-table">
      <div class="eng-head">
        <span>Инженер</span><span>Транспорт</span><span>Смена</span><span>Навыки</span>
        <span style="text-align:right">Заявок</span><span style="text-align:right">Км</span><span>Загрузка</span>
      </div>
      {#each rows as r (r.eid)}
        <button type="button" class="eng-row" class:sel={sel === r.eid} onclick={() => pick(r.eid)}>
          <span class="eng-who">
            <span class="eng-avatar" style={`background:${r.tint};color:${r.c}`}>{r.ini}</span>
            <span class="eng-info">
              <span class="eng-name">{r.name}</span>
              <span class="eng-state" style={`color:${r.stColor}`}>{r.st}</span>
            </span>
          </span>
          <span class="eng-tr">{r.tr}</span>
          <span class="eng-shift">{r.shift}</span>
          <span class="eng-skills">
            {#each r.skills as s, i (i)}<span class="eng-skill" style={`background:${s.bg};color:${s.c}`}>{s.t}</span>{/each}
          </span>
          <span class="eng-n">{r.n}</span>
          <span class="eng-km">{r.km}</span>
          <span class="eng-load">
            <span class="eng-load-bar"><span class="eng-load-fill" style={`width:${r.load}%;background:${r.c}`}></span></span>
            <span class="eng-load-pct">{r.load}%</span>
          </span>
        </button>
      {/each}
    </div>
  {/snippet}
  {#snippet side()}
    {#if sel}
      <EngineerCard eid={sel} onclose={() => (sel = null)} />
    {/if}
  {/snippet}
</Shell>

<script>
  /** 4d «План» — плитки, фильтры, диаграмма; справа «Не назначены» и «Мало запаса».
   *  Разметка backups/docs/design/DispatcherFlow.dc.html#4d. */
  import Shell from '../components/Shell.svelte';
  import Gantt from '../components/Gantt.svelte';
  import RouteMap from '../components/RouteMap.svelte';
  import KpiTiles from '../components/KpiTiles.svelte';
  import UnassignedCard from '../components/UnassignedCard.svelte';
  import TightCard from '../components/TightCard.svelte';
  import RequestCard from '../components/RequestCard.svelte';
  import ChangesPanel from '../components/ChangesPanel.svelte';
  import DiffPanel from '../components/DiffPanel.svelte';
  import Link from '../components/Link.svelte';
  import { store } from '../lib/session.svelte.js';
  import { kpis, tightList, unassignedList } from '../lib/plan.js';
  import { leavingOf } from '../lib/changes.js';
  import { banner as bannerOf } from '../lib/diffView.js';
  import { VERSIONS, beforeView, defaultVersion, hasVersions } from '../lib/gantt.js';

  let { sub = null } = $props();
  let only = $state(''), riskOnly = $state(false);
  const v = $derived(store.view);
  const base = $derived(`/s/${store.sid}/plan`);
  const ctx = $derived(store.selected ? { kind: 'request', id: store.selected } : { kind: 'plan' });
  // черновик — непринятый результат «Перепланировать»: разбор (4l) вместо обычной панели/режима
  const draft = $derived(!!v?.plan.replan_of && !v.plan.accepted);
  const diffOpen = $derived(draft && ['diff', 'default'].includes(store.panel));
  // «До / После / Изменения»: выбор живёт, пока не сменился план; по умолчанию черновик — разбор, принятый — «После»
  let pick = $state({ pid: null, k: null });
  const versions = $derived(hasVersions(v));
  const shown = $derived(!versions ? 'after' : pick.pid === v.plan.plan_id && pick.k ? pick.k : defaultVersion(v));
  const queue = $derived(store.panel === 'changes' && (store.session?.pending_events?.length ?? 0) > 0);
  const ganttMode = $derived(queue ? 'queue' : shown === 'diff' ? 'diff' : 'plan');
  const ganttView = $derived(!queue && shown === 'before' ? beforeView(v) : v);
  const bannerInfo = $derived(draft ? bannerOf(v.plan) : null);
</script>

{#snippet diffBanner()}
  <div class="diff-banner">
    <span class="diff-banner-check" aria-hidden="true">✓</span>
    <span class="diff-banner-title">{bannerInfo.title}</span>
    <span class="diff-banner-sub">{bannerInfo.sub}</span>
  </div>
{/snippet}

{#snippet topBar()}
  <div class="plan-bar">
    <span class="seg2"><Link href={base} aria-current={sub !== 'map' ? 'page' : undefined}>Диаграмма</Link>
      <Link href={`${base}/map`} aria-current={sub === 'map' ? 'page' : undefined}>Карта</Link></span>
    {#if sub !== 'map' && versions && !queue}
      <span class="seg2" role="group" aria-label="Какой план показать">
        {#each VERSIONS as o (o.k)}
          <button type="button" aria-pressed={shown === o.k} onclick={() => (pick = { pid: v.plan.plan_id, k: o.k })}>{o.t}</button>
        {/each}
      </span>
    {/if}
    {#if sub !== 'map'}
      <span class="chipbtn chip-select">
        <select bind:value={only} aria-label="Инженер">
          <option value="">Все инженеры</option>
          {#each v.plan.routes as rt (rt.engineer_id)}<option value={rt.engineer_id}>{rt.name}</option>{/each}
        </select><span aria-hidden="true">▾</span>
      </span>
      <button type="button" class="chipbtn" aria-pressed={riskOnly} onclick={() => (riskOnly = !riskOnly)}>Только с риском</button>
    {/if}
    <span style="flex:1"></span>
    <KpiTiles items={kpis(ganttView)} />
  </div>
{/snippet}

{#snippet sidePanel()}
  <!-- SIDE: задачи 18–20 добавляют панели по store.panel; «changes» доступна и без плана (события до его сборки) -->
  {#if store.panel === 'changes'}
    <ChangesPanel />
  {:else if v}
    {#if store.panel === 'request' && store.selected}
      <RequestCard rid={store.selected} />
    {:else if diffOpen}
      <DiffPanel />
    {:else}
      <UnassignedCard items={unassignedList(v)} />
      <TightCard items={tightList(v, store.colors)} />
    {/if}
  {/if}
{/snippet}

<Shell page="plan" context={ctx} top={v && sub !== 'map' ? topBar : undefined} banner={draft ? diffBanner : undefined}
       side={(v || store.panel === 'changes') && sub !== 'map' ? sidePanel : undefined}>
  {#snippet main()}
    {#if !v}
      <div class="card" style="padding:40px 24px;text-align:center">Расписания ещё нет.
        <Link href={`/s/${store.sid}/setup`} style="font-weight:600;text-decoration:underline">Построить</Link></div>
    {:else if sub === 'map'}
      <RouteMap view={v} />
    {:else}
      <!-- GANTT-MODE: задачи 18–19 выбирают режим по store.panel -->
      <Gantt view={ganttView} mode={ganttMode} selected={store.selected} {riskOnly} only={only || null}
             orphaned={ganttMode === 'queue' ? new Set(store.impact?.orphaned || []) : undefined}
             leaving={ganttMode === 'queue' ? leavingOf(store.session?.pending_events || [], store.engineers) : undefined}
             onselect={rid => store.select(rid)} />
    {/if}
  {/snippet}
</Shell>

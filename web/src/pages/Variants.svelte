<script>
  /** 4c «Варианты плана» — сравнение с базовым, утверждение.
   *  Разметка backups/docs/design/DispatcherFlow.dc.html#4c. */
  import { onMount } from 'svelte';
  import { api, ApiError } from '../lib/api.js';
  import { num } from '../lib/num.js';
  import { store } from '../lib/session.svelte.js';
  import { go } from '../lib/router.svelte.js';
  import { compareCharts, variantRows } from '../lib/variants.js';
  import Shell from '../components/Shell.svelte';
  import Link from '../components/Link.svelte';
  import Insight from '../components/Insight.svelte';

  const THRESHOLD = 0.5;

  let result = $state(null);
  let missing = $state(false);
  let error = $state('');
  let selected = $state(null);

  onMount(load);
  async function load() {
    error = '';
    missing = false;
    try {
      result = await api(store.path('/variants'));
      selected = result.recommended;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) missing = true; else error = e.message;
    }
  }

  const rows = $derived(result ? variantRows(result.variants, result.recommended, selected, THRESHOLD) : []);
  const charts = $derived(result ? compareCharts(result.variants) : []);
  const chosen = $derived(rows.find(r => r.on));

  async function onApprove() {
    if (!chosen) return;
    if (await store.approve(chosen.plan_id)) go(`/s/${store.sid}/plan`);
  }
</script>

<Shell page="setup" context={{ kind: 'variants' }}>
  {#snippet main()}
    {#if missing}
      <div class="card" style="padding:40px 24px;text-align:center">
        <Link href={`/s/${store.sid}/setup`} style="font-weight:600;text-decoration:underline">Сначала постройте варианты</Link>
      </div>
    {:else if error}
      <div class="band err">{error}</div>
    {:else if result}
      <div class="card" style="overflow:hidden">
        <div style="display:flex;align-items:baseline;gap:12px;padding:20px 20px 12px">
          <span style="font-size:22px;font-weight:700">Варианты плана</span>
          {#if result.elapsed_s != null}<span style="font-size:13px;color:var(--ink-3)">посчитано за {num(result.elapsed_s)} с</span>{/if}
        </div>
        <div class="variant-head">
          <span>Вариант</span><span style="text-align:right">Назначено</span><span style="text-align:right">Инженеров</span>
          <span style="text-align:right">Пробег, км</span><span style="text-align:right">Ожид. опозданий</span><span style="text-align:right">Переработка</span>
        </div>
        {#each rows as v (v.key)}
          <button type="button" class="variant-row" class:on={v.on} onclick={() => (selected = v.key)}>
            <span style="display:flex;align-items:center;gap:10px;min-width:0">
              <span class="variant-radio"><span class="variant-dot"></span></span>
              <span style={`width:12px;height:12px;border-radius:4px;background:${v.color};flex:none`}></span>
              <span style="display:flex;flex-direction:column;text-align:left;min-width:0">
                <span style="font-weight:700">{v.name}</span><span style="font-size:12px;color:var(--muted)">{v.desc}</span>
              </span>
              {#if v.rec}<span class="pill ok" style="font-size:11px">рекомендуем</span>{/if}
            </span>
            <span style="text-align:right">{v.asg}</span>
            <span style="text-align:right;font-weight:700">{v.eng}</span>
            <span style="text-align:right;font-weight:700">{v.km}</span>
            <span style={`text-align:right;font-weight:600;${v.lateBad ? 'color:var(--red-ink);font-weight:700' : ''}`}>{v.late}</span>
            <span style="text-align:right">{v.over}</span>
          </button>
        {/each}
        <div style="padding:16px 20px">
          <Insight text={result.text} onDiscuss={() => store.openAssistant({ kind: 'variants' })} />
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;padding:0 20px 20px">
          <Link href={`/s/${store.sid}/setup`} class="btn gray">Изменить настройки</Link>
          <button type="button" class="btn yellow approve" disabled={!chosen} onclick={onApprove}>Утвердить «{chosen?.name ?? ''}»</button>
        </div>
      </div>
    {/if}
  {/snippet}
  {#snippet side()}
    {#if result}
      {#each charts as ch (ch.title)}
        <div class="card" style="padding:18px 20px;display:flex;flex-direction:column;gap:12px">
          <div style="display:flex;justify-content:space-between;align-items:baseline">
            <span style="font-size:15px;font-weight:700">{ch.title}</span><span style="font-size:12px;color:var(--muted)">{ch.sub}</span>
          </div>
          {#each ch.rows as r}
            <div style="display:grid;grid-template-columns:130px minmax(0,1fr) 44px;gap:10px;align-items:center;font-size:13px">
              <span style="color:var(--ink-2)">{r.n}</span>
              <div class="compare-bar"><div class="compare-bar-fill" style={`width:${r.w}%;background:${r.c}`}></div></div>
              <span style="text-align:right;font-weight:700">{r.v}</span>
            </div>
          {/each}
        </div>
      {/each}
    {/if}
  {/snippet}
</Shell>

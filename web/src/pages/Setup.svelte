<script>
  /** 4b «Как строить план» — настройка расчёта, запуск построения вариантов.
   *  Разметка backups/docs/design/DispatcherFlow.dc.html#4b. */
  import { onDestroy } from 'svelte';
  import { store } from '../lib/session.svelte.js';
  import { go } from '../lib/router.svelte.js';
  import { GOALS, MARGIN_TITLE, applyMargin, marginLine, marginOf, sessionMix } from '../lib/setup.js';
  import { shortDate } from '../lib/time.js';
  import Shell from '../components/Shell.svelte';
  import Link from '../components/Link.svelte';

  const settings = $derived(store.settings);
  const mix = $derived(sessionMix(store.requests, store.engineers));
  const custom = $derived(settings ? marginOf(settings) === 'custom' : false);
  const replanned = $derived(!!store.view?.plan?.replan_of);
  // первая работа дня уже началась — план на весь день переписал бы сделанное
  const started = $derived(!!store.session?.day_started);

  let building = $state(false);
  let elapsed = $state(0);
  let timer = null;

  async function build() {
    if (building || !settings) return;
    building = true;
    elapsed = 0;
    timer = setInterval(() => { elapsed += 0.2; }, 200);
    const ok = await store.buildVariants();
    clearInterval(timer);
    timer = null;
    building = false;
    if (ok) go(`/s/${store.sid}/setup/variants`);
  }
  onDestroy(() => { if (timer) clearInterval(timer); });
</script>

<Shell page="setup" context={{ kind: 'variants' }}>
  {#snippet main()}
    {#if settings}
      <div class="card" style="padding:24px;display:flex;flex-direction:column;gap:24px">
        <span style="font-size:28px;font-weight:700">Как строить план</span>

        <div style="display:flex;flex-direction:column;gap:10px">
          <span style="font-size:14px;font-weight:600">Что важнее</span>
          <div class="goals">
            {#each GOALS as g (g.key)}
              <button type="button" class={`goal ${settings.priority === g.key ? 'on' : ''}`}
                onclick={() => (settings.priority = g.key)}>
                <span style="display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700">
                  <span class="goal-radio"><span class="goal-dot"></span></span>{g.t}
                </span>
                <span style="font-size:12px;color:var(--ink-3);padding-left:24px">{g.d}</span>
              </button>
            {/each}
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:10px">
          <span style="font-size:14px;font-weight:600">Запас времени на непредвиденное</span>
          <div style="display:flex;gap:8px">
            {#each Object.keys(MARGIN_TITLE) as key (key)}
              <button type="button" class={`margin-pill ${marginOf(settings) === key ? 'on' : ''}`}
                onclick={() => (store.settings = applyMargin(settings, key))}>{MARGIN_TITLE[key]}</button>
            {/each}
          </div>
          {#if custom}
            <span style="font-size:13px;color:var(--ink-3)">Свой запас: {marginLine([settings.work_pct, settings.travel_pct, settings.travel_min])}
              <button type="button" style="margin-left:6px;text-decoration:underline;font-weight:600;color:var(--ink)"
                onclick={() => (store.settings = applyMargin(settings, 'balanced'))}>вернуть пресет</button>
            </span>
          {:else}
            <span style="font-size:13px;color:var(--ink-3)">{marginLine([settings.work_pct, settings.travel_pct, settings.travel_min])}</span>
          {/if}
        </div>

        <div style="display:grid;grid-template-columns:160px minmax(0,1fr) 60px;gap:16px;align-items:center">
          <span style="font-size:14px;font-weight:600">Время на расчёт</span>
          <input type="range" min="1" max="60" step="1" style="accent-color:var(--yellow);width:100%"
            bind:value={settings.time_limit} />
          <span style="font-size:14px;font-weight:700;text-align:right">{settings.time_limit} с</span>
        </div>

        {#if building}
          <div style="display:flex;align-items:center;gap:16px;height:44px">
            <div class="build-progress"><div class="build-progress-fill"
              style={`width:${Math.min(100, elapsed / (settings.time_limit + 2) * 100)}%`}></div></div>
            <span style="font-size:14px;font-weight:700;white-space:nowrap">считаю варианты… {Math.round(elapsed)} с</span>
          </div>
        {:else if replanned}
          <div style="display:flex;flex-direction:column;gap:10px">
            <span style="font-size:13px;color:var(--ink-3)">День уже перепланирован — варианты на весь день больше не строятся. Настройки запаса учтутся при следующем перепланировании</span>
            <button type="button" class="btn gray" style="align-self:flex-start" onclick={() => store.saveSettings(settings)}>Сохранить</button>
          </div>
        {:else if started}
          <div style="display:flex;flex-direction:column;gap:10px">
            <span style="font-size:13px;color:var(--ink-3)">День уже начался — варианты на весь день больше не строятся, иначе поменялась бы уже начатая работа. Изменения вносите через «Перепланировать»; настройки запаса учтутся при нём</span>
            <button type="button" class="btn gray" style="align-self:flex-start" onclick={() => store.saveSettings(settings)}>Сохранить</button>
          </div>
        {:else}
          <div style="display:flex;gap:10px;padding-top:4px;align-items:center">
            <button type="button" class="btn yellow build" onclick={build}>Построить варианты плана</button>
            <span style="font-size:13px;color:var(--ink-3)">соберём 3 варианта и базовый для сравнения</span>
          </div>
        {/if}
      </div>
    {:else}
      <p class="muted">Загружаю…</p>
    {/if}
  {/snippet}
  {#snippet side()}
    {#if settings}
      <div class="card" style="padding:20px;display:flex;flex-direction:column;gap:18px">
        <div style="display:flex;align-items:baseline;justify-content:space-between">
          <span style="font-size:18px;font-weight:700">Данные сессии</span>
          {#if store.catalog}
            <span style="font-size:13px;color:var(--ink-3)">{shortDate(store.catalog.date)} · {store.catalog.day.join('–')}</span>
          {/if}
        </div>
        {#each mix as m}
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;font-size:13px">
              <span style="font-weight:600">{m.t}</span><span style="color:var(--ink-3)">{m.total}</span>
            </div>
            <div style="display:flex;height:10px;border-radius:5px;overflow:hidden;gap:2px">
              {#each m.parts as p}<div style={`flex:${p.n};background:${p.c}`}></div>{/each}
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--ink-2)">
              {#each m.parts as p}
                <span style="display:flex;align-items:center;gap:6px;white-space:nowrap">
                  <span style={`width:8px;height:8px;border-radius:50%;background:${p.c}`}></span>{p.l} {p.n}
                </span>
              {/each}
            </div>
          </div>
        {/each}
        <div style="display:flex;gap:8px">
          <Link href={`/s/${store.sid}/engineers`} class="btn gray" style="flex:1;justify-content:center">Инженеры →</Link>
          <Link href={`/s/${store.sid}/requests`} class="btn gray" style="flex:1;justify-content:center">Заявки →</Link>
        </div>
      </div>
    {/if}
  {/snippet}
</Shell>

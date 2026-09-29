<script>
  /** 4m «Аналитика» — наш план против базового, по часам, по навыкам, загрузка инженеров, запас по времени,
   *  приезд в окно, как менялся план, история, выгрузка CSV.
   *  Разметка backups/docs/design/DispatcherFlow.dc.html#4m. */
  import { untrack } from 'svelte';
  import { api, ApiError } from '../lib/api.js';
  import { store } from '../lib/session.svelte.js';
  import { historyRows, hourly, kmRows, loadLegend, loadRows, loadSummary, loadTotals, skillRows, slackRows, tiles, toCsv,
           trendRows, windowRows } from '../lib/analyticsView.js';
  import Shell from '../components/Shell.svelte';
  import Link from '../components/Link.svelte';

  let a = $state(null);
  let history = $state([]);
  let error = $state('');
  let loading = $state(false);

  $effect(() => {
    const pid = store.view?.plan?.plan_id;
    if (pid) untrack(load);
  });

  async function load() {
    loading = true;
    error = '';
    try {
      const [an, h] = await Promise.all([api(store.path('/analytics')), api(store.path('/history'))]);
      a = an;
      history = h;
    } catch (e) {
      error = e instanceof ApiError ? e.message : 'сервер недоступен';
    } finally {
      loading = false;
    }
  }

  const t = $derived(a ? tiles(a) : []);
  const km = $derived(a ? kmRows(a, store.engineers, store.colors) : []);
  const hrs = $derived(a ? hourly(a) : []);
  const sk = $derived(a ? skillRows(a) : []);
  const loadEng = $derived(a ? loadRows(a, store.engineers) : []);
  const loadTot = $derived(a ? loadTotals(a) : []);
  const loadSum = $derived(a ? loadSummary(a) : []);
  const slack = $derived(a ? slackRows(a) : []);
  const win = $derived(a ? windowRows(a) : []);
  const trend = $derived(a ? trendRows(history, store.catalog?.day?.[0] ?? '') : { steps: [], rows: [] });
  const hist = $derived(a ? historyRows(history, store.names, store.catalog?.day?.[0] ?? '') : []);

  function download() {
    const csv = toCsv(a, store.engineers);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `сравнение-${store.session?.title ?? store.sid}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
</script>

{#snippet loadBar(segs, aria)}
  <div class="an-load-bar" role="img" aria-label={aria}>
    {#each segs as g (g.k)}<div class={g.k === 'break' ? 'an-load-brk' : ''} style={`width:${g.w}%;background:${g.c}`}></div>{/each}
  </div>
{/snippet}

<!-- «наш» — толстая полоса в цвете корзины, поэтому в легенде — полоска из этих цветов -->
{#snippet planLegend(rows)}
  <span class="an-legend"><span class="an-legend-sq an-legend-wide" aria-hidden="true"
    style={`background:linear-gradient(90deg,${[...new Set(rows.map(r => r.c))].map((c, i, all) => `${c} ${i / all.length * 100}% ${(i + 1) / all.length * 100}%`).join(',')})`}></span>наш</span>
  <span class="an-legend"><span class="an-legend-sq" style="background:var(--idle)" aria-hidden="true"></span>базовый</span>
{/snippet}

{#snippet compareRows(rows, what)}
  {#each rows as r (r.label)}
    <div class="an-cmp-row" role="img"
         aria-label={`${what} ${r.label}: наш ${r.n ?? '—'} (${r.p}), базовый ${r.bn ?? '—'} (${r.bp})`}>
      <span>{r.label}</span>
      <div class="an-cmp-bars">
        <div class="an-cmp-cur" style={`width:${r.w}%;background:${r.c}`}></div>
        <div class="an-cmp-base" style={`width:${r.bw}%`}></div>
      </div>
      <span class="an-cmp-val"><b>{r.n ?? '—'}</b> · {r.bn ?? '—'}</span>
    </div>
  {/each}
{/snippet}

<Shell page="analytics" context={{ kind: 'analytics' }}>
  {#snippet main()}
    {#if !store.view}
      <div class="card" style="padding:40px 24px;text-align:center">Расписания ещё нет.
        <Link href={`/s/${store.sid}/setup`} style="font-weight:600;text-decoration:underline">Построить</Link></div>
    {:else if loading && !a}
      <div class="card muted" style="padding:40px 24px;text-align:center">Считаю базовый вариант…</div>
    {:else if error}
      <div class="band err">{error}</div>
    {:else if a}
      <div class="an-tiles">
        {#each t as m (m.label)}
          <div class="an-tile" style={`background:${m.bg}`}>
            <span class="an-tile-label">{m.label}</span>
            <span class="an-tile-val">{m.val}</span>
            <span class="an-tile-sub" style={`color:${m.c}`}>{m.sub}</span>
          </div>
        {/each}
      </div>
      <div class="an-note">Сравнение на вводных текущего расписания — суммы базового и нашего плана могут не совпадать, если очередь изменений не пуста.</div>
      <div class="an-grid">
        <div class="an-card" style="min-width:0">
          <div class="an-card-head">
            <span class="an-card-title">Пробег по инженерам, км</span>
            <span class="an-legend"><span class="an-legend-tick" aria-hidden="true"></span>базовый</span>
          </div>
          {#each km as r (r.name)}
            <div class="an-km-row">
              <span>{r.name}</span>
              <div class="an-bar-track" role="img" aria-label={`${r.name}: ${r.km} км, базовый на отметке`}>
                <div class="an-bar-fill" style={`width:${r.w}%;background:${r.c}`}></div>
                <div class="an-bar-tick" style={`left:${r.b}%`}></div>
              </div>
              <span class="an-km-val">{r.km}</span>
            </div>
          {/each}
        </div>
        <div class="an-col">
          <div class="an-card">
            <div class="an-card-head">
              <span class="an-card-title">Заявок в работе по часам</span>
              <span class="an-legend"><span class="an-legend-dash" aria-hidden="true"></span>на смене</span>
            </div>
            <div class="an-hours">
              {#each hrs as h (h.t)}
                <div class="an-hour">
                  <div class="an-hour-cap" style={`bottom:${h.capH}px`} aria-hidden="true"></div>
                  <span class="an-hour-n">{h.n}</span>
                  <div class="hour-bar" style={`height:${h.h}px;background:${h.c}`}
                       role="img" aria-label={`${h.t}:00 — в работе ${h.n}`}></div>
                </div>
              {/each}
            </div>
            <div class="an-hour-labels">{#each hrs as h (h.t)}<span>{h.t}</span>{/each}</div>
          </div>
          <div class="an-card">
            <span class="an-card-title">Заявки по навыкам</span>
            {#each sk as r (r.name)}
              <div class="an-skill-row">
                <span>{r.name}</span>
                <div class="an-skill-bar" role="img" aria-label={`${r.name}: назначено ${r.a} из ${r.tot}`}>
                  <div style={`width:${r.w}%;background:${r.c}`}></div>
                  <div style={`width:${r.u}%;background:var(--red)`}></div>
                </div>
                <span class="an-skill-val">{r.a}/{r.tot}</span>
              </div>
            {/each}
          </div>
        </div>
      </div>
      <div class="an-grid">
        <div class="an-card">
          <span class="an-card-title">Загрузка инженеров</span>
          <span class="an-cap">Из чего состоит смена каждого инженера в нашем плане. Сверху — вся команда: наш план и базовый.</span>
          <div class="an-legend-row">
            {#each loadLegend(loadTot) as p (p.k)}
              <span class="an-legend"><span class={`an-legend-sq${p.k === 'break' ? ' an-load-brk' : ''}`} style={`background:${p.c}`} aria-hidden="true"></span>{p.label}</span>
            {/each}
          </div>
          {#each loadTot as r (r.label)}
            <div class="an-load-row">
              <span class="an-load-team">{r.label}</span>
              {@render loadBar(r.segs, r.aria)}
              <span></span>
            </div>
          {/each}
          {#if loadSum.length}
            <div class="an-load-sum">
              {#each loadSum as l (l.label)}
                <span>{l.label}: <b>наш {l.cur}</b> · базовый {l.base}</span>
              {/each}
            </div>
          {/if}
          <div class="an-load-sep"></div>
          <div class="an-load-row an-load-headrow"><span></span><span></span><span>занят</span></div>
          {#each loadEng as r (r.name)}
            <div class="an-load-row">
              <span>{r.name}</span>
              {@render loadBar(r.segs, r.aria)}
              <span class="an-km-val">{r.busy}</span>
            </div>
          {/each}
        </div>
        <div class="an-col">
          <div class="an-card">
            <div class="an-card-head">
              <span class="an-card-title">Запас по времени</span>
              {@render planLegend(slack)}
            </div>
            <span class="an-cap">На сколько инженер может задержаться на заявке и всё равно успеть в окно — сюда и к следующим клиентам.{a.now ? ` Только заявки после ${a.now}.` : ''} Доля от заявок плана.</span>
            {@render compareRows(slack, 'запас')}
          </div>
          <div class="an-card">
            <div class="an-card-head">
              <span class="an-card-title">Когда приезжаем в окно</span>
              {@render planLegend(win)}
            </div>
            <span class="an-cap">Где внутри окна клиента инженер приезжает. «Раньше окна» — стоит у двери и ждёт, в конце окна — впритык.</span>
            {@render compareRows(win, 'приезд')}
          </div>
        </div>
      </div>
      <div class="an-card">
        <span class="an-card-title">Как менялся план за день</span>
        <span class="an-cap">{trend.steps.length > 1 ? 'Столбик — план после каждого пересчёта: назначено, пробег и сколько инженеров вышло на заявки.'
          : 'План ещё не пересчитывали — после «Перепланировать» здесь появится столбик на каждый пересчёт.'}</span>
        <div class="an-trend" style={`--n:${trend.steps.length}`}>
          <span></span>
          {#each trend.steps as t, i (i)}<span class="an-trend-t">{t}</span>{/each}
          {#each trend.rows as r (r.label)}
            <span class="an-trend-label">{r.label}</span>
            {#each r.cells as c, i (i)}
              <div class="an-trend-cell" role="img" aria-label={`${r.label} в ${trend.steps[i]}: ${c.v}`}>
                <span class="an-trend-v">{c.v}</span>
                <div class="an-trend-bar" style={`height:${c.h}px`}></div>
              </div>
            {/each}
          {/each}
        </div>
      </div>
      <div class="an-card" style="padding:0">
        <div class="an-hist-head">
          <span class="an-hist-title">История плана</span>
          <button type="button" class="btn sm gray" onclick={download}>Выгрузить CSV</button>
        </div>
        {#each hist as h, i (i)}
          <div class="an-hist-row">
            <span class="an-hist-t">{h.t}</span>
            <span>{h.why}</span>
            <span class="an-hist-a">{h.a}</span>
            <span class="an-hist-km">{h.km}</span>
            <span class="an-hist-ch">{h.ch}</span>
          </div>
        {/each}
      </div>
    {/if}
  {/snippet}
</Shell>

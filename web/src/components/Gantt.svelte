<script>
  /** Диаграмма Ганта — разметка backups/docs/design/Gantt.dc.html. Геометрия отрезков — lib/gantt.js;
   *  шкала растягивается по ширине контейнера, но не уже 780px; «−/+» — масштаб: крупнее диаграмма
   *  прокручивается вбок, колонка инженеров остаётся на месте, короткие заявки получают подписи. */
  import { onMount } from 'svelte';
  import { LEGEND, NW, ZOOMS, dayBounds, rows as buildRows, tip as buildTip, trackWidth } from '../lib/gantt.js';
  import { tick } from 'svelte';
  import { store } from '../lib/session.svelte.js';
  import { fmt } from '../lib/time.js';

  let { view, mode = 'plan', selected = null, riskOnly = false, only = null, orphaned = undefined, leaving = undefined,
        onselect = () => {} } = $props();

  let width = $state(0);
  let hov = $state(null);
  let wrap = $state(null);
  const ZKEY = 'gantt-zoom';
  let zoom = $state((() => { try { return Math.min(ZOOMS.length - 1, Math.max(0, +localStorage.getItem(ZKEY) || 0)); } catch { return 0; } })());

  const bounds = $derived(dayBounds(view));
  const TW = $derived(trackWidth(width - NW - 2, bounds[1] - bounds[0], zoom));

  // после смены масштаба держим в кадре «сейчас» (или то, что было посередине)
  async function setZoom(z) {
    const mid = wrap ? (wrap.scrollLeft + (wrap.clientWidth - NW) / 2) / TW : 0;
    zoom = z;
    try { localStorage.setItem(ZKEY, String(z)); } catch { /* приватный режим — масштаб не запомнится */ }
    await tick();
    if (!wrap) return;
    const focus = hasT ? x(now) : mid * TW;
    wrap.scrollLeft = Math.max(0, focus - (wrap.clientWidth - NW) / 2);
  }
  const x = $derived.by(() => { const [t0, t1] = bounds, tw = TW; return t => (t - t0) / (t1 - t0) * tw; });
  const hours = $derived.by(() => {
    const out = [];
    for (let t = bounds[0]; t < bounds[1]; t += 60) out.push({ t: fmt(t), l: x(t) });
    return out;
  });
  const list = $derived(buildRows(view, store.colors, x, { mode, selected, riskOnly, only, orphaned, leaving }));
  const now = $derived(store.session?.clock_min);
  const hasT = $derived(now != null && now > bounds[0] && now < bounds[1]);
  const legend = $derived(LEGEND[mode] || []);

  const TIP_W = 270, MARGIN = 8;
  let tipEl = $state(null), tipY = $state(null), anchor = null;

  // Подсказка — position:fixed по экрану (не режется overflow:hidden карточки, если строк мало).
  // Высота зависит от пояснений, поэтому сначала рисуем невидимой, меряем и ставим под отрезок или над ним.
  function enter(e, b) {
    const t = buildTip(view, store.colors, b.rid, { mode, ghost: b.kind === 'ghost' ? b.eid : null });
    if (!t) return;
    anchor = e.currentTarget.getBoundingClientRect();
    const x = Math.max(MARGIN, Math.min(anchor.left + anchor.width / 2 - TIP_W / 2, window.innerWidth - TIP_W - MARGIN));
    tipY = null;
    hov = { ...t, x };
  }
  $effect(() => {
    if (!hov || !tipEl || !anchor) return;
    const h = tipEl.offsetHeight, vh = window.innerHeight;
    const below = anchor.bottom + 2, above = anchor.top - h - 2;
    tipY = below + h <= vh - MARGIN ? below : above >= MARGIN ? above : Math.max(MARGIN, vh - h - MARGIN);
  });
  const leave = () => (hov = null);
  const style = b => `left:${b.l}px;width:${b.w}px;top:${b.top}px;height:${b.h}px;border-radius:${b.r}px;background:${b.bg};`
    + `border:${b.bd};box-shadow:${b.sh};outline:${b.ol};opacity:${b.op};color:${b.color};padding:0 ${b.pad ?? 5}px`;

  // Подсказка привязана к экранным координатам на момент наведения — при скролле страницы (в т.ч.
  // горизонтальном скролле .gantt-wrap, который не всплывает, поэтому слушаем скролл в фазе перехвата)
  // или изменении размера окна она устареет, поэтому просто прячем её; следующее наведение покажет актуальную.
  onMount(() => {
    const clear = () => (hov = null);
    window.addEventListener('scroll', clear, true);
    window.addEventListener('resize', clear);
    return () => {
      window.removeEventListener('scroll', clear, true);
      window.removeEventListener('resize', clear);
    };
  });
</script>

<div class="gantt-wrap" bind:clientWidth={width} bind:this={wrap}>
  <div class="gantt card" style={`width:${NW + TW + 2}px`}>
    <div class="gantt-head">
      <div class="gantt-name-col gantt-head-label">Инженер
        <span class="gantt-zoom" role="group" aria-label="Масштаб">
          <button type="button" aria-label="Мельче" title="Мельче" disabled={zoom === 0} onclick={() => setZoom(zoom - 1)}>−</button>
          <button type="button" aria-label="Крупнее" title="Крупнее — подписи у коротких заявок" disabled={zoom === ZOOMS.length - 1}
                  onclick={() => setZoom(zoom + 1)}>+</button>
        </span></div>
      <div class="gantt-scale" style={`width:${TW}px`}>
        {#each hours as h (h.t)}<div class="gantt-hour" style={`left:${h.l}px`}>{h.t}</div>{/each}
        {#if hasT}<div class="gantt-now-pill" style={`left:${x(now)}px`}>сейчас {fmt(now)}</div>{/if}
      </div>
    </div>
    <div class="gantt-body">
      {#each hours as h (h.t)}<div class="gantt-grid" style={`left:${NW + h.l}px`}></div>{/each}
      {#if hasT}<div class="gantt-past" style={`left:${NW}px;width:${x(now)}px`}></div>{/if}
      {#each list as row, ri (row.eid)}
        <div class="gantt-row">
          <div class="gantt-name-col gantt-name">
            <span class="gantt-dot" style={`background:${row.dot}`}></span>
            {#if row.note}
              <span class="gantt-eng-col"><span class="gantt-eng" style={`color:${row.nameColor}`}>{row.name}</span>
                <span class="gantt-note">{row.note}</span></span>
            {:else}
              <span class="gantt-eng" style={`color:${row.nameColor}`}>{row.name}</span>
            {/if}
            <span style="flex:1"></span>
            <span class="gantt-meta">{row.meta}</span>
          </div>
          <div class="gantt-track" style={`width:${TW}px`}>
            {#each row.bars as b, bi (bi)}
              {#if b.kind === 'work'}
                <button type="button" class="gantt-bar bar-work" style={style(b)} aria-label={`Заявка ${b.rid}`}
                        aria-pressed={selected === b.rid}
                        onmouseenter={e => enter(e, b)} onmouseleave={leave} onfocus={e => enter(e, b)} onblur={leave}
                        onclick={() => onselect(b.rid)}><span class="gantt-bar-label">{b.label}</span></button>
              {:else if b.kind === 'ghost'}
                <div class="gantt-bar bar-ghost" style={style(b)} role="img" aria-label={`Заявка ${b.rid} в прошлом плане`}
                     onmouseenter={e => enter(e, b)} onmouseleave={leave}><span class="gantt-bar-label">{b.label}</span></div>
              {:else if b.kind === 'badge'}
                <div class="gantt-badge" style={`left:${b.l}px;top:${b.top}px;background:${b.bg};color:${b.color};border:${b.bd}`}
                     aria-hidden="true">{b.text}</div>
              {:else}
                <div class={`gantt-bar bar-${b.kind}`} style={style(b)}><span class="gantt-bar-label">{b.label}</span></div>
              {/if}
            {/each}
          </div>
        </div>
      {/each}
      {#if hasT}<div class="gantt-now" style={`left:${NW + x(now)}px`}></div>{/if}
      {#if hov}
        <div class="gantt-tip" bind:this={tipEl}
             style={`left:${hov.x}px;top:${tipY ?? 0}px;visibility:${tipY == null ? 'hidden' : 'visible'}`}>
          <div class="gantt-tip-head" style={`background:${hov.tint}`}><span style="font-weight:700;white-space:nowrap">{hov.id}</span>
            <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{hov.type}</span></div>
          <div class="gantt-tip-grid">
            <span class="muted">Адрес</span><span>{hov.addr}</span>
            <span class="muted">Окно</span><span>{hov.win}</span>
            <span class="muted">{hov.planK}</span><span>{hov.plan}</span>
            <span class="muted">Инженер</span><span>{hov.eng}</span>
            {#if hov.tol}<span class="muted">Запас</span><span style={`font-weight:700;color:${hov.tolColor}`}>{hov.tol}</span>{/if}
          </div>
          {#each hov.lines as ln (ln.k)}
            <div class="gantt-tip-note"><div class="gantt-tip-k">{ln.k}</div>{ln.t}</div>
          {/each}
        </div>
      {/if}
    </div>
    {#if legend.length}
      <div class="gantt-legend">
        {#each legend as lg (lg.t)}<div class="gantt-legend-item"><span class="gantt-swatch" style={`background:${lg.bg};border:${lg.bd};opacity:${lg.op ?? 1};color:${lg.c ?? 'inherit'}`}>{lg.mark ?? ''}</span>{lg.t}</div>{/each}
      </div>
    {/if}
  </div>
</div>

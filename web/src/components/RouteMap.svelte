<script>
  /** 4g «Карта» — список маршрутов слева, карта посередине: все маршруты бледно, выбранный ярко
   *  с нумерованными точками (цвет — по запасу, задача 13); справа — порядок его остановок
   *  (задача: «при выборе инженера справа не отображается порядок выполнения заявок»).
   *  Наведение на точку/строку — подсказка/подсветка друг друга, клик по точке — карточка заявки
   *  (4e); клик по строке — тот же маркер на карте (без перехода: дорожная карта и так открыта).
   *  Выбранный инженер — ?e=, подсвеченная точка — ?r=. Разметка backups/docs/design/DispatcherFlow.dc.html#4g. */
  import L from 'leaflet';
  import { onMount, untrack } from 'svelte';
  import { api } from '../lib/api.js';
  import { store } from '../lib/session.svelte.js';
  import { route as addr, go } from '../lib/router.svelte.js';
  import { TILES, footer, isRoad, lineOf, pointsOf, routeList, stopList } from '../lib/mapView.js';
  import Link from './Link.svelte';

  let { view } = $props();
  let data = $state(null), show = $state('all'), error = $state(''), hoverId = $state(null);
  let el, map = $state.raw(null), layer = null, markers = {};
  const chosen = $derived(addr.query.get('e') || data?.routes[0]?.engineer_id || null);
  const list = $derived(routeList(view, store.colors, chosen));
  const base = $derived(`/s/${store.sid}/plan`);
  const selRow = $derived(list.rows.find(r => r.eid === chosen) ?? null);
  const stops = $derived(chosen ? stopList(view, chosen, store.session.clock_min, store.colors) : null);

  $effect(() => { view.plan.plan_id; untrack(async () => {
    try { data = await api(`/sessions/${store.sid}/routes`); } catch (e) { error = e.message; }
  }); });

  onMount(() => {
    const m = L.map(el, { zoomControl: false }).setView([55.62, 37.68], 12);
    L.control.zoom({ position: 'topright' }).addTo(m);
    L.tileLayer(TILES.url, TILES.options).addTo(m);
    layer = L.layerGroup().addTo(m);
    map = m;
    return () => m.remove();
  });

  $effect(() => {
    if (!map || !data) return;
    layer.clearLayers();
    markers = {};
    hoverId = null;
    let focus = null;
    for (const rt of data.routes) {
      const on = rt.engineer_id === chosen, c = store.colors[rt.engineer_id].main;
      if (!on && show === 'one') continue;
      const line = L.polyline(lineOf(rt), { color: c, weight: on ? 5 : 3, opacity: on ? 1 : 0.35,
                                            dashArray: isRoad(data.source, rt.transport) ? null : '6 6' }).addTo(layer);
      const d = rt.points[0];
      L.marker([d.lat, d.lon], { icon: L.divIcon({ className: '', html: `<span class="depot" style="border-color:${c}"></span>` }) }).addTo(layer);
      if (on) {
        focus = line;
        for (const p of pointsOf(rt, view, store.colors)) {
          const hot = addr.query.get('r') === p.id;
          const mk = L.marker(p.x, { icon: L.divIcon({ className: '', iconSize: [28, 28],
            html: `<span class="stop${hot ? ' hot' : ''}" style="background:${p.color}">${p.seq}</span>` }) })
            .bindTooltip(tipHtml(p.tip), { direction: 'right', offset: [16, 0], className: 'map-tip' })
            .on('click', () => { store.select(p.id); go(`/s/${store.sid}/plan`); })
            .on('mouseover', () => (hoverId = p.id)).on('mouseout', () => (hoverId = null))
            .addTo(layer);
          markers[p.id] = mk;
        }
      } else {
        for (const p of rt.points.slice(1)) L.circleMarker([p.lat, p.lon], { radius: 4, color: c, weight: 0, fillOpacity: 0.6 }).addTo(layer);
      }
    }
    if (focus) map.fitBounds(focus.getBounds(), { padding: [40, 40] });
  });

  // Наведение на строку списка справа ↔ подсветка точки на карте: точки уже созданы выше,
  // здесь только переключаем класс — без пересборки слоя (иначе карта дёргалась бы при каждом hover).
  $effect(() => {
    // hoverId читаем отдельной строкой (не только внутри for): при первом запуске markers ещё
    // пуст, цикл не выполнится ни разу, и без этого чтения эффект не подпишется на hoverId вовсе.
    const id0 = hoverId;
    // .stop — внутренний span значка, а не div-обёртка Leaflet (getElement()), на неё и вешаем класс
    for (const [id, mk] of Object.entries(markers)) mk.getElement()?.querySelector('.stop')?.classList.toggle('hover', id === id0);
  });

  const esc = x => String(x).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  function tipHtml(t) {
    const tint = store.colors[chosen].tint;
    return `<div class="tip-head" style="background:${tint}"><b>${esc(t.title)}</b> ${esc(t.type)}</div>`
      + `<div class="tip-grid"><span class="muted">Адрес</span><span>${esc(t.addr)}</span><span class="muted">План</span><span>${esc(t.plan)}</span>`
      + `<span class="muted">Дорога</span><span>${esc(t.leg)}</span><span class="muted">Запас</span><b style="color:${t.tolColor}">${esc(t.tol)}</b></div>`;
  }
  const pick = eid => go(`/s/${store.sid}/plan/map?e=${eid}`);
  // Клик по строке справа — центрируем карту на точке и открываем её подсказку: дорожная карта уже
  // открыта, поэтому не уводим диспетчера на диаграмму (это делает клик прямо по маркеру — 4e).
  function focusStop(id) {
    const mk = markers[id];
    if (!mk) return;
    map.panTo(mk.getLatLng());
    mk.openTooltip();
  }
</script>

<div class="plan-bar">
  <span class="seg2"><Link href={base}>Диаграмма</Link><Link href={`${base}/map`} aria-current="page">Карта</Link></span>
  <span class="chipbtn chip-select">
    <select bind:value={show} aria-label="Показать">
      <option value="all">Показать: все маршруты</option>
      <option value="one">Показать: только выбранный</option>
    </select><span aria-hidden="true">▾</span>
  </span>
</div>
{#if error}<div class="band err" role="alert">{error}<button onclick={() => (error = '')} aria-label="Скрыть">×</button></div>{/if}
<div class="map-grid">
  <div class="maproute-card">
    <div class="maproute-head"><span>Маршрут</span><span class="n">заявок</span><span class="km">км</span></div>
    {#each list.rows as r (r.eid)}
      <button type="button" class="maproute-row" aria-pressed={r.on}
              style={r.on ? `background:${store.colors[r.eid].tint}` : ''} onclick={() => pick(r.eid)}>
        <span class="maproute-name"><span class="maproute-bar" style={`background:${r.c}`}></span>
          <span style={`font-weight:${r.on ? 700 : 400}`}>{r.name}</span></span>
        <span class="n">{r.n}</span><span class="km">{r.km}</span>
      </button>
    {/each}
    <div style="flex:1"></div>
    <div class="maproute-foot"><span class="muted">Всего</span><span style="font-weight:700">{list.total} км</span></div>
  </div>
  <div class="map-col">
    {#if data && data.source !== 'osrm'}
      <div class="map-note">Время в пути — оценка по прямой: сервис дорог недоступен</div>
    {/if}
    <div class="mapcard">
      <div class="map-el" bind:this={el}></div>
      {#if selRow}
        <div class="map-foot">
          <span class="map-foot-dot" style={`background:${selRow.c}`}></span>
          <span class="map-foot-name">{selRow.name}</span>
          <span class="muted">{footer(view, chosen)}</span>
        </div>
      {/if}
    </div>
  </div>
  {#if stops}
    <div class="mapstops-card">
      <div class="maproute-head" style="display:block"><b>Порядок заявок</b> · {stops.name}</div>
      <div class="mapstops-body">
        <div class="mapstops-edge">
          <span class="mapstops-dot" style={`background:${stops.head.here ? 'var(--amber)' : selRow?.c ?? '#9AA1AB'}`}></span>
          {#if stops.head.here}
            <span><b>Сейчас здесь</b> · {stops.head.label} <span class="muted">свободен с {stops.head.time}</span></span>
          {:else}
            <span><b>{stops.head.label}</b> <span class="muted">старт {stops.head.time}</span></span>
          {/if}
        </div>
        {#each stops.rows as r (r.id)}
          <button type="button" class="mapstops-row" class:hover={hoverId === r.id}
                  onmouseenter={() => (hoverId = r.id)} onmouseleave={() => (hoverId = null)} onclick={() => focusStop(r.id)}>
            <div class="mapstops-row-top">
              <span class="mapstops-seq" style={`background:${r.color}`}>{r.seq}</span>
              <span style="font-weight:700">{r.id}</span>{#if r.manual}<span title="закреплена диспетчером">📌</span>{/if}
              <span class="muted">{r.type}</span>
              <span style="flex:1"></span>
              <span style={`color:${r.tolColor};font-weight:600`}>{r.tol}</span>
            </div>
            <div class="mapstops-addr">{r.addr}</div>
            <div class="mapstops-row-bottom muted">
              <span>{r.plan}</span><span>{r.win}</span>{#if r.leg}<span>{r.leg}</span>{/if}{#if r.wait}<span>{r.wait}</span>{/if}
            </div>
            {#if r.locked}<span class="pill gray">заморожена</span>
            {:else if r.status === 'done'}<span class="pill ok">✓ выполнена</span>
            {:else if r.status === 'active'}<span class="pill warn">● в работе</span>{/if}
          </button>
        {:else}
          <div class="side-card-empty">Нет заявок в маршруте</div>
        {/each}
        <div class="mapstops-edge">
          <span class="mapstops-dot" style="background:#9AA1AB"></span>
          <span><b>Конец смены</b> · {stops.tail.time}</span>
        </div>
        <div class="mapstops-foot muted">{stops.tail.n} · {stops.tail.km} км · в дороге {stops.tail.travel} мин</div>
      </div>
    </div>
  {/if}
</div>

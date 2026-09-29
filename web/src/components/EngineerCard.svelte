<script>
  /** 4i — правая карточка инженера: сейчас/дальше/пробег, список заявок, маршрут на карте, доступность.
   *  Разметка — правая колонка backups/docs/design/DispatcherFlow.dc.html#4i. */
  import { store } from '../lib/session.svelte.js';
  import { engineerCard, queuedFor } from '../lib/engineers.js';
  import Link from './Link.svelte';

  let { eid, onclose } = $props();

  const pending = $derived(store.session?.pending_events ?? []);
  const card = $derived(engineerCard(eid, store.engineers, store.view, store.colors, store.session.clock_min, pending));

  function openAvailability() {
    store.openModal({ kind: 'availability', eid, edit: queuedFor(eid, pending) });
  }
</script>

{#if card}
  <div class="ecard">
    <div class="ecard-head" style={`background:${card.tint}`}>
      <span class="ecard-avatar" style={`background:${card.c}`}>{card.ini}</span>
      <div class="ecard-who">
        <span class="ecard-name">{card.name}</span>
        <span class="ecard-line"><span class="ecard-dot"></span>{card.line}</span>
      </div>
      <button type="button" class="ecard-close" aria-label="Закрыть" onclick={() => onclose?.()}>×</button>
    </div>
    <div class="ecard-chips">
      {#each card.chips as c, i (i)}<span class="ecard-chip" style={`background:${c.bg};color:${c.c}`}>{c.t}</span>{/each}
    </div>
    <div class="ecard-grid">
      <span class="muted">Сейчас</span><span>{card.now}</span>
      <span class="muted">Дальше</span><span>{card.next}</span>
      <span class="muted">Пробег</span><span>{card.km}</span>
    </div>
    <div class="ecard-list">
      {#each card.list as r (r.id)}
        <div class="ecard-list-row" style={`background:${r.cur ? card.tint : '#F7F8F9'}`}>
          <span class="muted">{r.t}</span><span style="font-weight:700">{r.id}</span>
          <span class="ecard-list-type">{r.type}</span>
        </div>
      {/each}
    </div>
    <div class="ecard-actions">
      <Link href={`/s/${store.sid}/plan/map?e=${eid}`} class="btn gray">Маршрут на карте</Link>
      <button type="button" class="btn outline availability" onclick={openAvailability}>Изменить доступность</button>
    </div>
  </div>
{/if}

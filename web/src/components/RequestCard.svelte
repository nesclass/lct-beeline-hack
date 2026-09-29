<script>
  /** 4e — карточка заявки: почему этот инженер, кто ещё мог бы, переназначить.
   *  Разметка — правая колонка backups/docs/design/DispatcherFlow.dc.html#4e. */
  import { store } from '../lib/session.svelte.js';
  import { cardFor } from '../lib/requestCard.js';
  import Insight from './Insight.svelte';
  import Link from './Link.svelte';

  let { rid } = $props();

  let reassigning = $state(false);
  $effect(() => { rid; reassigning = false; });

  const card = $derived(cardFor(store.view, store.colors, rid));
  const eid = $derived(store.view?.plan?.assignments?.[rid]?.engineer_id ?? null);

  function toggleReassign() {
    if (!card?.movable.length) return;
    reassigning = !reassigning;
  }
  async function pick(mid) {
    reassigning = false;
    if (await store.moveRequest(rid, mid)) store.notice = 'Перенос в изменениях — план поменяется после «Перепланировать»';
  }
</script>

{#if card}
  <div class="request-card">
    <div class="request-head" style={`background:${card.tint}`}>
      <div class="request-head-top">
        <span class="request-id">{card.id}</span>
        <span class={`pill ${card.status.tone}`}>{card.status.text}</span>
        <span style="flex:1"></span>
        <button type="button" class="request-close" aria-label="Закрыть" onclick={() => store.closePanel()}>×</button>
      </div>
      <span class="request-sub">{card.type} · {card.addr}</span>
    </div>
    <div class="request-rows">
      {#each card.rows as [label, value, color] (label)}
        <span class="muted">{label}</span>
        {#if label === 'Инженер'}
          <span class="request-eng"><span class="request-eng-dot" style={`background:${color}`}></span>{value}</span>
        {:else if label === 'Запас'}
          <span style={`font-weight:700;color:${color}`}>{value}</span>
        {:else}
          <span>{value}</span>
        {/if}
      {/each}
    </div>
    {#if card.why}
      <div class="request-why"><Insight text={card.why} checks={card.checks} /></div>
    {:else if card.explain}
      <div class="request-explain">{card.explain}</div>
    {/if}
    {#if card.alts.length}
      <div class="request-alts-title">Кто ещё мог бы</div>
      <div class="request-alts">
        {#each card.alts as a (a.eid)}
          <div class="request-alt-row">
            <span class="request-alt-dot" style={`background:${a.c}`}></span>
            <span class="request-alt-name">{a.name}</span>
            <span class={`pill ${a.tone}`}>{a.text}</span>
          </div>
        {/each}
      </div>
    {/if}
    <div class="request-actions">
      {#if eid}
        <Link href={`/s/${store.sid}/plan/map?e=${eid}&r=${rid}`} class="btn gray sm">На карте</Link>
      {:else}
        <button type="button" class="btn gray sm" disabled title="Заявка не в маршруте">На карте</button>
      {/if}
      <button type="button" class="btn gray sm" disabled={!card.movable.length} aria-expanded={reassigning}
              title={card.movable.length ? '' : 'никто другой не успевает'} onclick={toggleReassign}>Переназначить…</button>
      <button type="button" class="btn violet sm discuss" onclick={() => store.openAssistant({ kind: 'request', id: rid })}>✦ Обсудить</button>
    </div>
    {#if reassigning}
      <div class="request-move-list">
        {#each card.movable as m (m.eid)}
          <button type="button" class="request-move-row" onclick={() => pick(m.eid)}>{m.name} · {m.text}</button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

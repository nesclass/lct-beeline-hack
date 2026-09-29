<script>
  /** 4l «Что изменилось» — разбор непринятого черновика: плитки «было», пояснение ассистента,
   *  группы правок, «Откатить» / «Принять и уведомить». Разметка backups/docs/design/DispatcherFlow.dc.html#4l. */
  import { store } from '../lib/session.svelte.js';
  import { affectedText, deltaTiles, groups, insight } from '../lib/diffView.js';
  import Insight from './Insight.svelte';

  const plan = $derived(store.view.plan);
  const tiles = $derived(deltaTiles(plan, store.view.previous.metrics));
  const g = $derived(groups(plan, store.names));

  async function onAccept() {
    const affected = await store.accept();
    if (affected) store.notice = affectedText(affected, store.names);
  }
</script>

<div class="diff-panel side-card">
  <div class="diff-panel-title">Что изменилось</div>
  <div class="diff-tiles">
    {#each tiles as t (t.k)}
      <div class="diff-tile" style={`background:${t.bg}`}>
        <span class="diff-tile-k">{t.k}</span>
        <span class="diff-tile-b">{t.b}</span>
        <span class="diff-tile-a" style={`color:${t.c}`}>{t.a}</span>
      </div>
    {/each}
  </div>
  <div class="diff-insight-wrap">
    <Insight text={insight(plan, store.names)} onDiscuss={() => store.openAssistant({ kind: 'changes' })} />
  </div>
  {#each g as grp (grp.t)}
    <div class="diff-group">
      <div class="diff-group-head"><span class="diff-swatch" style={`background:${grp.sw.bg};border:${grp.sw.bd}`}></span>{grp.t} · {grp.n}</div>
      {#each grp.items as it (it.id)}
        <div class="diff-item"><span class="diff-item-id">{it.id}</span><span class="diff-item-text">{it.text}</span><span class="diff-item-t">{it.t}</span></div>
      {/each}
    </div>
  {/each}
  <div class="diff-actions">
    <button type="button" class="btn gray rollback" disabled={!!store.busy} onclick={() => store.rollback()}>Откатить</button>
    <button type="button" class="btn yellow accept" disabled={!!store.busy} onclick={onAccept}>Принять и уведомить</button>
  </div>
</div>

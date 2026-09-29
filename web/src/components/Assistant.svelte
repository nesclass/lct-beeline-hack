<script>
  /** 4f «Ассистент» — общая панель диалога, одна на все вкладки. Разметка backups/docs/design/Assistant.dc.html.
   *  Ничего не применяет сам: «Добавить в изменения» кладёт правку в очередь через store.moveRequest. */
  import { store } from '../lib/session.svelte.js';
  import { contextLabel, placeholder, rowView } from '../lib/assistantView.js';

  const a = $derived(store.assistant);
  const waiting = $derived(a.messages.length > 0 && a.messages[a.messages.length - 1].role === 'user');

  let showHistory = $state(false);
  let draft = $state('');
  let bodyEl = $state(null);

  $effect(() => { a.messages.length; if (bodyEl) bodyEl.scrollTop = bodyEl.scrollHeight; });

  function send(text) {
    const q = (text ?? draft).trim();
    if (!q) return;
    draft = '';
    store.ask(q);
  }
  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  }

  function toggleHistory() { showHistory = !showHistory; }
  function restore(i) {
    store.restoreConversation(i);
    showHistory = false;
  }

  async function addToChanges(m) {
    if (await store.moveRequest(m.action.request_id, m.action.engineer_id)) { m.action = null; m.actionDone = true; }
  }
  function skipAction(m) { m.action = null; }
</script>

<div class="assistant-panel">
  <div class="assistant-head">
    <span class="assistant-mark">✦</span>
    <div class="assistant-title">
      <span class="assistant-name">Ассистент</span>
      <span class="assistant-ctx">видит: {a.label || contextLabel(a.context, store.view, store.names)}</span>
    </div>
    <button type="button" class="assistant-history" onclick={toggleHistory}>История</button>
    <button type="button" class="assistant-close" onclick={() => store.closePanel()} aria-label="Закрыть">×</button>
  </div>
  {#if showHistory}
    <div class="assistant-body assistant-hist">
      {#if a.past.length}
        {#each a.past as p, i (i)}
          <button type="button" class="assistant-hist-item" onclick={() => restore(i)}>
            <span class="assistant-hist-label">{p.label}</span>
            <span class="assistant-hist-q">{p.messages[0]?.text ?? ''}</span>
          </button>
        {/each}
      {:else}
        <span class="muted">Прошлых разговоров пока нет</span>
      {/if}
    </div>
  {:else}
    <div class="assistant-body" bind:this={bodyEl}>
      {#each a.messages as m, mi (mi)}
        {#if m.role === 'user'}
          <div class="user-bubble">{m.text}</div>
        {:else}
          <div class="ai-bubble" class:ai-error={m.source === 'error'}>
            {#if m.tools?.length}
              <div class="ai-tools">{#each m.tools as t (t)}<span class="ai-tool">✓ {t}</span>{/each}</div>
            {/if}
            <span class="ai-text">{m.text}</span>
            {#if m.rows?.length}
              <div class="ai-rows">
                {#each m.rows as r, ri (ri)}
                  {@const rv = rowView(r, store.colors, ri)}
                  <div class="ai-row">
                    <span class="ai-row-n"><span class="ai-row-dot" style={`background:${rv.dot}`}></span>{rv.n}</span>
                    <span class="ai-row-a">{rv.a}</span>
                    <span class="ai-row-v" style={`color:${rv.vc}`}>{rv.v}</span>
                  </div>
                {/each}
              </div>
            {/if}
            {#if m.action}
              <div class="ai-action">
                <span class="ai-action-title">{m.action.title}</span>
                <div class="ai-action-btns">
                  <button type="button" class="ai-action-add" onclick={() => addToChanges(m)}>Добавить в изменения</button>
                  <button type="button" class="ai-action-skip" onclick={() => skipAction(m)}>Не нужно</button>
                </div>
              </div>
            {:else if m.actionDone}
              <span class="ai-action-done">✓ в изменениях</span>
            {/if}
            {#if m.source === 'template'}
              <span class="ai-tpl">отвечаю по шаблону: языковая модель недоступна</span>
            {/if}
          </div>
        {/if}
      {/each}
      {#if waiting}<div class="ai-wait" role="status" aria-label="Ассистент думает"><span></span><span></span><span></span></div>{/if}
    </div>
    {#if a.suggestions?.length}
      <div class="assistant-suggest">
        {#each a.suggestions as s (s)}<button type="button" onclick={() => send(s)}>{s}</button>{/each}
      </div>
    {/if}
    <div class="assistant-input">
      <input class="assistant-field" type="text" placeholder={placeholder(a.context)} bind:value={draft}
             onkeydown={onKey} disabled={waiting} aria-label="Вопрос ассистенту" />
      <button type="button" class="assistant-send" onclick={() => send()} disabled={waiting} aria-label="Отправить">↑</button>
    </div>
  {/if}
</div>

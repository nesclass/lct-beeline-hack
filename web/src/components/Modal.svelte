<script>
  /** Окно поверх плана (DispatcherFlow #4h/#4j) — общий каркас: заголовок, тело, подвал.
   *  aside — необязательная панель справа внутри затемнения (задачи 17, 20). */
  let { title, onclose, width = 680, children, footer, aside } = $props();
  function key(e) { if (e.key === 'Escape') onclose(); }
</script>

<svelte:window onkeydown={key} />
<div class="overlay" class:has-aside={!!aside} role="presentation" onclick={e => e.target === e.currentTarget && onclose()}>
  <div class="modal" role="dialog" aria-modal="true" aria-label={title} style="width:{width}px">
    <div class="modal-head"><span class="modal-title">{title}</span><button type="button" onclick={onclose} aria-label="Закрыть">×</button></div>
    <div class="modal-body">{@render children()}</div>
    {#if footer}<div class="modal-foot">{@render footer()}</div>{/if}
  </div>
  {#if aside}{@render aside()}{/if}
</div>

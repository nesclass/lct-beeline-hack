<script>
  /** Фиолетовая подсказка ассистента — общий блок 4c/4e/4l. checks (4e) — проверки сеткой 2×2 под текстом. */
  let { text, checks = null, onDiscuss = null } = $props();
</script>

<div class="insight">
  <span class="insight-mark">✦</span>
  <div class="insight-body">
    <span class="insight-text">{text}</span>
    {#if checks?.length}
      <div class="insight-checks">
        {#each checks as c (c)}<span class="insight-check"><span class="insight-check-mark">✓</span>{c}</span>{/each}
      </div>
    {/if}
  </div>
  {#if onDiscuss}
    <button type="button" class="insight-discuss" onclick={onDiscuss}>Обсудить</button>
  {/if}
</div>

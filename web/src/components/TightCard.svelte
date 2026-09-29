<script>
  /** «Мало запаса» (4d). items — lib/plan.js tightList(). */
  let { items } = $props();
</script>

<div class="side-card">
  <div class="side-card-head"><span class="side-card-title">Мало запаса</span></div>
  {#each items as t (t.id)}
    <div class="tight-row"><span style="font-weight:700">{t.id}</span>
      <span class="tight-who"><span class="tight-dot" style={`background:${t.ec}`}></span>{t.eng} · {t.t}</span>
      <span class={`tight-pill ${t.tone}`}>{t.tol} мин</span></div>
  {:else}
    <div class="side-card-empty">Все остановки с запасом не меньше 20 минут</div>
  {/each}
</div>

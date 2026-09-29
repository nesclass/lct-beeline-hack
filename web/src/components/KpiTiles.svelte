<script>
  /** Плитки 4d: цветная полоса, подпись, значение. items — lib/plan.js kpis(). */
  let { items } = $props();
</script>

<div class="kpis">
  {#each items as m (m.label)}
    <div class="kpi"><span class="kpi-strip" style={`background:${m.c}`}></span>
      <div class="kpi-text"><span class="kpi-label">{m.label}</span><span class="kpi-val">{m.val}</span></div></div>
  {/each}
</div>

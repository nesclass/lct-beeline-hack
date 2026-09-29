<script>
  /** «Не назначены» (4d). items — lib/plan.js unassignedList(). */
  let { items } = $props();
</script>

<div class="side-card">
  <div class="side-card-head"><span class="side-card-title">Не назначены</span>
    {#if items.length}<span class="count-badge">{items.length}</span>{/if}</div>
  {#each items as u (u.id)}
    <div class="unassigned-row">
      <div class="unassigned-top"><span style="font-weight:700">{u.id}</span><span>{u.type}</span><span style="flex:1"></span>
        <span class="unassigned-win">{u.win}</span></div>
      <span class="unassigned-why">{u.why}</span>
    </div>
  {:else}
    <div class="side-card-empty">Все заявки назначены</div>
  {/each}
</div>

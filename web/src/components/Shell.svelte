<script>
  /** Правая колонка: ассистент (4f) заменяет её на любом экране, пока открыт (задача 20). */
  import Header from './Header.svelte';
  import Assistant from './Assistant.svelte';
  import { store } from '../lib/session.svelte.js';
  // top — полоса над обеими колонками (фильтры и плитки 4d)
  let { page, context = { kind: 'plan' }, main, side, banner, top } = $props();
</script>

<Header {page} {context} />
{#if banner}{@render banner()}{/if}
<div class="shell">
  {#if top}<div class="shell-top">{@render top()}</div>{/if}
  <div class="shell-main">{@render main()}</div>
  <!-- без панели и без ассистента колонку не держим: основная часть (карта, аналитика) — во всю ширину -->
  {#if store.panel === 'assistant' || side}
    <aside class="shell-side">{#if store.panel === 'assistant'}<Assistant />{:else}{@render side()}{/if}</aside>
  {/if}
</div>

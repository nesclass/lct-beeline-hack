<script>
  import { untrack } from 'svelte';
  import { go, route } from './lib/router.svelte.js';
  import { parse, setupClosed } from './lib/routes.js';
  import { store } from './lib/session.svelte.js';
  import Link from './components/Link.svelte';
  import Header from './components/Header.svelte';
  import Home from './pages/Home.svelte';
  import Setup from './pages/Setup.svelte';
  import Variants from './pages/Variants.svelte';
  import Plan from './pages/Plan.svelte';
  import Analytics from './pages/Analytics.svelte';
  import Engineers from './pages/Engineers.svelte';
  import Requests from './pages/Requests.svelte';
  import EventModal from './components/EventModal.svelte';
  import AvailabilityModal from './components/AvailabilityModal.svelte';

  const r = $derived(parse(route.path));
  // полоса ошибки и уведомление относятся к экрану, где случились: при переходе — убрать
  $effect(() => { route.path; untrack(() => { store.error = ''; store.notice = ''; }); });
  // зависимость — только адрес: то, что open читает и пишет в сторе, эффект не перезапускает
  $effect(() => { const sid = r.sid; if (sid) untrack(() => store.open(sid)); });
  // расписание уже есть — настройки нет: адрес заменяем, чтобы «назад» не вернул на неё
  const closed = $derived(setupClosed(r, store.session));
  $effect(() => { if (closed) go(`/s/${r.sid}/plan`, { replace: true }); });
</script>

{#if r.page === 'home'}
  <Home />
{:else if r.page === 'notfound'}
  <Header page="" minimal />
  <main style="padding:40px"><p>Нет такой страницы. <Link href="/" style="text-decoration:underline">К сценариям</Link></p></main>
{:else if r.page !== 'home' && store.missing}
  <Header page="" minimal />
  <main style="padding:40px"><p class="err">Сессия не найдена — возможно, база была очищена.
    <Link href="/" style="text-decoration:underline">Выбрать сценарий</Link></p></main>
{:else if r.page !== 'home' && !store.session}
  <Header page="" minimal />
  <main style="padding:40px"><p class="muted">Загружаю сессию…</p></main>
{:else if closed}
  <Header page="plan" />
{:else if r.page === 'setup'}
  <Setup />
{:else if r.page === 'variants'}
  <Variants />
{:else if r.page === 'plan'}
  <Plan sub={r.sub} />
{:else if r.page === 'analytics'}
  <Analytics />
{:else if r.page === 'engineers'}
  <Engineers />
{:else if r.page === 'requests'}
  <Requests />
{/if}
<!-- MODALS -->
{#if store.modal?.kind === 'event'}<EventModal />{/if}
{#if store.modal?.kind === 'availability'}<AvailabilityModal />{/if}

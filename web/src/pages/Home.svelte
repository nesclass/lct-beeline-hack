<script>
  /** 4a «Сценарии дня» — новые сессии, недавние, загрузка своего файла. Разметка backups/docs/design/DispatcherFlow.dc.html#4a. */
  import { onMount } from 'svelte';
  import { api } from '../lib/api.js';
  import { go } from '../lib/router.svelte.js';
  import { decodeFile, scenarioCards, sessionRows } from '../lib/home.js';
  import Header from '../components/Header.svelte';
  import Link from '../components/Link.svelte';

  let cards = $state([]), rows = $state([]), error = $state(''), errors = $state([]), creating = $state('');
  let fileInput;

  async function load() {
    try {
      const [sc, ss] = await Promise.all([api('/scenarios'), api('/sessions')]);
      cards = scenarioCards(sc); rows = sessionRows(ss);
    } catch (e) { error = e.message; }
  }
  onMount(load);

  async function start(id) {
    creating = id; error = '';
    try { go(`/s/${(await api('/sessions', { method: 'POST', body: { scenario: id } })).session_id}/setup`); }
    catch (e) { error = e.message; creating = ''; }
  }

  async function upload(ev) {
    const f = ev.currentTarget.files[0];
    ev.currentTarget.value = '';
    if (!f) return;
    error = ''; errors = [];
    try {
      const card = await api('/scenarios/upload', { method: 'POST', body: { filename: f.name, content: decodeFile(await f.arrayBuffer()) } });
      await start(card.id);
    } catch (e) { error = e.message; errors = e.errors || []; }
  }
</script>

<Header page="home" minimal />
<div style="max-width:1120px;margin:0 auto;padding:36px 24px 44px;display:flex;flex-direction:column;gap:24px">
  <div style="display:flex;align-items:flex-end;gap:20px">
    <div style="display:flex;flex-direction:column;gap:6px;flex:1">
      <span style="font-size:32px;font-weight:700;letter-spacing:-.01em">Сценарии дня</span>
      <span style="font-size:15px;color:var(--ink-3)">Сессия — своя копия инженеров и заявок. Исходные данные не меняются.</span>
    </div>
    <button type="button" class="btn outline" onclick={() => fileInput.click()}>Загрузить CSV / JSON</button>
    <input type="file" accept=".csv,.json" hidden bind:this={fileInput} onchange={upload} />
  </div>

  {#if error}
    <div class="upload-errors" style="display:flex;flex-direction:column;gap:6px;padding:14px 18px;border-radius:14px;background:var(--red-tint);color:var(--red-ink)">
      <span style="font-weight:700">{error}</span>
      {#each errors as line}<span style="font-size:13px">{line}</span>{/each}
    </div>
  {/if}

  <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px">
    {#each cards as c (c.id)}
      <div class="scenario-card" data-scenario={c.id}
        style="display:flex;flex-direction:column;background:var(--card);border-radius:18px;overflow:hidden;border:1px solid var(--line)">
        <div style="display:flex;flex-direction:column;gap:6px;padding:20px 20px 18px;background:{c.bg}">
          <span style="font-size:20px;font-weight:700">{c.title}</span>
          <span style="font-size:13px;color:var(--ink-2)">{c.desc}</span>
          {#if c.uploaded}<span style="font-size:12px;color:var(--muted)">из файла</span>{/if}
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:16px 20px">
          <div style="display:flex;flex-direction:column">
            <span style="font-size:22px;font-weight:700">{c.eng}</span><span style="font-size:12px;color:var(--muted)">инженеров</span>
          </div>
          <div style="display:flex;flex-direction:column">
            <span style="font-size:22px;font-weight:700">{c.req}</span><span style="font-size:12px;color:var(--muted)">заявок</span>
          </div>
          <div style="display:flex;flex-direction:column">
            <span style="font-size:22px;font-weight:700">{c.area}</span><span style="font-size:12px;color:var(--muted)">{c.districts}</span>
          </div>
        </div>
        <div style="padding:0 20px 20px">
          <button type="button" class={`btn ${c.primary ? 'yellow' : 'gray'}`} style="width:100%"
            disabled={creating === c.id} onclick={() => start(c.id)}>Новая сессия</button>
        </div>
      </div>
    {/each}
  </div>

  <div style="background:var(--card);border-radius:18px;border:1px solid var(--line);overflow:hidden">
    <div style="padding:16px 20px 8px;font-size:16px;font-weight:700">Недавние сессии</div>
    {#if rows.length === 0}
      <div class="muted" style="padding:8px 20px 20px">Сессий пока нет</div>
    {:else}
      {#each rows as x (x.sid)}
        <div style="display:grid;grid-template-columns:90px 200px 110px minmax(0,1fr) 160px 130px;align-items:center;gap:12px;height:52px;padding:0 20px;border-top:1px solid var(--line-3);font-size:14px">
          <span class="muted">{x.short}</span>
          <span style="font-weight:600">{x.scen}</span>
          <span>сейчас {x.clock}</span>
          <span class="pill {x.pill.tone}" style="justify-self:start">{x.pill.text}</span>
          <span class="muted" style="white-space:nowrap">{x.upd}</span>
          <Link href={x.href} class="btn sm gray" style="justify-self:end">Продолжить</Link>
        </div>
      {/each}
    {/if}
  </div>
</div>

<script>
  /** Поля заявки — разметка backups/docs/design/DispatcherFlow.dc.html#4h.
   *  form — { address, type, transport, tw_start, tw_end, urgent }; см. lib/requestForm.js. */
  import { workInfo } from '../lib/requestForm.js';
  import { TRANSPORT_SHORT } from '../lib/labels.js';

  let { form = $bindable(), catalog, showPriority = false } = $props();

  const work = $derived(workInfo(form, catalog));
</script>

<div class="rf-grid">
  <div class="rf-field wide">
    <span class="rf-label">Адрес</span>
    <input type="text" name="address" list="districts" placeholder="Район, улица, дом" bind:value={form.address} />
    <datalist id="districts">
      {#each catalog.districts as d (d.name)}<option value={`${d.name}, `}></option>{/each}
    </datalist>
  </div>
  <div class="rf-field">
    <span class="rf-label">Тип работ</span>
    <select bind:value={form.type}>
      {#each catalog.types as t (t.type)}<option value={t.type}>{t.type}</option>{/each}
    </select>
  </div>
  <div class="rf-field">
    <span class="rf-label">Транспорт</span>
    <select bind:value={form.transport}>
      <option value="">Любой</option>
      {#each Object.keys(catalog.transport || {}) as k (k)}<option value={k}>{TRANSPORT_SHORT[k] || catalog.transport[k]}</option>{/each}
    </select>
  </div>
  <div class="rf-field">
    <span class="rf-label">Окно клиента</span>
    <div class="rf-window">
      <input type="time" step="300" aria-label="Начало окна" bind:value={form.tw_start} />
      <input type="time" step="300" aria-label="Конец окна" bind:value={form.tw_end} />
    </div>
  </div>
  {#if showPriority}
    <div class="rf-field">
      <span class="rf-label">Приоритет</span>
      <div class="rf-seg">
        <button type="button" class:on={!form.urgent} onclick={() => (form.urgent = false)}>Обычная</button>
        <button type="button" class:on={form.urgent} onclick={() => (form.urgent = true)}>Срочная</button>
      </div>
    </div>
  {/if}
  <div class="rf-chips">
    <span class="rf-chip skill">навык: {work.skill}</span>
    <span class="rf-chip">работа {work.minutes} мин</span>
  </div>
</div>

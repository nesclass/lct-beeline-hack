<script>
  /** Поле времени без нативного <input type=time>: тот в разных браузерах и локалях рисуется
   *  по-разному (12-часовой формат, скрытая иконка) и в окне 4j обрезался. Здесь — маска «ЧЧ:ММ»
   *  (цифры, двоеточие само, четыре цифры — сразу применяется) и шаг ∓15 мин кнопками; раньше min не опускается. */
  import { clamp, fmt, hm, maskTime, parseTime } from '../lib/time.js';

  let { value, onchange, min = null, max = '23:59', step = 15, name = undefined, label = 'Время' } = $props();
  let draft = $state(null);                 // пока поле в фокусе — то, что набрано

  const bound = v => fmt(clamp(hm(v), min ? hm(min) : 0, hm(max)));
  function commit() {
    if (draft === null) return;
    const v = parseTime(draft);
    draft = null;
    if (v && bound(v) !== value) onchange(bound(v));
  }
  function onInput(e) {
    const el = e.currentTarget, erasing = e.inputType?.startsWith('delete');
    // стирание не трогаем маской — иначе двоеточие не удалить; при наборе — форматируем
    const m = erasing ? { text: el.value, complete: false } : maskTime(el.value);
    draft = m.text;
    el.value = m.text;
    if (m.complete) { commit(); queueMicrotask(() => el.select()); }   // следующая цифра — новое время, а не хвост
  }
  const shift = d => onchange(bound(fmt(clamp(hm(value) + d, 0, 23 * 60 + 59))));
</script>

<span class="tf">
  <button type="button" class="tf-step" aria-label={`${label}: на ${step} минут раньше`} disabled={!!min && hm(value) <= hm(min)}
          onclick={() => shift(-step)}>−</button>
  <input class="tf-input" {name} aria-label={label} inputmode="numeric" autocomplete="off" maxlength="5"
         placeholder="ЧЧ:ММ" value={draft ?? value} oninput={onInput} onfocus={e => e.currentTarget.select()} onclick={e => { if (draft === null) e.currentTarget.select(); }}
         onblur={commit} onchange={commit}
         onkeydown={e => { if (e.key === 'Enter') e.currentTarget.blur();
                          else if (e.key === 'Escape') { e.stopPropagation(); draft = null; e.currentTarget.value = value; e.currentTarget.blur(); }
                          else if (e.key === 'ArrowUp') { e.preventDefault(); shift(step); }
                          else if (e.key === 'ArrowDown') { e.preventDefault(); shift(-step); } }} />
  <button type="button" class="tf-step" aria-label={`${label}: на ${step} минут позже`} onclick={() => shift(step)}>+</button>
</span>

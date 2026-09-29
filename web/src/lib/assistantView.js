/** 4f ассистент — общий формат строк ответа, подсказка в поле и первый вопрос при «Обсудить». */
export const TONE = { ok: 'var(--green)', warn: 'var(--amber-text)', bad: 'var(--red)', ink: 'var(--ink)' };
const DOTS = ['var(--green)', 'var(--yellow)', 'var(--blue)', 'var(--red)'];

export const rowView = (r, colors, i) => ({ n: r.name, dot: r.engineer_id && colors[r.engineer_id] ? colors[r.engineer_id].main : DOTS[i % DOTS.length],
                                            a: r.a, v: r.v, vc: TONE[r.tone] || TONE.ink });

/** «видит: …» сразу при открытии — те же подписи, что у сервера (app/assistant.label); ответ потом
 *  заменит своей. Раньше до первого ответа в шапке стояло пустое «видит:». */
export function contextLabel(ctx, view, names = {}) {
  if (!ctx) return '';
  const d = view?.meta?.date, day = d ? `${d.slice(8, 10)}.${d.slice(5, 7)}` : 'сегодня', now = view?.plan?.now;
  switch (ctx.kind) {
    case 'request': return `заявка ${ctx.id} · план на ${day}`;
    case 'engineer': return `инженер ${names[ctx.id] ?? ctx.id} · недоступность`;
    case 'changes': return now ? `перепланирование от ${now}` : 'изменения в очереди';
    case 'analytics': return `аналитика · план ${now || 'на день'} и базовый`;
    case 'variants': return 'варианты плана';
    default: return `план на ${day}`;
  }
}

export const placeholder = ctx => (ctx?.kind === 'engineer' ? 'Спросите о последствиях' : 'Спросите о плане или попросите изменить');

export function firstQuestion(ctx) {
  switch (ctx?.kind) {
    case 'request': return `Почему так назначена ${ctx.id}?`;
    case 'changes': return 'Коротко: что поменялось?';
    case 'variants': return 'Какой вариант выбрать?';
    case 'analytics': return 'Чем наш план лучше базового?';
    case 'engineer': return 'Что будет?';
    default: return null;
  }
}

/** Полный снимок текущего разговора для past — контекст и history для сервера, не только подписи. */
const snapshot = s => ({ id: s.id, context: s.context, label: s.label, messages: s.messages, suggestions: s.suggestions, history: s.history });

/** Переключение контекста (открыли «Обсудить» по другому предмету): если контекст не меняется — состояние
 *  не трогаем; иначе текущий разговор целиком уходит в past, а новый стартует с чистого листа.
 *  id новому разговору не назначает (это решает вызывающий код — только когда переключение действительно произошло). */
export function switchTo(state, context) {
  if (!context || JSON.stringify(context) === JSON.stringify(state.context)) return state;
  const past = state.messages.length ? [snapshot(state), ...state.past].slice(0, 10) : state.past;
  return { id: undefined, context, label: '', messages: [], suggestions: [], history: [], past };
}

/** Восстановление разговора из past по индексу: контекст и history возвращаются вместе с сообщениями —
 *  иначе следующий вопрос уйдёт на сервер с чужим контекстом и пустой историей. Текущий разговор архивируется. */
export function restore(state, index) {
  const chosen = state.past[index];
  if (!chosen) return state;
  const rest = state.past.filter((_, i) => i !== index);
  const past = state.messages.length ? [snapshot(state), ...rest].slice(0, 10) : rest;
  return { id: chosen.id, context: chosen.context, label: chosen.label, messages: chosen.messages, suggestions: chosen.suggestions, history: chosen.history, past };
}

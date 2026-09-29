import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, errorText } from './api.js';

const reply = (status, text) => vi.fn(async () => ({ ok: status < 400, status, text: async () => text }));
afterEach(() => vi.unstubAllGlobals());

describe('ошибки', () => {
  it('строка, список pydantic, словарь загрузки, пусто', () => {
    expect(errorText({ detail: 'нет такой сессии' }, 404)).toBe('нет такой сессии');
    expect(errorText({ detail: [{ msg: 'Value error, конец окна должен быть позже начала' }] }, 422))
      .toBe('конец окна должен быть позже начала');
    expect(errorText({ detail: { message: 'в файле есть ошибки', errors: ['строка 2: …'] } }, 422)).toBe('в файле есть ошибки');
    expect(errorText(null, 502)).toBe('сервер не ответил как ожидалось (502)');
  });
});

describe('запрос', () => {
  it('JSON туда и обратно', async () => {
    const f = reply(200, '{"session_id":"abc"}');
    vi.stubGlobal('fetch', f);
    expect(await api('/sessions', { method: 'POST', body: { scenario: 'normal' } })).toEqual({ session_id: 'abc' });
    expect(f).toHaveBeenCalledWith('/api/sessions', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{"scenario":"normal"}' });
  });
  it('ошибка с текстом и замечаниями', async () => {
    vi.stubGlobal('fetch', reply(422, '{"detail":{"message":"в файле есть ошибки","errors":["строка 2: x"]}}'));
    const e = await api('/scenarios/upload', { method: 'POST', body: {} }).catch(x => x);
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.message, e.errors]).toEqual([422, 'в файле есть ошибки', ['строка 2: x']]);
  });
  it('тело не в JSON и обрыв сети', async () => {
    vi.stubGlobal('fetch', reply(500, 'Internal Server Error'));
    expect((await api('/x').catch(x => x)).message).toBe('сервер не ответил как ожидалось (500)');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const e = await api('/x').catch(x => x);
    expect([e.status, e.message]).toEqual([0, 'сервер недоступен — проверьте, что он запущен']);
  });
});
